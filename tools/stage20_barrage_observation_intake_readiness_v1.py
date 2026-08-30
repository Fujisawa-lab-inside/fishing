from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_barrage_observation_intake_readiness_v1.json"
OUTPUT = ROOT / "docs/results/stage20-barrage-observation-intake-readiness-v1/report.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    if contract.get("status") != "PREPARE_ONLY_AGGREGATED_READINESS_NO_PHYSICAL_INPUT":
        raise ValueError("observation intake readiness status changed")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        if not path.is_file() or sha256(path) != binding["sha256"]:
            raise ValueError(f"observation intake readiness binding mismatch: {binding['path']}")
    boundary = contract["decisionBoundary"]
    for key, value in boundary.items():
        if key != "readinessAuditPermitted" and value:
            raise ValueError(f"unreviewed intake authority enabled: {key}")
    return contract


def assess() -> dict[str, Any]:
    contract = verified_contract()
    physical = json.loads((ROOT / "docs/results/stage20-barrage-physical-validation-readiness-v1/assessment.json").read_text())
    registry = json.loads((ROOT / "config/stage20_barrage_trusted_custodian_registry_v1.json").read_text())
    verifier = json.loads((ROOT / "config/stage20_barrage_external_verifier_activation_requirements_v1.json").read_text())
    receipt = json.loads((ROOT / "config/stage20_barrage_external_signature_verification_receipt_v1.json").read_text())
    gates = [
        {"id":"G0_schema_and_static_closure","pass":True,"reason":"tracked validators and PREPARE_ONLY contracts are present"},
        {"id":"G1_physical_observation_pack","pass":False,"reason":"no authenticated physical observation rows"},
        {"id":"G2_source_manifest_chain","pass":False,"reason":"no physical source manifest and custodian approval chain"},
        {"id":"G3_trusted_custodian_registry","pass":registry["decisionBoundary"]["trustedCustodianCount"] > 0,"reason":"trusted custodian count is zero"},
        {"id":"G4_external_verifier_activation","pass":verifier["decisionBoundary"]["activationPresent"],"reason":"external verifier activation is absent"},
        {"id":"G5_signature_verification_receipt","pass":receipt["decisionBoundary"]["cryptographicVerificationPermitted"],"reason":"no trusted cryptographic verification receipt"},
        {"id":"G6_physical_evidence_readiness","pass":physical["physicalValidationEvidenceReady"],"reason":f"{physical['passedCheckCount']}/{physical['requiredCheckCount']} physical checks pass"},
        {"id":"G7_offline_calibration_authority","pass":False,"reason":"no separately authorized frozen physical dataset"},
    ]
    if [gate["id"] for gate in gates] != contract["requiredGateOrder"]:
        raise ValueError("observation intake gate order changed")
    first_blocking = next(gate["id"] for gate in gates if not gate["pass"])
    return {
        "schema": "onga-stage20-barrage-observation-intake-readiness-v1-report",
        "status": "BLOCKED_BEFORE_PHYSICAL_OBSERVATION_INTAKE",
        "passedGateCount": sum(bool(gate["pass"]) for gate in gates),
        "requiredGateCount": len(gates),
        "firstBlockingGate": first_blocking,
        "gates": gates,
        "physicalReadinessPassedChecks": physical["passedCheckCount"],
        "physicalReadinessRequiredChecks": physical["requiredCheckCount"],
        "offlineCalibrationPermitted": False,
        "parameterFitPermitted": False,
        "solverRunPermitted": False,
        "yodaLaunchPermitted": False,
        "releasePermitted": False,
    }
if __name__ == "__main__":
    report = assess()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "passed": report["passedGateCount"], "required": report["requiredGateCount"]}))
