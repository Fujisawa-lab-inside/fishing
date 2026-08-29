#!/usr/bin/env python3
"""Fail-closed validator for time-aligned barrage gate-physics observations."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_barrage_gate_physics_observation_pack_v1.json"
OUTPUT = ROOT / "docs/results/stage20-barrage-gate-physics-observation-pack-v1/static-validation.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_STATES = {"stable", "opening", "closing"}
REQUIRED_UNITS = {
    "upstreamLevelM": "m",
    "downstreamLevelM": "m",
    "totalReleaseM3S": "m3/s",
    "mainGateOpeningFractionById1To8": "fraction",
    "microAdjustmentGateOpeningFraction": "fraction",
}


class ObservationPackError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ObservationPackError(f"[stage20-barrage-gate-physics-observation-pack-v1] {message}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    require(contract.get("schema") == "onga-stage20-barrage-gate-physics-observation-pack-contract-v1", "schema changed")
    require(contract.get("status") == "EMPTY_TEMPLATE_READY_VALIDATOR_ONLY_NO_PHYSICAL_OBSERVATIONS", "status changed")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        require(path.is_file(), f"bound evidence absent: {path}")
        require(sha256(path) == binding["sha256"], f"bound evidence changed: {path}")
    boundary = contract["decisionBoundary"]
    require(boundary["schemaAndValidatorPermitted"] is True, "validator disabled")
    for key, value in boundary.items():
        if key != "schemaAndValidatorPermitted":
            require(value is False, f"forbidden boundary enabled: {key}")
    return contract


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def validate_pack(pack: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if pack.get("schema") != contract["packSchema"]:
        issues.append("PACK_SCHEMA_MISMATCH")
    if pack.get("classification") not in {"physical_observation", "synthetic_fixture"}:
        issues.append("CLASSIFICATION_INVALID")
    dataset = pack.get("dataset")
    if not isinstance(dataset, dict):
        return issues + ["DATASET_MISSING"]
    datum = dataset.get("verticalDatumName")
    if not isinstance(datum, str) or not datum.strip():
        issues.append("VERTICAL_DATUM_MISSING")
    if not isinstance(dataset.get("clockSource"), str) or not dataset["clockSource"].strip():
        issues.append("CLOCK_SOURCE_MISSING")
    if not isinstance(dataset.get("sourceSha256"), str) or SHA256_RE.fullmatch(dataset["sourceSha256"]) is None:
        issues.append("SOURCE_SHA256_INVALID")
    expected_source_class = {
        "physical_observation": "instrument_export",
        "synthetic_fixture": "synthetic_fixture",
    }.get(pack.get("classification"))
    if dataset.get("sourceClass") != expected_source_class:
        issues.append("SOURCE_CLASS_CLASSIFICATION_MISMATCH")
    if not isinstance(dataset.get("sourceManifestSha256"), str) or SHA256_RE.fullmatch(dataset["sourceManifestSha256"]) is None:
        issues.append("SOURCE_MANIFEST_SHA256_INVALID")
    instrument_ids = dataset.get("instrumentIds")
    if not isinstance(instrument_ids, list) or not instrument_ids or any(not isinstance(value, str) or not value.strip() for value in instrument_ids) or len(set(instrument_ids)) != len(instrument_ids):
        issues.append("INSTRUMENT_IDS_INVALID")
    if dataset.get("units") != REQUIRED_UNITS:
        issues.append("UNITS_INVALID")
    if dataset.get("wholeEventSplit") is not True:
        issues.append("WHOLE_EVENT_SPLIT_REQUIRED")
    if dataset.get("splitFrozenBeforeCalibration") is not True:
        issues.append("SPLIT_NOT_FROZEN")
    if not isinstance(dataset.get("saltIntrusionOrAdverseVolumeCriterion"), str) or not dataset["saltIntrusionOrAdverseVolumeCriterion"].strip():
        issues.append("ADVERSE_CRITERION_MISSING")

    rows = pack.get("rows")
    if not isinstance(rows, list) or not rows:
        return issues + ["OBSERVATION_ROWS_MISSING"]
    timestamps: set[str] = set()
    event_roles: dict[str, set[str]] = {}
    event_cells: dict[tuple[str, str], set[str]] = {}
    operating_states: set[str] = set()
    required_states = set(contract["requiredOperatingStates"])
    required_roles = set(contract["requiredSplitRoles"])
    for index, row in enumerate(rows):
        prefix = f"ROW_{index}"
        if not isinstance(row, dict):
            issues.append(f"{prefix}_INVALID")
            continue
        timestamp = row.get("timestampJst")
        try:
            parsed = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else None
        except ValueError:
            parsed = None
        if parsed is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 9 * 3600:
            issues.append(f"{prefix}_TIMESTAMP_INVALID")
        elif timestamp in timestamps:
            issues.append("DUPLICATE_TIMESTAMP")
        else:
            timestamps.add(timestamp)
        event_id = row.get("eventId")
        split_role = row.get("splitRole")
        if not isinstance(event_id, str) or not event_id:
            issues.append(f"{prefix}_EVENT_ID_INVALID")
        elif split_role not in required_roles:
            issues.append(f"{prefix}_SPLIT_ROLE_INVALID")
        else:
            event_roles.setdefault(event_id, set()).add(split_role)
        state = row.get("operatingState")
        if state not in required_states:
            issues.append(f"{prefix}_OPERATING_STATE_INVALID")
        else:
            operating_states.add(state)
            if isinstance(event_id, str) and event_id and split_role in required_roles:
                event_cells.setdefault((state, split_role), set()).add(event_id)
        for field in ("upstreamLevelM", "downstreamLevelM", "totalReleaseM3S"):
            if not _finite(row.get(field)):
                issues.append(f"{prefix}_{field}_INVALID")
        if row.get("verticalDatumName") != datum:
            issues.append(f"{prefix}_DATUM_MISMATCH")
        openings = row.get("mainGateOpeningFractionById1To8")
        if not isinstance(openings, list) or len(openings) != 8 or any(not _finite(value) or not 0.0 <= float(value) <= 1.0 for value in openings):
            issues.append(f"{prefix}_MAIN_GATE_OPENINGS_INVALID")
        micro = row.get("microAdjustmentGate")
        if not isinstance(micro, dict) or micro.get("state") not in {"closed", "open", "modulating"} or not _finite(micro.get("openingFraction")) or not 0.0 <= float(micro.get("openingFraction", -1)) <= 1.0:
            issues.append(f"{prefix}_MICRO_GATE_INVALID")
        if row.get("actuatorState") not in ALLOWED_STATES:
            issues.append(f"{prefix}_ACTUATOR_STATE_INVALID")
        if row.get("releaseSourceClass") != "direct_observation":
            issues.append(f"{prefix}_RELEASE_NOT_DIRECT_OBSERVATION")
    if len(event_roles) < contract["qualityContract"]["minimumDistinctEvents"]:
        issues.append("DISTINCT_EVENT_COUNT_INSUFFICIENT")
    minimum_per_cell = contract["qualityContract"]["minimumIndependentEventsPerStatePerSplit"]
    for state in sorted(required_states):
        for role in sorted(required_roles):
            if len(event_cells.get((state, role), set())) < minimum_per_cell:
                issues.append(f"EVENT_CELL_COUNT_INSUFFICIENT_{state}_{role}")
    if set().union(*event_roles.values()) != required_roles if event_roles else True:
        issues.append("CALIBRATION_VALIDATION_SPLITS_INCOMPLETE")
    if any(len(roles) != 1 for roles in event_roles.values()):
        issues.append("EVENT_SPLIT_LEAKAGE")
    if operating_states != required_states:
        issues.append("OPERATING_STATE_COVERAGE_INCOMPLETE")
    return sorted(set(issues))


def assess(pack: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, Any]:
    document = contract or verified_contract()
    issues = validate_pack(pack, document)
    structural_pass = not issues
    physical_ready = structural_pass and pack.get("classification") == "physical_observation"
    return {
        "schema": "onga-stage20-barrage-gate-physics-observation-pack-v1-assessment",
        "status": "READY_FOR_PARAMETER_CALIBRATION_DESIGN_NOT_SOLVER_RUN" if physical_ready else "BLOCKED_OBSERVATION_PACK_INCOMPLETE_OR_NONPHYSICAL",
        "structuralPass": structural_pass,
        "physicalObservationReady": physical_ready,
        "issues": issues,
        "parameterCalibrationPermitted": False,
        "solverRunPermitted": False,
        "yodaLaunchPermitted": False,
        "forecastAuthorized": False,
        "guiIntegrationAuthorized": False,
        "releaseAuthorized": False,
    }


def main() -> None:
    contract = verified_contract()
    result = assess(contract["template"], contract)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "issueCount": len(result["issues"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
