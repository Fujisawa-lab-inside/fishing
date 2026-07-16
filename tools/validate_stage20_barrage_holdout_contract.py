#!/usr/bin/env python3
"""Validate the inactive eight-job barrage holdout contract and workflow."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def digest(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    contract_path = "config/stage20_barrage_holdout_contract_v1.json"
    contract = load(contract_path)
    candidate = load("config/stage20_barrage_holdout_execution_candidate_v1.json")
    approval = load(contract["scopeApproval"]["path"])
    require(contract["executionAuthorized"] is False, "contract self-authorized")
    require(approval["approvedChoice"] == "A", "barrage-first scope not approved")
    for item in ("scopeApproval", "holdoutPlan", "basisPlan"):
        require(digest(contract[item]["path"]) == contract[item]["sha256"], f"{item} digest mismatch")
    for key, hash_key in (("tideCandidate", "tideCandidateSha256"), ("waterMask", "waterMaskSha256")):
        require(digest(contract["inputs"][key]) == contract["inputs"][hash_key], f"{key} digest mismatch")
    require(digest(contract["mesh"]["manifest"].replace(".json", ".bin")) == contract["mesh"]["sha256"], "mesh digest mismatch")
    require(digest(contract["kernel"]["path"]) == contract["kernel"]["sha256"], "kernel digest mismatch")
    require(digest(contract["runner"]["path"]) == contract["runner"]["sha256"], "runner digest mismatch")
    require(digest(contract["runner"]["workflowPath"]) == contract["runner"]["workflowSha256"], "workflow digest mismatch")
    require(candidate["contract"]["path"] == contract_path, "candidate contract path mismatch")
    require(candidate["contract"]["sha256"] == digest(contract_path), "candidate contract digest mismatch")
    decision = candidate["decision"]
    require(digest(decision["decisionImage"]) == decision["decisionImageSha256"], "decision image digest mismatch")
    require(digest(decision["renderer"]) == decision["rendererSha256"], "decision renderer digest mismatch")
    require(candidate["safeguards"]["physicalRunAuthorized"] is False, "candidate physical run enabled")

    jobs = contract["jobs"]
    ids = [job["id"] for job in jobs]
    require(len(ids) == len(set(ids)) == 8, "eight unique segment jobs required")
    for basis in ("barrage-closed", "barrage-open"):
        chain = [job for job in jobs if job["basisId"] == basis]
        require(len(chain) == 4, f"four jobs required for {basis}")
        for index, job in enumerate(chain):
            expected_predecessor = None if index == 0 else chain[index - 1]["id"]
            require(job["predecessorJobId"] == expected_predecessor, f"predecessor mismatch: {job['id']}")
            require(job["targetPhysicalSeconds"] == 14400, f"segment duration mismatch: {job['id']}")
            require(job["maximumNumericalWallSeconds"] == 18000, f"wall stop mismatch: {job['id']}")
    require(sum(len(job["snapshotModelHours"]) for job in jobs) == 10, "ten endpoint snapshots required")
    require(contract["heldOutReference"]["usedToFitInterpolation"] is False, "held-out reference used in fit")
    require(contract["postRunHoldoutAcceptance"]["allFiveHoursAndFourRegionsMustPass"] is True, "partial acceptance enabled")

    workflow = (ROOT / contract["runner"]["workflowPath"]).read_text(encoding="utf-8")
    workflow_job_ids = re.findall(r"^  ([a-z][a-z0-9_]*):\n    (?:needs:.*\n    )?runs-on:", workflow, re.MULTILINE)
    require(set(workflow_job_ids) == {"preflight", "authorize", "closed_s01", "open_s01", "closed_s02", "open_s02", "closed_s03", "open_s03", "closed_s04", "open_s04"}, "workflow job set mismatch")
    require("stage20_barrage_holdout_activation_v1.json" in workflow, "activation-only trigger missing")
    require("workflow_dispatch" not in workflow, "manual trigger must be absent")
    require("GITHUB_RUN_ATTEMPT" in (ROOT / contract["runner"]["path"]).read_text(encoding="utf-8"), "rerun guard missing")
    require(workflow.count("timeout --signal=TERM --kill-after=30s 5h") == 8, "five-hour stops missing")
    require(workflow.count("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02") == 8, "artifact upload count mismatch")
    require(workflow.count("actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093") == 6, "restart download count mismatch")
    for expected in (
        "closed_s02:\n    needs: [closed_s01, open_s01]",
        "open_s02:\n    needs: [closed_s01, open_s01]",
        "closed_s03:\n    needs: [closed_s02, open_s02]",
        "open_s03:\n    needs: [closed_s02, open_s02]",
        "closed_s04:\n    needs: [closed_s03, open_s03]",
        "open_s04:\n    needs: [closed_s03, open_s03]",
    ):
        require(expected in workflow, "cross-chain stage barrier missing")

    control = contract["control"]
    for path_key, present_key in (("authorizationPath", "authorizationPresent"), ("gatePath", "gatePresent"), ("activationPath", "activationPresent")):
        require(control[present_key] is False, f"{present_key} changed")
        require(not (ROOT / control[path_key]).exists(), f"inactive control unexpectedly exists: {control[path_key]}")
    safeguards = contract["safeguards"]
    require(safeguards["automaticRetryAllowed"] is False, "automatic retry enabled")
    require(safeguards["additionalRunAllowed"] is False, "additional run enabled")
    require(safeguards["crossBasisRestartAllowed"] is False, "cross-basis restart enabled")
    require(safeguards["publicSimulatorConnectionAllowed"] is False, "public connection enabled")
    require(safeguards["mainMergeAllowed"] is False, "main merge enabled")

    print(json.dumps({
        "status": "passed_inactive_contract",
        "contract": contract_path,
        "physicalJobCount": 8,
        "endpointSnapshotCount": 10,
        "authorizationPresent": False,
        "gatePresent": False,
        "activationPresent": False,
        "numericalStepCalled": False
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
