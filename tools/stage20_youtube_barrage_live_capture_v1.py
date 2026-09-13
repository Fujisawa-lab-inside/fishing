#!/usr/bin/env python3
"""Bounded YouTube-live frame capture for Onga barrage lamp calibration.

The command deliberately captures only a short calibration window.  It does
not infer a gate state and never stores the expiring signed media URL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/stage20_youtube_barrage_live_source_v1.json"
TOKYO = ZoneInfo("Asia/Tokyo")
SCHEMA = "onga-stage20-youtube-barrage-live-capture-v1"
STATUS = "PASS_BOUNDED_FRAME_CAPTURE_NOT_GATE_INFERENCE"
ALLOWED_MEDIA_HOST_SUFFIXES = (".googlevideo.com", ".youtube.com", ".youtube-nocookie.com")


class LiveCaptureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveCaptureError(f"[stage20-youtube-barrage-live-capture-v1] {message}")


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LiveCaptureError(f"[stage20-youtube-barrage-live-capture-v1] invalid config: {path}") from error
    require(value.get("schema") == "onga-stage20-youtube-barrage-live-source-v1", "config schema changed")
    require(value.get("status") == "PUBLIC_LIVE_SOURCE_CONFIRMED_CAPTURE_CANDIDATE_NOT_GATE_LABEL", "source status changed")
    require(value.get("videoId") == "8_77np7-EDU", "video ID changed")
    require(value.get("watchUrl") == "https://www.youtube.com/watch?v=8_77np7-EDU", "watch URL changed")
    capture = value.get("capture", {})
    require(capture.get("wholeDayVideoRetentionPermitted") is False, "whole-day retention must remain disabled")
    require(capture.get("signedMediaUrlRetentionPermitted") is False, "signed media URL retention must remain disabled")
    boundary = value.get("boundary", {})
    for forbidden in (
        "gateStateInferred",
        "trainingLabelGenerated",
        "lampCoordinatesConfirmed",
        "lampAbsenceInterpretedAsClosed",
        "hydraulicSolverExecuted",
        "forecastAuthorized",
        "fishingDecisionAuthorized",
    ):
        require(boundary.get(forbidden) is False, f"forbidden boundary enabled: {forbidden}")
    return value


def validate_media_url(value: str) -> str:
    require(isinstance(value, str) and "\n" not in value and "\r" not in value, "resolved media URL is invalid")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    require(parsed.scheme == "https", "resolved media URL is not HTTPS")
    require(any(host.endswith(suffix) for suffix in ALLOWED_MEDIA_HOST_SUFFIXES), f"resolved media host is not allowlisted: {host}")
    require(bool(parsed.path), "resolved media URL has no path")
    return value


def resolve_media_url(watch_url: str, yt_dlp: str, maximum_height_px: int) -> str:
    require(1 <= maximum_height_px <= 1080, "maximum frame height is outside 1..1080")
    command = [
        yt_dlp,
        "--no-playlist",
        "--no-warnings",
        "--get-url",
        "--format",
        f"bestvideo[height<={maximum_height_px}]/bestvideo",
        watch_url,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise LiveCaptureError("[stage20-youtube-barrage-live-capture-v1] yt-dlp resolution failed") from error
    require(completed.returncode == 0, f"yt-dlp failed: {completed.stderr.strip()[:300]}")
    candidates = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    require(len(candidates) == 1, "yt-dlp must return exactly one combined media URL")
    return validate_media_url(candidates[0])


def ffmpeg_command(ffmpeg: str, media_url: str, output_pattern: Path, duration_seconds: int, fps: float) -> list[str]:
    validate_media_url(media_url)
    require(15 <= duration_seconds <= 900, "capture duration must remain within 15..900 seconds")
    require(1.0 <= fps <= 4.0, "capture frame rate must remain within 1..4 fps")
    return [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        media_url,
        "-t",
        str(duration_seconds),
        "-an",
        "-vf",
        f"fps={fps:g},scale=-2:720:force_original_aspect_ratio=decrease",
        "-q:v",
        "3",
        str(output_pattern),
    ]


def inspect_frames(paths: Sequence[Path]) -> list[dict[str, Any]]:
    require(bool(paths), "no JPEG frames were captured")
    rows: list[dict[str, Any]] = []
    total_bytes = 0
    for index, path in enumerate(paths, start=1):
        require(path.is_file(), f"captured frame is absent: {path}")
        with Image.open(path) as image:
            image.verify()
            width, height = image.size
        require(width > 0 and 0 < height <= 720, f"captured frame dimensions are invalid: {path.name}")
        size = path.stat().st_size
        total_bytes += size
        rows.append(
            {
                "sequence": index,
                "relativePath": f"frames/{path.name}",
                "widthPx": width,
                "heightPx": height,
                "byteLength": size,
                "sha256": sha256_file(path),
            }
        )
    require(total_bytes <= 1024 * 1024 * 1024, "bounded capture exceeded the 1 GiB hard limit")
    return rows


def render_contact_sheet(paths: Sequence[Path], output_path: Path, fps: float, maximum_tiles: int = 90) -> dict[str, Any]:
    require(bool(paths), "no frames are available for the contact sheet")
    require(10 <= maximum_tiles <= 120, "contact-sheet tile limit is outside 10..120")
    stride = max(1, math.ceil(len(paths) / maximum_tiles))
    selected = list(paths[::stride])[:maximum_tiles]
    columns = 6
    tile_width, image_height, label_height = 240, 135, 24
    rows = math.ceil(len(selected) / columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * (image_height + label_height)), (12, 18, 24))
    draw = ImageDraw.Draw(sheet)
    selections: list[dict[str, Any]] = []
    for tile_index, path in enumerate(selected):
        frame_index = paths.index(path)
        with Image.open(path) as source:
            thumb = source.convert("RGB")
            resampling = getattr(Image, "Resampling", Image)
            thumb.thumbnail((tile_width, image_height), resampling.LANCZOS)
        x = (tile_index % columns) * tile_width
        y = (tile_index // columns) * (image_height + label_height)
        sheet.paste(thumb, (x + (tile_width - thumb.width) // 2, y))
        seconds = frame_index / fps
        draw.text((x + 5, y + image_height + 4), f"#{frame_index + 1}  +{seconds:.1f}s", fill=(236, 241, 245))
        selections.append({"frameSequence": frame_index + 1, "secondsFromCaptureStart": seconds})
    sheet.save(output_path, format="JPEG", quality=88, optimize=True)
    return {
        "relativePath": output_path.name,
        "tileCount": len(selected),
        "sourceFrameStride": stride,
        "selections": selections,
        "byteLength": output_path.stat().st_size,
        "sha256": sha256_file(output_path),
    }


def capture(
    output: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    duration_seconds: int = 600,
    yt_dlp: str = "yt-dlp",
    ffmpeg: str = "ffmpeg",
    now_jst: datetime | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    output = output.resolve()
    require(not output.exists(), f"output already exists: {output}")
    started_at = (now_jst or datetime.now(TOKYO)).astimezone(TOKYO)
    fps = float(config["capture"]["framesPerSecond"])
    maximum_height = int(config["capture"]["maximumFrameHeightPx"])
    maximum_duration = int(config["capture"]["maximumCaptureSeconds"])
    require(duration_seconds <= maximum_duration, "capture duration exceeds config maximum")
    media_url = resolve_media_url(config["watchUrl"], yt_dlp, maximum_height)
    staging = output.parent / f".{output.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    frames_dir = staging / "frames"
    frames_dir.mkdir(parents=True, mode=0o700)
    try:
        command = ffmpeg_command(ffmpeg, media_url, frames_dir / "frame-%06d.jpg", duration_seconds, fps)
        completed = subprocess.run(command, capture_output=True, text=True, timeout=duration_seconds + 120, check=False)
        require(completed.returncode == 0, f"ffmpeg capture failed: {completed.stderr.strip()[-500:]}")
        frame_paths = sorted(frames_dir.glob("frame-*.jpg"))
        frames = inspect_frames(frame_paths)
        contact_sheet = render_contact_sheet(frame_paths, staging / "contact-sheet.jpg", fps)
        finished_at = datetime.now(TOKYO)
        report = {
            "schema": SCHEMA,
            "status": STATUS,
            "source": {
                "provider": config["provider"],
                "channelUrl": config["channelUrl"],
                "watchUrl": config["watchUrl"],
                "videoId": config["videoId"],
                "resolvedMediaUrlStored": False,
                "resolvedMediaUrlSha256": hashlib.sha256(media_url.encode("utf-8")).hexdigest(),
            },
            "capture": {
                "startedAtJst": started_at.isoformat(timespec="seconds"),
                "finishedAtJst": finished_at.isoformat(timespec="seconds"),
                "requestedDurationSeconds": duration_seconds,
                "framesPerSecond": fps,
                "frameCount": len(frames),
                "totalFrameBytes": sum(row["byteLength"] for row in frames),
                "frames": frames,
            },
            "review": {
                "contactSheet": contact_sheet,
                "purpose": "locate the 2k000 barrage interval before automatic target-view calibration",
            },
            "next": "identify the 2k000 barrage interval, retain its temporal sequence, and calibrate paired orange-lamp ROIs",
            "boundary": {
                "targetBarrageIntervalSelected": False,
                "gateStateInferred": False,
                "trainingLabelGenerated": False,
                "lampAbsenceInterpretedAsClosed": False,
                "hydraulicSolverExecuted": False,
                "published": False,
            },
        }
        (staging / "capture.json").write_bytes(canonical_bytes(report))
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, output)
        return report
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--yt-dlp", default="yt-dlp")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    report = capture(
        args.output,
        config_path=args.config,
        duration_seconds=args.duration_seconds,
        yt_dlp=args.yt_dlp,
        ffmpeg=args.ffmpeg,
    )
    print(json.dumps({"status": report["status"], "frameCount": report["capture"]["frameCount"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
