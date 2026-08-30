from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_barrage_external_verifier_activation_requirements_v1.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    if contract.get("status") != "PREPARE_ONLY_NO_VERIFIER_ACTIVATION":
        raise ValueError("external verifier activation requirements status changed")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        if not path.is_file() or sha256(path) != binding["sha256"]:
            raise ValueError(f"external verifier binding mismatch: {binding['path']}")
    boundary = contract["decisionBoundary"]
    for key, value in boundary.items():
        if key != "requirementsValidationPermitted" and value:
            raise ValueError(f"unreviewed verifier capability enabled: {key}")
    return contract


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return parsed if parsed is not None and parsed.utcoffset() is not None else None


def assess(activation: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, Any]:
    document = contract or verified_contract()
    issues: list[str] = []
    if activation.get("schema") != document["activationSchema"]:
        issues.append("ACTIVATION_SCHEMA_INVALID")
    if activation.get("classification") not in {"empty_template", "candidate_untrusted"}:
        issues.append("ACTIVATION_CLASSIFICATION_INVALID")
    if activation.get("singleUse") is not True:
        issues.append("SINGLE_USE_REQUIRED")
    valid_from = _timestamp(activation.get("validFrom"))
    valid_until = _timestamp(activation.get("validUntil"))
    if valid_from is None or valid_until is None or valid_until <= valid_from:
        issues.append("ACTIVATION_WINDOW_INVALID")
    identity = activation.get("verifierIdentity")
    if not isinstance(identity, dict):
        issues.append("VERIFIER_IDENTITY_MISSING")
    else:
        missing_identity = [field for field in document["requiredIdentity"] if not identity.get(field)]
        if missing_identity:
            issues.append("VERIFIER_IDENTITY_INCOMPLETE")
        for field in ("executableSha256", "distributionArtifactSha256", "dependencyManifestSha256", "runtimeIdentitySha256"):
            value = identity.get(field)
            if value is not None and (not isinstance(value, str) or SHA256_RE.fullmatch(value) is None):
                issues.append(f"{field}_INVALID")
    reviews = activation.get("reviewEvidence")
    reviewer_ids = {review.get("reviewerId") for review in reviews if isinstance(review, dict)} if isinstance(reviews, list) else set()
    if len(reviewer_ids) < document["requiredReview"]["minimumIndependentReviewers"]:
        issues.append("INDEPENDENT_REVIEW_INSUFFICIENT")
    tests = activation.get("testReceipts")
    passed = {test.get("testId") for test in tests if isinstance(test, dict) and test.get("result") == "PASS"} if isinstance(tests, list) else set()
    if set(document["requiredTests"]) - passed:
        issues.append("REQUIRED_NEGATIVE_OR_VECTOR_TESTS_MISSING")
    if activation.get("activated") is not False:
        issues.append("UNAUTHORIZED_ACTIVATION_STATE")
    return {
        "status": "BLOCKED_NO_REVIEWED_EXTERNAL_VERIFIER_ACTIVATION",
        "requirementsPass": not issues,
        "activationReady": False,
        "issues": sorted(set(issues)),
        "verifierExecutionPermitted": False,
        "cryptographicVerificationPermitted": False,
        "physicalSourceAuthenticationPermitted": False,
        "solverRunPermitted": False,
        "yodaLaunchPermitted": False,
        "releasePermitted": False,
    }


if __name__ == "__main__":
    contract = verified_contract()
    print(json.dumps(assess(contract["template"], contract), indent=2, sort_keys=True))
