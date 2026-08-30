from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/stage20_barrage_physical_source_provenance_v1.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text())
    if contract.get("status") != "PREPARE_ONLY_STATIC_CHAIN_VALIDATOR_NO_TRUSTED_CUSTODIAN_REGISTRY":
        raise ValueError("provenance contract status changed")
    for binding in contract["bindings"]:
        path = ROOT / binding["path"]
        if not path.is_file() or sha256(path) != binding["sha256"]:
            raise ValueError(f"provenance binding mismatch: {binding['path']}")
    if contract["trustedCustodianRegistry"]["present"] is not False:
        raise ValueError("unreviewed trusted custodian registry enabled")
    boundary = contract["decisionBoundary"]
    for key, value in boundary.items():
        if key != "staticChainValidationPermitted" and value:
            raise ValueError(f"forbidden provenance authority enabled: {key}")
    return contract


def _safe_file(base: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def assess(dataset: dict[str, Any], base: Path = ROOT, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    document = contract or verified_contract()
    issues: list[str] = []
    manifest_path = _safe_file(base, dataset.get("sourceManifestPath"))
    approval_path = _safe_file(base, dataset.get("sourceApprovalPath"))
    manifest_sha = dataset.get("sourceManifestSha256")
    approval_sha = dataset.get("sourceApprovalSha256")
    if manifest_path is None or not isinstance(manifest_sha, str) or SHA256_RE.fullmatch(manifest_sha) is None:
        issues.append("SOURCE_MANIFEST_REFERENCE_INVALID")
    elif sha256(manifest_path) != manifest_sha:
        issues.append("SOURCE_MANIFEST_SHA_MISMATCH")
    if approval_path is None or not isinstance(approval_sha, str) or SHA256_RE.fullmatch(approval_sha) is None:
        issues.append("SOURCE_APPROVAL_REFERENCE_INVALID")
    elif sha256(approval_path) != approval_sha:
        issues.append("SOURCE_APPROVAL_SHA_MISMATCH")

    manifest = json.loads(manifest_path.read_text()) if manifest_path is not None and "SOURCE_MANIFEST_SHA_MISMATCH" not in issues else {}
    approval = json.loads(approval_path.read_text()) if approval_path is not None and "SOURCE_APPROVAL_SHA_MISMATCH" not in issues else {}
    if manifest.get("schema") != document["sourceManifestSchema"]:
        issues.append("SOURCE_MANIFEST_SCHEMA_INVALID")
    if manifest.get("sourceClass") not in document["requiredSourceClasses"]:
        issues.append("SOURCE_CLASS_INVALID")
    if manifest.get("units") != document["requiredUnits"]:
        issues.append("SOURCE_UNITS_INVALID")
    if not isinstance(manifest.get("instrumentIds"), list) or not manifest.get("instrumentIds"):
        issues.append("SOURCE_INSTRUMENT_IDS_INVALID")
    if not isinstance(manifest.get("sourceFiles"), list) or not manifest.get("sourceFiles"):
        issues.append("SOURCE_FILE_INVENTORY_MISSING")
    if approval.get("schema") != document["approvalSchema"]:
        issues.append("SOURCE_APPROVAL_SCHEMA_INVALID")
    if approval.get("sourceManifestSha256") != manifest_sha:
        issues.append("SOURCE_APPROVAL_MANIFEST_LINK_MISMATCH")
    if approval.get("decision") != "APPROVED_PHYSICAL_SOURCE":
        issues.append("SOURCE_APPROVAL_DECISION_INVALID")
    if not isinstance(approval.get("custodianId"), str) or not approval.get("custodianId"):
        issues.append("SOURCE_APPROVAL_CUSTODIAN_INVALID")

    static_chain_pass = not issues
    authentication_issues = [] if document["trustedCustodianRegistry"]["present"] else ["TRUSTED_CUSTODIAN_REGISTRY_MISSING"]
    return {
        "status": "BLOCKED_EXTERNAL_AUTHENTICITY_NOT_ESTABLISHED",
        "staticChainPass": static_chain_pass,
        "physicalSourceAuthenticated": False,
        "issues": sorted(set(issues + authentication_issues)),
        "parameterFitPermitted": False,
        "solverRunPermitted": False,
        "yodaLaunchPermitted": False,
        "releasePermitted": False,
    }


if __name__ == "__main__":
    print(json.dumps(assess({}), indent=2, sort_keys=True))
