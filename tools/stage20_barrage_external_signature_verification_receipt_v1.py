from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_barrage_external_signature_verification_receipt_v1.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    if contract.get("status") != "EMPTY_TEMPLATE_PREPARE_ONLY_NO_EXTERNAL_VERIFIER":
        raise ValueError("signature receipt contract status changed")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        if not path.is_file() or sha256(path) != binding["sha256"]:
            raise ValueError(f"signature receipt binding mismatch: {binding['path']}")
    boundary = contract["decisionBoundary"]
    if boundary["trustedRegistryPresent"] or boundary["externalVerifierPresent"] or boundary["cryptographicVerificationPermitted"]:
        raise ValueError("unreviewed signature verification enabled")
    return contract


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return parsed if parsed is not None and parsed.utcoffset() is not None else None


def assess(receipt: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, Any]:
    document = contract or verified_contract()
    issues: list[str] = []
    if receipt.get("schema") != document["receiptSchema"]:
        issues.append("RECEIPT_SCHEMA_INVALID")
    if receipt.get("classification") not in {"empty_template", "candidate_untrusted"}:
        issues.append("RECEIPT_CLASSIFICATION_INVALID")
    missing = [field for field in document["requiredFields"] if receipt.get(field) is None]
    if missing:
        issues.append("REQUIRED_FIELDS_MISSING")
    sha_fields = [
        "registrySha256",
        "custodianKeyFingerprintSha256",
        "sourceManifestSha256",
        "sourceApprovalSha256",
        "signedPayloadSha256",
        "detachedSignatureSha256",
        "verifierExecutableSha256",
    ]
    for field in sha_fields:
        value = receipt.get(field)
        if value is not None and (not isinstance(value, str) or SHA256_RE.fullmatch(value) is None):
            issues.append(f"{field}_INVALID")
    if receipt.get("algorithm") is not None and receipt.get("algorithm") not in document["allowedAlgorithms"]:
        issues.append("SIGNATURE_ALGORITHM_INVALID")
    if receipt.get("verifiedAt") is not None and _timestamp(receipt.get("verifiedAt")) is None:
        issues.append("VERIFIED_AT_INVALID")
    if receipt.get("result") is not None and receipt.get("result") != "PASS_SIGNATURE_VALID":
        issues.append("VERIFICATION_RESULT_INVALID")
    if receipt.get("classification") == "candidate_untrusted":
        issues.append("CANDIDATE_RECEIPT_NOT_TRUSTED")
    return {
        "status": "BLOCKED_NO_TRUSTED_REGISTRY_OR_EXTERNAL_VERIFIER",
        "receiptSchemaPass": not [issue for issue in issues if issue != "CANDIDATE_RECEIPT_NOT_TRUSTED"],
        "cryptographicallyVerified": False,
        "physicalSourceAuthenticated": False,
        "issues": sorted(set(issues + ["TRUSTED_REGISTRY_MISSING", "EXTERNAL_VERIFIER_MISSING"])),
        "parameterFitPermitted": False,
        "solverRunPermitted": False,
        "yodaLaunchPermitted": False,
        "releasePermitted": False,
    }


if __name__ == "__main__":
    contract = verified_contract()
    print(json.dumps(assess(contract["template"], contract), indent=2, sort_keys=True))
