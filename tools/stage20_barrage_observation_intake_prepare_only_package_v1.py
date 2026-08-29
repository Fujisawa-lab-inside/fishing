from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_barrage_observation_intake_prepare_only_package_v1.json"


def validate_package() -> dict[str, object]:
    package = json.loads(CONTRACT.read_text())
    if package.get("status") != "PREPARE_ONLY_STATIC_OBSERVATION_INTAKE_NO_FIT_NO_SOLVER":
        raise ValueError("package is not PREPARE_ONLY")

    bindings = package.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("bindings missing")

    verified: list[str] = []
    for binding in bindings:
        path = ROOT / binding["path"]
        if not path.is_file():
            raise ValueError(f"binding missing: {binding['path']}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != binding["sha256"]:
            raise ValueError(f"binding SHA mismatch: {binding['path']}")
        verified.append(binding["role"])

    boundary = package["decisionBoundary"]
    forbidden = [key for key, value in boundary.items() if key != "staticValidationPermitted" and value]
    if forbidden:
        raise ValueError(f"forbidden authority enabled: {forbidden}")

    gate = package["intakeGate"]
    if gate["syntheticFixtureMayAuthorizePhysics"] or gate["publicSummaryMaySubstituteGateTelemetry"]:
        raise ValueError("unsafe observation substitution enabled")

    return {
        "status": "PASS_PREPARE_ONLY_STATIC_CLOSURE",
        "bindingCount": len(bindings),
        "allBindingsVerified": len(verified) == len(bindings),
        "parameterFitCount": 0,
        "solverRunCount": 0,
        "yodaConnectionCount": 0,
        "packageTransferCount": 0,
        "releaseAuthorized": False,
    }


if __name__ == "__main__":
    print(json.dumps(validate_package(), indent=2, sort_keys=True))
