#!/usr/bin/env python3
"""Validate the inactive Stage 20 barrage holdout recovery candidate."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from run_stage20_barrage_holdout_recovery_segment import (
    ACTIVATION_PATH,
    AUTHORIZATION_PATH,
    CONTRACT_PATH,
    GATE_PATH,
    sha256,
    validate_contract,
)


CANDIDATE_PATH = Path("config/stage20_barrage_holdout_recovery_candidate_v1.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    candidate = json.loads((root / CANDIDATE_PATH).read_text(encoding="utf-8"))
    contract = validate_contract(root)
    require(candidate["schema"] == "onga-stage20-barrage-holdout-recovery-candidate-v1", "candidate schema mismatch")
    require(candidate["status"] == "prepared_inactive_awaiting_visual_authorization", "candidate status mismatch")
    require(candidate["executionContract"]["path"] == str(CONTRACT_PATH), "candidate contract path mismatch")
    require(candidate["executionContract"]["sha256"] == sha256(root / CONTRACT_PATH), "candidate contract digest mismatch")
    visual = candidate["visualDecision"]
    require(visual["decisionImageSha256"] == sha256(root / visual["decisionImage"]), "decision image digest mismatch")
    require(visual["rendererSha256"] == sha256(root / visual["renderer"]), "decision renderer digest mismatch")
    validation = candidate["validation"]
    require(validation["validator"] == str(Path(__file__).resolve().relative_to(root)), "validator path mismatch")
    require(validation["validatorSha256"] == sha256(Path(__file__).resolve()), "validator digest mismatch")
    require(validation["status"] == "passed_inactive_barrage_holdout_recovery_candidate_validation", "validator status mismatch")
    require(candidate["recovery"]["newPhysicalJobs"] == len(contract["jobs"]) == 5, "recovery job count mismatch")
    require(candidate["recovery"]["newSnapshots"] == sum(len(job["snapshotModelHours"]) for job in contract["jobs"]), "new snapshot count mismatch")
    require(candidate["recovery"]["combinedSnapshotsAfterSuccess"] == 10, "combined snapshot count mismatch")
    require(candidate["recovery"]["unsealedPartialClosedS03Reused"] is False, "unsealed partial input enabled")
    require(candidate["resource"]["standardPublicRunnerMinuteChargeExpectedUsd"] == 0, "free standard runner assumption changed")
    require(candidate["resource"]["paidResourceAllowed"] is False, "paid resource enabled")
    require(candidate["resource"]["largerRunnerAllowed"] is False, "larger runner enabled")
    require(candidate["evidenceCorrections"]["regionalMasksDigestLockedBeforeExecution"] is True, "regional masks not locked")
    require(candidate["evidenceCorrections"]["successorReceiptsWillRecordInputRestartSha256"] is True, "input restart receipt evidence missing")
    require(candidate["evidenceCorrections"]["maximumDepthRmseM"] == contract["postRunHoldoutAcceptance"]["maximumDepthRmseM"], "depth RMSE mismatch")
    require(candidate["evidenceCorrections"]["maximumAbsoluteDepthErrorM"] == contract["postRunHoldoutAcceptance"]["maximumAbsoluteDepthErrorM"], "depth maximum mismatch")
    require(candidate["execution"]["physicalRunStarted"] is False and candidate["execution"]["numericalStepCalled"] is False, "candidate claims execution")
    masks = json.loads((root / contract["regionalMasks"]["manifest"]).read_text(encoding="utf-8"))
    payload = (root / contract["regionalMasks"]["binary"]).read_bytes()
    require([view["id"] for view in masks["views"]] == ["estuary", "barrage", "confluence", "fishway"], "regional mask IDs mismatch")
    require(masks["views"][0]["legacyAlias"] == "full_estuary", "full-estuary alias missing")
    for view in masks["views"]:
        start = int(view["byteOffset"])
        end = start + int(view["byteLength"])
        ids = [item[0] for item in struct.iter_unpack("<i", payload[start:end])]
        require(len(ids) == int(view["cellCount"]), f"regional mask count mismatch: {view['id']}")
        require(ids == sorted(set(ids)), f"regional mask IDs are not sorted unique: {view['id']}")
        require(ids and ids[0] >= 0 and ids[-1] < contract["mesh"]["cellCount"], f"regional mask ID outside mesh: {view['id']}")
    require([item[0] for item in struct.iter_unpack("<i", payload[: masks["views"][0]["byteLength"]])] == list(range(contract["mesh"]["cellCount"])), "estuary mask is not the full mesh")
    for path in (AUTHORIZATION_PATH, GATE_PATH, ACTIVATION_PATH):
        require(not (root / path).exists(), f"inactive control file unexpectedly present: {path}")
    workflow = (root / contract["runner"]["workflowPath"]).read_text(encoding="utf-8")
    require("runs-on: ubuntu-latest" in workflow, "standard runner missing")
    require("--jq '.visibility'" in workflow and '"$visibility" != "public"' in workflow, "public visibility fail-closed check missing")
    require("retention-days: 30" in workflow, "artifact retention mismatch")
    require("timeout --signal=TERM --kill-after=30s 5h" in workflow, "five-hour numerical stop missing")
    require("larger" not in workflow.lower(), "larger runner reference present in workflow")
    for job in contract["jobs"]:
        require(workflow.count(f"--job-id {job['id']}") == 1, f"workflow job mapping mismatch: {job['id']}")
    safeguards = candidate["safeguards"]
    require(all(safeguards[key] is False for key in safeguards), "candidate safeguard enabled")
    print(
        json.dumps(
            {
                "status": "passed_inactive_barrage_holdout_recovery_candidate_validation",
                "physicalJobs": len(contract["jobs"]),
                "newSnapshots": candidate["recovery"]["newSnapshots"],
                "authorizationPresent": False,
                "gatePresent": False,
                "activationPresent": False,
                "numericalStepCalled": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
