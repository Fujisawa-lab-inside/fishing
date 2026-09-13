#!/usr/bin/env python3
"""Select and render a low-cost barrage-release transition review.

The review places two preserved camera frames and candidate A8..A1 crops next
to each other.  Official total barrage release is used only to find a useful
high/low comparison event.  Neither the release value nor the image difference
is treated as a per-gate opening label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


SCHEMA = "onga-stage20-gate-transition-review-v1"
STATUS = "PASS_TRANSITION_REVIEW_CANDIDATE_NOT_GATE_LABEL"
CAMERA_SOURCE_NAME = "barrageCamera"
POINT_NAME = "barragePoint"
EXPECTED_GATE_IDS = [f"A{index}" for index in range(8, 0, -1)]
DEFAULT_GATE_REGION = (130, 85, 610, 290)


class TransitionReviewError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TransitionReviewError(f"[stage20-gate-transition-review-v1] {message}")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_timestamp(value: Any, field: str) -> datetime:
    require(isinstance(value, str), f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise TransitionReviewError(f"[stage20-gate-transition-review-v1] {field} is invalid") from error
    require(parsed.utcoffset() is not None, f"{field} must include a UTC offset")
    return parsed


def image_quality(path: Path, crop: tuple[int, int, int, int] = DEFAULT_GATE_REGION) -> dict[str, float]:
    with Image.open(path) as source:
        rgb = np.asarray(source.convert("RGB"), dtype=np.float32)
    x0, y0, x1, y1 = crop
    require(0 <= x0 < x1 <= rgb.shape[1] and 0 <= y0 < y1 <= rgb.shape[0], "quality crop is outside image")
    region = rgb[y0:y1, x0:x1]
    luminance = 0.2126 * region[..., 0] + 0.7152 * region[..., 1] + 0.0722 * region[..., 2]
    horizontal = float(np.abs(np.diff(luminance, axis=1)).mean())
    vertical = float(np.abs(np.diff(luminance, axis=0)).mean())
    edge = (horizontal + vertical) / 2.0
    contrast = float(np.percentile(luminance, 95.0) - np.percentile(luminance, 5.0))
    brightness = float(luminance.mean())
    score = edge + min(contrast, 128.0) / 128.0 - abs(brightness - 128.0) / 20.0
    return {
        "edgeEnergy": edge,
        "p95MinusP5Contrast": contrast,
        "meanBrightness": brightness,
        "visibilityScore": score,
    }


def load_record(observation_path: Path) -> dict[str, Any]:
    try:
        document = json.loads(observation_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransitionReviewError(f"[stage20-gate-transition-review-v1] invalid observation: {observation_path}") from error
    run_id = document.get("runId")
    require(isinstance(run_id, str) and run_id, "runId is absent")
    camera = document.get("sources", {}).get(CAMERA_SOURCE_NAME, {})
    require(camera.get("status") == "FETCHED", f"camera was not fetched for {run_id}")
    relative_path = camera.get("relativePath")
    require(isinstance(relative_path, str) and relative_path, f"camera relativePath is absent for {run_id}")
    image_path = observation_path.parent / relative_path
    require(image_path.is_file(), f"camera image is absent for {run_id}")
    point = document.get("parsed", {}).get(POINT_NAME, {})
    values = point.get("values", {})
    release = values.get("barrageReleaseM3S")
    require(isinstance(release, (int, float)) and not isinstance(release, bool), f"release is absent for {run_id}")
    require(-5000.0 <= float(release) <= 50000.0, f"release is outside screening bounds for {run_id}")
    capture_at = parse_timestamp(document.get("captureStartedAtJst"), "captureStartedAtJst")
    observed_at = parse_timestamp(point.get("observedAt"), "barragePoint.observedAt")
    return {
        "runId": run_id,
        "observationPath": observation_path.resolve(),
        "imagePath": image_path.resolve(),
        "captureStartedAtJst": capture_at,
        "pointObservedAtJst": observed_at,
        "releaseM3S": float(release),
        "pointValues": values,
        "quality": image_quality(image_path),
    }


def discover_records(collection_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(collection_root.glob("runs/*/*/*/*/observation.json")):
        try:
            records.append(load_record(path))
        except TransitionReviewError:
            continue
    require(len(records) >= 2, "fewer than two complete camera/point observations are available")
    records.sort(key=lambda row: (row["pointObservedAtJst"], row["captureStartedAtJst"], row["runId"]))
    return records


def _best_quality(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    require(bool(records), "no quality candidate is available")
    return max(records, key=lambda row: (row["quality"]["visibilityScore"], row["captureStartedAtJst"]))


def select_transition_pair(
    records: Sequence[dict[str, Any]],
    *,
    minimum_release_delta_m3s: float = 20.0,
    maximum_adjacent_minutes: float = 30.0,
    plateau_minutes: float = 60.0,
) -> dict[str, Any]:
    require(minimum_release_delta_m3s > 0.0, "minimum release delta must be positive")
    ordered = sorted(records, key=lambda row: (row["pointObservedAtJst"], row["captureStartedAtJst"], row["runId"]))
    candidates: list[tuple[float, int, dict[str, Any], dict[str, Any]]] = []
    for index, (left, right) in enumerate(zip(ordered, ordered[1:])):
        elapsed = (right["pointObservedAtJst"] - left["pointObservedAtJst"]).total_seconds() / 60.0
        if elapsed <= 0.0 or elapsed > maximum_adjacent_minutes:
            continue
        delta = abs(right["releaseM3S"] - left["releaseM3S"])
        if delta >= minimum_release_delta_m3s:
            candidates.append((delta, -index, left, right))
    require(bool(candidates), "no qualifying adjacent release transition was found")
    _, _, before, after = max(candidates, key=lambda row: (row[0], row[1]))
    closing = before["releaseM3S"] > after["releaseM3S"]
    high_boundary = before if closing else after
    low_boundary = after if closing else before
    window = timedelta(minutes=plateau_minutes)
    high_floor = high_boundary["releaseM3S"] - max(5.0, 0.15 * abs(high_boundary["releaseM3S"]))
    low_ceiling = low_boundary["releaseM3S"] + max(1.0, 0.15 * abs(high_boundary["releaseM3S"] - low_boundary["releaseM3S"]))
    if closing:
        high_pool = [
            row for row in ordered
            if high_boundary["pointObservedAtJst"] - window <= row["pointObservedAtJst"] <= high_boundary["pointObservedAtJst"]
            and row["releaseM3S"] >= high_floor
        ]
        low_pool = [
            row for row in ordered
            if low_boundary["pointObservedAtJst"] <= row["pointObservedAtJst"] <= low_boundary["pointObservedAtJst"] + window
            and row["releaseM3S"] <= low_ceiling
        ]
    else:
        low_pool = [
            row for row in ordered
            if low_boundary["pointObservedAtJst"] - window <= row["pointObservedAtJst"] <= low_boundary["pointObservedAtJst"]
            and row["releaseM3S"] <= low_ceiling
        ]
        high_pool = [
            row for row in ordered
            if high_boundary["pointObservedAtJst"] <= row["pointObservedAtJst"] <= high_boundary["pointObservedAtJst"] + window
            and row["releaseM3S"] >= high_floor
        ]
    high = _best_quality(high_pool)
    low = _best_quality(low_pool)
    return {
        "transitionDirection": "release_drop" if closing else "release_rise",
        "boundaryBefore": before,
        "boundaryAfter": after,
        "high": high,
        "low": low,
        "releaseDeltaM3S": high["releaseM3S"] - low["releaseM3S"],
        "highCandidateCount": len(high_pool),
        "lowCandidateCount": len(low_pool),
        "_highPool": high_pool,
        "_lowPool": low_pool,
    }


def select_explicit_pair(records: Sequence[dict[str, Any]], high_run_id: str, low_run_id: str) -> dict[str, Any]:
    by_id = {row["runId"]: row for row in records}
    require(high_run_id in by_id, f"high run is absent: {high_run_id}")
    require(low_run_id in by_id, f"low run is absent: {low_run_id}")
    high = by_id[high_run_id]
    low = by_id[low_run_id]
    require(high["releaseM3S"] > low["releaseM3S"], "explicit high release must exceed explicit low release")
    high_floor = high["releaseM3S"] - max(5.0, 0.15 * abs(high["releaseM3S"]))
    low_ceiling = low["releaseM3S"] + max(1.0, 0.15 * abs(high["releaseM3S"] - low["releaseM3S"]))
    window = timedelta(minutes=60.0)
    high_pool = [
        row for row in records
        if abs(row["pointObservedAtJst"] - high["pointObservedAtJst"]) <= window
        and row["releaseM3S"] >= high_floor
    ]
    low_pool = [
        row for row in records
        if abs(row["pointObservedAtJst"] - low["pointObservedAtJst"]) <= window
        and row["releaseM3S"] <= low_ceiling
    ]
    return {
        "transitionDirection": "explicit_high_low_review",
        "boundaryBefore": None,
        "boundaryAfter": None,
        "high": high,
        "low": low,
        "releaseDeltaM3S": high["releaseM3S"] - low["releaseM3S"],
        "highCandidateCount": len(high_pool),
        "lowCandidateCount": len(low_pool),
        "_highPool": high_pool,
        "_lowPool": low_pool,
    }


def load_rois(path: Path, image_size: tuple[int, int]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransitionReviewError(f"[stage20-gate-transition-review-v1] invalid ROI config: {path}") from error
    require(config.get("status") == "CANDIDATE_REQUIRES_HUMAN_CONFIRMATION", "ROI status must remain candidate")
    require(config.get("cameraImageSizePx") == list(image_size), "ROI image size does not match camera frame")
    rois = config.get("candidateRoisNearToFar")
    require(isinstance(rois, list), "candidate ROI list is absent")
    require([row.get("gateId") for row in rois] == EXPECTED_GATE_IDS, "candidate ROI order must be A8 through A1")
    width, height = image_size
    for row in rois:
        bbox = row.get("bboxPx")
        require(isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(value, int) for value in bbox), f"invalid ROI for {row.get('gateId')}")
        x0, y0, x1, y1 = bbox
        require(0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, f"ROI outside camera frame for {row.get('gateId')}")
    boundary = config.get("boundary", {})
    require(boundary.get("gateStateInferred") is False, "ROI config must not infer gate state")
    require(boundary.get("trainingLabelGenerated") is False, "ROI config must not generate training labels")
    return config, rois


def _font(size: int) -> ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _contain(image: Image.Image, size: tuple[int, int], background: tuple[int, int, int]) -> Image.Image:
    return ImageOps.pad(image.convert("RGB"), size, method=Image.Resampling.BICUBIC, color=background, centering=(0.5, 0.5))


def render_review(high: dict[str, Any], low: dict[str, Any], rois: Sequence[dict[str, Any]], output_path: Path) -> None:
    with Image.open(high["imagePath"]) as source:
        high_image = source.convert("RGB")
    with Image.open(low["imagePath"]) as source:
        low_image = source.convert("RGB")
    require(high_image.size == low_image.size, "high and low camera frame sizes differ")

    canvas_width = 1560
    header_height = 100
    full_width, full_height = 740, 555
    card_width, card_height = 370, 245
    gap = 20
    canvas_height = header_height + full_height + gap + 2 * (card_height + gap) + 30
    background = (15, 24, 31)
    canvas = Image.new("RGB", (canvas_width, canvas_height), background)
    draw = ImageDraw.Draw(canvas)
    title_font = _font(28)
    label_font = _font(22)
    small_font = _font(16)
    tiny_font = _font(14)
    draw.text((24, 18), "ONGA BARRAGE RELEASE TRANSITION / CANDIDATE GATE ROIs", fill=(242, 247, 250), font=title_font)
    draw.text((24, 58), "PAIRED LAMPS ARE POSITIVE-ONLY CUES; ABSENCE MEANS UNKNOWN, NOT CLOSED", fill=(255, 196, 95), font=small_font)

    full_display_size = (full_width, full_height - 48)
    colors = [(255, 98, 85), (255, 166, 68), (255, 218, 82), (138, 224, 101), (73, 211, 191), (64, 177, 255), (131, 133, 255), (221, 108, 255)]
    for column, (kind, record, source) in enumerate((("HIGH", high, high_image), ("LOW", low, low_image))):
        left = 20 + column * (full_width + gap)
        top = header_height
        label = (
            f"{kind}  Q={record['releaseM3S']:.1f} m3/s  official {record['pointObservedAtJst'].strftime('%H:%M')}"
            f"  capture {record['captureStartedAtJst'].strftime('%H:%M')}"
        )
        draw.text((left, top), label, fill=(240, 244, 247), font=small_font)
        displayed = source.resize(full_display_size, Image.Resampling.BICUBIC)
        overlay = ImageDraw.Draw(displayed)
        scale_x = full_display_size[0] / source.width
        scale_y = full_display_size[1] / source.height
        for color, roi in zip(colors, rois):
            x0, y0, x1, y1 = roi["bboxPx"]
            scaled = (round(x0 * scale_x), round(y0 * scale_y), round(x1 * scale_x), round(y1 * scale_y))
            overlay.rectangle(scaled, outline=color, width=3)
            overlay.rectangle((scaled[0], scaled[1], scaled[0] + 39, scaled[1] + 24), fill=color)
            overlay.text((scaled[0] + 3, scaled[1] + 1), roi["gateId"], fill=(8, 12, 16), font=tiny_font)
        canvas.paste(displayed, (left, top + 38))

    cards_top = header_height + full_height + gap
    crop_size = (166, 170)
    for index, (color, roi) in enumerate(zip(colors, rois)):
        row, column = divmod(index, 4)
        left = 20 + column * (card_width + gap)
        top = cards_top + row * (card_height + gap)
        draw.rounded_rectangle((left, top, left + card_width, top + card_height), radius=12, fill=(25, 36, 45), outline=color, width=2)
        draw.text((left + 12, top + 10), f"{roi['gateId']} candidate span / raw crop enlarged", fill=color, font=label_font)
        high_crop = _contain(high_image.crop(tuple(roi["bboxPx"])), crop_size, background)
        low_crop = _contain(low_image.crop(tuple(roi["bboxPx"])), crop_size, background)
        canvas.paste(high_crop, (left + 12, top + 48))
        canvas.paste(low_crop, (left + 192, top + 48))
        draw.text((left + 12, top + 220), f"HIGH {high['releaseM3S']:.1f}", fill=(240, 244, 247), font=tiny_font)
        draw.text((left + 192, top + 220), f"LOW {low['releaseM3S']:.1f}", fill=(240, 244, 247), font=tiny_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    canvas.save(temporary, format="PNG", optimize=True)
    os.replace(temporary, output_path)


def _bounded_sequence(records: Sequence[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    ordered = sorted(records, key=lambda row: (row["pointObservedAtJst"], row["captureStartedAtJst"], row["runId"]))
    if len(ordered) <= limit:
        return ordered
    indexes = np.linspace(0, len(ordered) - 1, num=limit, dtype=int)
    return [ordered[int(index)] for index in indexes]


def render_lamp_sequence_review(
    high_records: Sequence[dict[str, Any]],
    low_records: Sequence[dict[str, Any]],
    rois: Sequence[dict[str, Any]],
    output_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Render time sequences so intermittent paired end-lamps can be located."""
    displayed_high = _bounded_sequence(high_records)
    displayed_low = _bounded_sequence(low_records)
    require(bool(displayed_high) and bool(displayed_low), "lamp sequence needs high and low evidence frames")
    columns = 4
    thumb_size = (365, 166)
    card_height = 205
    gap = 14
    header_height = 100
    section_label_height = 36
    high_rows = (len(displayed_high) + columns - 1) // columns
    low_rows = (len(displayed_low) + columns - 1) // columns
    canvas_width = 4 * thumb_size[0] + 5 * gap
    canvas_height = header_height + 2 * section_label_height + (high_rows + low_rows) * (card_height + gap) + 20
    background = (15, 24, 31)
    canvas = Image.new("RGB", (canvas_width, canvas_height), background)
    draw = ImageDraw.Draw(canvas)
    title_font = _font(27)
    label_font = _font(17)
    tiny_font = _font(13)
    draw.text((20, 16), "ROTATING-LAMP CUE REVIEW / HIGH AND LOW RELEASE SEQUENCES", fill=(242, 247, 250), font=title_font)
    draw.text((20, 57), "Paired lamps support OPEN; an unlit 10-minute frame means UNKNOWN, never CLOSED", fill=(255, 196, 95), font=label_font)
    colors = [(255, 98, 85), (255, 166, 68), (255, 218, 82), (138, 224, 101), (73, 211, 191), (64, 177, 255), (131, 133, 255), (221, 108, 255)]
    source_crop = (100, 72, 620, 309)

    def section(records: Sequence[dict[str, Any]], title: str, top: int) -> int:
        draw.text((20, top), title, fill=(232, 238, 242), font=label_font)
        top += section_label_height
        for index, record in enumerate(records):
            row, column = divmod(index, columns)
            left = gap + column * (thumb_size[0] + gap)
            card_top = top + row * (card_height + gap)
            with Image.open(record["imagePath"]) as source:
                source_rgb = source.convert("RGB")
            crop = source_rgb.crop(source_crop).resize(thumb_size, Image.Resampling.BICUBIC)
            overlay = ImageDraw.Draw(crop)
            scale_x = thumb_size[0] / (source_crop[2] - source_crop[0])
            scale_y = thumb_size[1] / (source_crop[3] - source_crop[1])
            for color, roi in zip(colors, rois):
                x0, y0, x1, y1 = roi["bboxPx"]
                box = (
                    round((x0 - source_crop[0]) * scale_x),
                    round((y0 - source_crop[1]) * scale_y),
                    round((x1 - source_crop[0]) * scale_x),
                    round((y1 - source_crop[1]) * scale_y),
                )
                overlay.rectangle(box, outline=color, width=2)
            canvas.paste(crop, (left, card_top))
            label = f"{record['pointObservedAtJst'].strftime('%H:%M')}  Q={record['releaseM3S']:.1f}  {record['runId']}"
            draw.text((left, card_top + thumb_size[1] + 5), label, fill=(225, 232, 237), font=tiny_font)
        return top + ((len(records) + columns - 1) // columns) * (card_height + gap)

    next_top = section(displayed_high, f"HIGH RELEASE SEQUENCE ({len(high_records)} available; {len(displayed_high)} shown)", header_height)
    section(displayed_low, f"LOW RELEASE SEQUENCE ({len(low_records)} available; {len(displayed_low)} shown)", next_top)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    canvas.save(temporary, format="PNG", optimize=True)
    os.replace(temporary, output_path)
    return displayed_high, displayed_low


def render_per_gate_lamp_review(
    high_records: Sequence[dict[str, Any]],
    low_records: Sequence[dict[str, Any]],
    rois: Sequence[dict[str, Any]],
    output_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Render enlarged per-gate time strips for paired lamp inspection."""
    displayed_high = _bounded_sequence(high_records)
    displayed_low = _bounded_sequence(low_records)
    require(bool(displayed_high) and bool(displayed_low), "per-gate lamp review needs high and low frames")
    all_records = displayed_high + displayed_low
    cell_width, cell_height = 98, 132
    label_width = 155
    gap = 7
    header_height = 112
    row_height = 180
    canvas_width = label_width + len(all_records) * (cell_width + gap) + gap
    canvas_height = header_height + len(rois) * row_height + 20
    background = (15, 24, 31)
    canvas = Image.new("RGB", (canvas_width, canvas_height), background)
    draw = ImageDraw.Draw(canvas)
    title_font = _font(27)
    label_font = _font(18)
    tiny_font = _font(12)
    draw.text((18, 14), "PER-GATE ORANGE ROTATING-LAMP REVIEW / ENLARGED RAW CROPS", fill=(242, 247, 250), font=title_font)
    draw.text((18, 52), "HIGH first, LOW after blue divider; paired ORANGE lamps are positive-only evidence", fill=(255, 196, 95), font=label_font)
    draw.text((18, 80), "No visible lamp means UNKNOWN, not CLOSED; no inferred state or training label", fill=(190, 203, 212), font=label_font)
    low_start_x = label_width + len(displayed_high) * (cell_width + gap)
    draw.line((low_start_x - 3, header_height - 8, low_start_x - 3, canvas_height - 16), fill=(68, 176, 255), width=4)

    loaded: dict[str, Image.Image] = {}
    for record in all_records:
        with Image.open(record["imagePath"]) as source:
            loaded[record["runId"]] = source.convert("RGB")

    for row_index, roi in enumerate(rois):
        top = header_height + row_index * row_height
        draw.text((18, top + 48), roi["gateId"], fill=(240, 244, 247), font=title_font)
        draw.text((18, top + 82), "candidate span", fill=(164, 181, 191), font=tiny_font)
        for column, record in enumerate(all_records):
            left = label_width + column * (cell_width + gap)
            crop = loaded[record["runId"]].crop(tuple(roi["bboxPx"]))
            enlarged = _contain(crop, (cell_width, cell_height), background)
            canvas.paste(enlarged, (left, top))
            kind_color = (255, 135, 92) if column < len(displayed_high) else (88, 184, 255)
            draw.rectangle((left, top, left + cell_width, top + cell_height), outline=kind_color, width=2)
            draw.text((left + 2, top + cell_height + 3), record["pointObservedAtJst"].strftime("%H:%M"), fill=kind_color, font=tiny_font)
            draw.text((left + 2, top + cell_height + 20), f"Q{record['releaseM3S']:.1f}", fill=(202, 212, 219), font=tiny_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    canvas.save(temporary, format="PNG", optimize=True)
    os.replace(temporary, output_path)
    return displayed_high, displayed_low


def _record_for_report(record: dict[str, Any]) -> dict[str, Any]:
    image_path = Path(record["imagePath"])
    observation_path = Path(record["observationPath"])
    return {
        "runId": record["runId"],
        "captureStartedAtJst": record["captureStartedAtJst"].isoformat(timespec="seconds"),
        "pointObservedAtJst": record["pointObservedAtJst"].isoformat(timespec="minutes"),
        "barrageReleaseM3S": record["releaseM3S"],
        "officialPointValues": record["pointValues"],
        "quality": record["quality"],
        "cameraImage": {
            "path": str(image_path),
            "byteLength": image_path.stat().st_size,
            "sha256": sha256_file(image_path),
        },
        "observation": {
            "path": str(observation_path),
            "byteLength": observation_path.stat().st_size,
            "sha256": sha256_file(observation_path),
        },
    }


def generate_review(
    collection_root: Path,
    roi_config_path: Path,
    output_root: Path,
    *,
    high_run_id: str | None = None,
    low_run_id: str | None = None,
) -> dict[str, Any]:
    require(not output_root.exists(), f"output root already exists: {output_root}")
    require((high_run_id is None) == (low_run_id is None), "high and low run IDs must be provided together")
    records = discover_records(collection_root)
    pair = (
        select_explicit_pair(records, high_run_id, low_run_id)
        if high_run_id is not None and low_run_id is not None
        else select_transition_pair(records)
    )
    with Image.open(pair["high"]["imagePath"]) as image:
        image_size = image.size
    roi_config, rois = load_rois(roi_config_path, image_size)
    output_root.mkdir(parents=True, mode=0o700)
    review_path = output_root / "gate-transition-review.png"
    lamp_sequence_path = output_root / "rotating-lamp-sequence-review.png"
    per_gate_lamp_path = output_root / "per-gate-rotating-lamp-review.png"
    report_path = output_root / "report.json"
    render_review(pair["high"], pair["low"], rois, review_path)
    displayed_high, displayed_low = render_lamp_sequence_review(pair["_highPool"], pair["_lowPool"], rois, lamp_sequence_path)
    per_gate_high, per_gate_low = render_per_gate_lamp_review(pair["_highPool"], pair["_lowPool"], rois, per_gate_lamp_path)
    require(
        [row["runId"] for row in per_gate_high] == [row["runId"] for row in displayed_high]
        and [row["runId"] for row in per_gate_low] == [row["runId"] for row in displayed_low],
        "lamp review frame selections diverged",
    )
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "selectionMode": "explicit" if high_run_id is not None else "automatic_largest_adjacent_release_transition_then_best_visibility",
        "transitionDirection": pair["transitionDirection"],
        "releaseDeltaM3S": pair["releaseDeltaM3S"],
        "highCandidateCount": pair["highCandidateCount"],
        "lowCandidateCount": pair["lowCandidateCount"],
        "high": _record_for_report(pair["high"]),
        "low": _record_for_report(pair["low"]),
        "roiConfig": {
            "path": str(roi_config_path.resolve()),
            "byteLength": roi_config_path.stat().st_size,
            "sha256": sha256_file(roi_config_path),
            "status": roi_config["status"],
            "nearToFar": [row["gateId"] for row in rois],
            "fieldObservedStateCue": roi_config.get("fieldObservedStateCue"),
        },
        "reviewImage": {
            "path": str(review_path.resolve()),
            "byteLength": review_path.stat().st_size,
            "sha256": sha256_file(review_path),
        },
        "rotatingLampSequenceReview": {
            "path": str(lamp_sequence_path.resolve()),
            "byteLength": lamp_sequence_path.stat().st_size,
            "sha256": sha256_file(lamp_sequence_path),
            "highAvailableFrameCount": len(pair["_highPool"]),
            "lowAvailableFrameCount": len(pair["_lowPool"]),
            "highDisplayedRunIds": [row["runId"] for row in displayed_high],
            "lowDisplayedRunIds": [row["runId"] for row in displayed_low],
            "interpretation": "human cue-location review only; paired rotating lamps are not yet mapped to pixels or converted into gate labels",
        },
        "perGateRotatingLampReview": {
            "path": str(per_gate_lamp_path.resolve()),
            "byteLength": per_gate_lamp_path.stat().st_size,
            "sha256": sha256_file(per_gate_lamp_path),
            "gateOrderNearToFar": [row["gateId"] for row in rois],
            "interpretation": "enlarged raw crops only; inspect both ends across time before defining lamp coordinates",
        },
        "boundary": {
            "rawImagesModified": False,
            "perGateStateInferred": False,
            "trainingLabelGenerated": False,
            "totalReleaseAssignedToIndividualGates": False,
            "candidateRoisRequireHumanConfirmation": True,
            "rotatingLampCoordinatesConfirmed": False,
            "lampAbsenceInterpretedAsClosed": False,
            "reviewImageIsVisualAidOnly": True,
            "modelFitPerformed": False,
        },
    }
    temporary = report_path.with_name(f".{report_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(canonical_bytes(report))
    os.replace(temporary, report_path)
    report["reportPath"] = str(report_path.resolve())
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-root", type=Path, required=True)
    parser.add_argument("--roi-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--high-run-id")
    parser.add_argument("--low-run-id")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = generate_review(
            args.collection_root.resolve(),
            args.roi_config.resolve(),
            args.output.resolve(),
            high_run_id=args.high_run_id,
            low_run_id=args.low_run_id,
        )
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "FAILED_NO_GATE_LABEL", "errorType": type(error).__name__, "message": str(error)}, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
