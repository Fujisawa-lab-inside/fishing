from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_barrage_trusted_custodian_registry_v1.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    if contract.get("status") != "EMPTY_TEMPLATE_PREPARE_ONLY_NO_TRUSTED_CUSTODIANS":
        raise ValueError("custodian registry contract status changed")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        if not path.is_file() or sha256(path) != binding["sha256"]:
            raise ValueError(f"custodian registry binding mismatch: {binding['path']}")
    boundary = contract["decisionBoundary"]
    if boundary["trustedCustodianCount"] != 0 or boundary["registryActivationPermitted"]:
        raise ValueError("unreviewed custodian registry enabled")
    return contract


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return parsed if parsed is not None and parsed.utcoffset() is not None else None


def assess(registry: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, Any]:
    document = contract or verified_contract()
    issues: list[str] = []
    if registry.get("schema") != document["registrySchema"]:
        issues.append("REGISTRY_SCHEMA_INVALID")
    if registry.get("classification") not in {"empty_template", "candidate_untrusted"}:
        issues.append("REGISTRY_CLASSIFICATION_INVALID")
    entries = registry.get("entries")
    if not isinstance(entries, list):
        issues.append("REGISTRY_ENTRIES_INVALID")
        entries = []
    if entries:
        issues.append("CANDIDATE_ENTRIES_REQUIRE_EXTERNAL_REVIEW")
    for index, entry in enumerate(entries):
        prefix = f"ENTRY_{index}"
        if not isinstance(entry, dict):
            issues.append(f"{prefix}_INVALID")
            continue
        missing = [field for field in document["requiredEntryFields"] if field not in entry]
        if missing:
            issues.append(f"{prefix}_REQUIRED_FIELDS_MISSING")
        if entry.get("publicKeyAlgorithm") not in document["allowedPublicKeyAlgorithms"]:
            issues.append(f"{prefix}_KEY_ALGORITHM_INVALID")
        if not isinstance(entry.get("publicKeyFingerprintSha256"), str) or SHA256_RE.fullmatch(entry["publicKeyFingerprintSha256"]) is None:
            issues.append(f"{prefix}_KEY_FINGERPRINT_INVALID")
        valid_from = _timestamp(entry.get("keyValidFrom"))
        valid_until = _timestamp(entry.get("keyValidUntil"))
        if valid_from is None or valid_until is None or valid_until <= valid_from:
            issues.append(f"{prefix}_KEY_VALIDITY_INVALID")
        reviews = entry.get("reviewEvidence")
        if not isinstance(reviews, list) or len({review.get("reviewerId") for review in reviews if isinstance(review, dict)}) < document["activationRequirements"]["minimumIndependentReviewers"]:
            issues.append(f"{prefix}_INDEPENDENT_REVIEW_INSUFFICIENT")
        if entry.get("independentOfModelDevelopment") is not True:
            issues.append(f"{prefix}_INDEPENDENCE_UNVERIFIED")
        if entry.get("revocationStatus") != "not_revoked_checked_at_use":
            issues.append(f"{prefix}_REVOCATION_STATUS_INVALID")
    if registry.get("externalSignatureVerifier") is not None:
        issues.append("EXTERNAL_SIGNATURE_VERIFIER_NOT_AUTHORIZED")
    return {
        "status": "BLOCKED_NO_TRUSTED_CUSTODIAN_REGISTRY",
        "schemaPass": not [issue for issue in issues if issue not in {"CANDIDATE_ENTRIES_REQUIRE_EXTERNAL_REVIEW"}],
        "candidateEntryCount": len(entries),
        "trustedCustodianCount": 0,
        "registryReady": False,
        "issues": sorted(set(issues)),
        "physicalSourceAuthenticationPermitted": False,
        "solverRunPermitted": False,
        "yodaLaunchPermitted": False,
        "releasePermitted": False,
    }


if __name__ == "__main__":
    contract = verified_contract()
    print(json.dumps(assess(contract["template"], contract), indent=2, sort_keys=True))
