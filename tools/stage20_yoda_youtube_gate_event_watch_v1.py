#!/usr/bin/env python3
"""Run a bounded, release-triggered YouTube calibration watch on YODA.

The watcher reads the existing ten-minute official observation collection.  It
captures a short YouTube window only after a release increase or while release
remains elevated.  It never infers a per-gate state and never treats an absent
lamp as evidence that a gate is closed.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import stage20_youtube_barrage_live_capture_v1 as live_capture


TOKYO = ZoneInfo("Asia/Tokyo")
SCHEMA = "onga-stage20-yoda-youtube-gate-event-watch-v1"
RUNNING = "RUNNING_RELEASE_TRIGGERED_CAPTURE_NO_GATE_INFERENCE"
COMPLETE = "COMPLETE_RELEASE_TRIGGERED_CAPTURE_NO_GATE_INFERENCE"
FAILED = "FAILED_NO_RETRY"


class WatchError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WatchError(f"[stage20-yoda-youtube-gate-event-watch-v1] {message}")


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


def parse_jst(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise WatchError("[stage20-yoda-youtube-gate-event-watch-v1] invalid JST timestamp") from error
    require(parsed.utcoffset() == timedelta(hours=9), "timestamp must include +09:00")
    return parsed.astimezone(TOKYO)


def write_atomic(path: Path, value: dict[str, Any]) -> None:
    temporary = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    temporary.write_bytes(canonical_bytes(value))
    os.replace(temporary, path)


def read_official_observation(collection_root: Path) -> dict[str, Any]:
    latest_path = collection_root / "latest.json"
    require(latest_path.is_file(), f"latest pointer is absent: {latest_path}")
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    require(latest.get("status") == "COMPLETE_CAPTURE_NO_GATE_INFERENCE", "latest collection is incomplete")
    relative = latest.get("runRelativePath")
    require(isinstance(relative, str) and relative.startswith("runs/"), "latest run path is invalid")
    observation_path = collection_root / relative / "observation.json"
    require(observation_path.is_file(), "latest observation is absent")
    require(sha256_file(observation_path) == latest.get("observationSha256"), "latest observation SHA changed")
    observation = json.loads(observation_path.read_text(encoding="utf-8"))
    point = observation.get("parsed", {}).get("barragePoint", {})
    values = point.get("values", {})
    release = values.get("barrageReleaseM3S")
    inflow = values.get("barrageInflowM3S")
    require(isinstance(release, (int, float)) and not isinstance(release, bool), "official release is invalid")
    require(isinstance(inflow, (int, float)) and not isinstance(inflow, bool), "official inflow is invalid")
    require(0.0 <= float(release) <= 20_000.0, "official release is outside screening bounds")
    return {
        "runId": latest.get("runId"),
        "observationSha256": latest.get("observationSha256"),
        "observedAtJst": point.get("observedAt"),
        "barrageInflowM3S": float(inflow),
        "barrageReleaseM3S": float(release),
    }


def capture_decision(
    observation: dict[str, Any],
    state: dict[str, Any],
    now_jst: datetime,
    *,
    release_trigger_m3s: float,
    release_rise_trigger_m3s: float,
    minimum_seconds_between_attempts: int,
) -> tuple[bool, str]:
    release = float(observation["barrageReleaseM3S"])
    previous = state.get("lastObservedReleaseM3S")
    elevated = release >= release_trigger_m3s
    rising = isinstance(previous, (int, float)) and release - float(previous) >= release_rise_trigger_m3s
    if not elevated and not rising:
        return False, "release_below_trigger_without_large_rise"
    last_attempt = state.get("lastCaptureAttemptAtJst")
    if last_attempt is not None:
        elapsed = (now_jst - parse_jst(last_attempt)).total_seconds()
        if elapsed < minimum_seconds_between_attempts:
            return False, "capture_cooldown_active"
    return True, "release_at_or_above_trigger" if elevated else "release_rise_trigger"


def initial_state(
    *,
    started_at: datetime,
    end_at: datetime,
    collection_root: Path,
    output_root: Path,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": RUNNING,
        "startedAtJst": started_at.isoformat(timespec="seconds"),
        "endAtJst": end_at.isoformat(timespec="seconds"),
        "collectionRoot": str(collection_root.resolve()),
        "outputRoot": str(output_root.resolve()),
        "parameters": parameters,
        "lastObservation": None,
        "lastObservedReleaseM3S": None,
        "lastCaptureAttemptAtJst": None,
        "captureCount": 0,
        "captures": [],
        "error": None,
        "boundary": {
            "gateStateInferred": False,
            "trainingLabelGenerated": False,
            "lampAbsenceInterpretedAsClosed": False,
            "hydraulicSolverExecuted": False,
            "published": False,
        },
    }


def watch(args: argparse.Namespace, now_jst: datetime | None = None) -> dict[str, Any]:
    started_at = (now_jst or datetime.now(TOKYO)).astimezone(TOKYO)
    end_at = parse_jst(args.end_at_jst)
    require(started_at < end_at <= started_at + timedelta(hours=24), "watch end must be within the next 24 hours")
    require(30 <= args.poll_seconds <= 600, "poll interval must remain within 30..600 seconds")
    require(15 <= args.capture_duration_seconds <= 900, "capture duration must remain within 15..900 seconds")
    require(1 <= args.maximum_captures <= 24, "maximum captures must remain within 1..24")
    require(600 <= args.minimum_seconds_between_attempts <= 7200, "capture cooldown must remain within 600..7200 seconds")
    require(0.0 <= args.release_trigger_m3s <= 100.0, "release trigger is outside 0..100 m3/s")
    require(0.1 <= args.release_rise_trigger_m3s <= 20.0, "release-rise trigger is outside 0.1..20 m3/s")

    output_root = args.output.resolve()
    require(not output_root.exists(), f"fresh output is required: {output_root}")
    output_root.mkdir(parents=True, mode=0o700)
    lock_handle = (output_root / "watch.lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise WatchError("[stage20-yoda-youtube-gate-event-watch-v1] duplicate watcher") from error

    parameters = {
        "pollSeconds": args.poll_seconds,
        "captureDurationSeconds": args.capture_duration_seconds,
        "maximumCaptures": args.maximum_captures,
        "releaseTriggerM3S": args.release_trigger_m3s,
        "releaseRiseTriggerM3S": args.release_rise_trigger_m3s,
        "minimumSecondsBetweenAttempts": args.minimum_seconds_between_attempts,
    }
    state = initial_state(
        started_at=started_at,
        end_at=end_at,
        collection_root=args.collection_root,
        output_root=output_root,
        parameters=parameters,
    )
    state_path = output_root / "state.json"
    write_atomic(state_path, state)
    last_run_id: str | None = None
    try:
        while datetime.now(TOKYO) < end_at and state["captureCount"] < args.maximum_captures:
            observation = read_official_observation(args.collection_root)
            now = datetime.now(TOKYO)
            if observation["runId"] != last_run_id:
                should_capture, reason = capture_decision(
                    observation,
                    state,
                    now,
                    release_trigger_m3s=args.release_trigger_m3s,
                    release_rise_trigger_m3s=args.release_rise_trigger_m3s,
                    minimum_seconds_between_attempts=args.minimum_seconds_between_attempts,
                )
                state["lastObservation"] = observation
                if should_capture:
                    state["lastCaptureAttemptAtJst"] = now.isoformat(timespec="seconds")
                    write_atomic(state_path, state)
                    capture_id = now.strftime("%Y%m%dT%H%M%S%z")
                    capture_output = output_root / "captures" / capture_id
                    report = live_capture.capture(
                        capture_output,
                        duration_seconds=args.capture_duration_seconds,
                        yt_dlp=args.yt_dlp,
                        ffmpeg=args.ffmpeg,
                    )
                    state["captureCount"] += 1
                    state["captures"].append(
                        {
                            "captureId": capture_id,
                            "trigger": reason,
                            "officialObservation": observation,
                            "relativePath": f"captures/{capture_id}",
                            "captureJsonSha256": sha256_file(capture_output / "capture.json"),
                            "frameCount": report["capture"]["frameCount"],
                        }
                    )
                state["lastObservedReleaseM3S"] = observation["barrageReleaseM3S"]
                last_run_id = str(observation["runId"])
                write_atomic(state_path, state)
            remaining = (end_at - datetime.now(TOKYO)).total_seconds()
            if remaining > 0:
                time.sleep(min(args.poll_seconds, remaining))
        state["status"] = COMPLETE
        state["finishedAtJst"] = datetime.now(TOKYO).isoformat(timespec="seconds")
        write_atomic(state_path, state)
        return state
    except Exception as error:
        state["status"] = FAILED
        state["finishedAtJst"] = datetime.now(TOKYO).isoformat(timespec="seconds")
        state["error"] = {"type": type(error).__name__, "message": str(error)[:1000]}
        write_atomic(state_path, state)
        raise
    finally:
        lock_handle.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--end-at-jst", required=True)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--capture-duration-seconds", type=int, default=600)
    parser.add_argument("--maximum-captures", type=int, default=16)
    parser.add_argument("--release-trigger-m3s", type=float, default=1.0)
    parser.add_argument("--release-rise-trigger-m3s", type=float, default=0.5)
    parser.add_argument("--minimum-seconds-between-attempts", type=int, default=3600)
    parser.add_argument("--yt-dlp", required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    result = watch(args)
    print(json.dumps({"status": result["status"], "captureCount": result["captureCount"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
