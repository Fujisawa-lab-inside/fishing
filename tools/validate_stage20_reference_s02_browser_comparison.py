#!/usr/bin/env python3
"""Validate the retained S02 browser-comparison evidence and safeguards."""

from __future__ import annotations

import hashlib
import json
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
    evaluation_path = "config/stage20_reference_s02_browser_comparison_v1.json"
    evaluation = load(evaluation_path)
    approval = load("config/stage20_reference_s02_browser_comparison_approval_v1.json")
    report_path = evaluation["source"]["comparisonReport"]
    manifest_path = evaluation["source"]["timePackManifest"]
    report = load(report_path)
    manifest = load(manifest_path)

    require(approval["approvedChoice"] == "A", "comparison preparation was not approved")
    require(
        approval["status"] == "comparison_preparation_approved_and_completed",
        "unexpected approval status",
    )
    require(digest(report_path) == evaluation["source"]["comparisonReportSha256"], "report digest mismatch")
    require(digest(manifest_path) == evaluation["source"]["timePackManifestSha256"], "pack manifest digest mismatch")
    for path_key, hash_key in (
        ("interpolator", "interpolatorSha256"),
        ("comparisonRunner", "comparisonRunnerSha256"),
        ("packBuilder", "packBuilderSha256"),
        ("evaluator", "evaluatorSha256"),
    ):
        require(
            digest(evaluation["source"][path_key]) == evaluation["source"][hash_key],
            f"implementation digest mismatch: {path_key}",
        )
    binary_path = str(Path(manifest_path).parent / manifest["binary"]["url"])
    require(digest(binary_path) == manifest["binary"]["sha256"], "pack binary digest mismatch")
    require((ROOT / binary_path).stat().st_size == manifest["binary"]["byteLength"], "pack byte length mismatch")
    require(manifest["arrays"]["snapshots"]["shape"] == [5, 3, 50199], "unexpected pack shape")
    require(manifest["timeContract"]["anchorHours"] == [-12, -11, -10, -9, -8], "unexpected anchor hours")
    require(manifest["timeContract"]["extrapolationAllowed"] is False, "extrapolation must be disabled")
    for source in manifest["sources"]:
        require(digest(source["path"]) == source["sha256"], f"source digest mismatch: {source['path']}")

    require(report["pack"]["manifestSha256"] == digest(manifest_path), "report manifest digest mismatch")
    require(report["pack"]["binarySha256"] == digest(binary_path), "report binary digest mismatch")
    require(len(report["exactAnchorReconstruction"]) == 5, "five exact anchors required")
    for item in report["exactAnchorReconstruction"]:
        require(item["velocityVectorRmseMPS"] == 0, "exact anchor reconstruction changed")
    require(len(report["leaveOneHourOut"]) == 3, "three leave-one-out cases required")
    for item in report["leaveOneHourOut"]:
        prediction = str(Path(report_path).parent / item["prediction"])
        require(digest(prediction) == item["predictionSha256"], f"prediction digest mismatch: {prediction}")
        require((ROOT / prediction).stat().st_size == item["predictionByteLength"], "prediction byte length mismatch")

    thresholds = evaluation["thresholds"]
    require(evaluation["exactHourlyAnchorPath"]["passed"] is True, "exact-hour path must pass")
    require(
        evaluation["exactHourlyAnchorPath"]["maximumFloat32VelocityVectorRmseMPS"]
        <= thresholds["maximumFloat32VelocityVectorRmseMPS"],
        "float32 error exceeds threshold",
    )
    require(evaluation["missingHourLinearFallback"]["passed"] is False, "missing-hour fallback must be rejected")
    require(
        evaluation["missingHourLinearFallback"]["worstModelHour"] == -11,
        "unexpected worst leave-one-out hour",
    )
    per_hour = {item["modelHour"]: item["passed"] for item in evaluation["missingHourLinearFallback"]["perHourAcceptance"]}
    require(per_hour == {-11: False, -10: False, -9: True}, "leave-one-out acceptance changed")
    decision = evaluation["architectureDecision"]
    require(decision["retainEveryDisplayedHourlySnapshot"] is True, "hourly snapshots must be retained")
    require(decision["allowMissingHourLinearFallback"] is False, "missing-hour fallback must remain disabled")
    require(decision["crossConditionInterpolationValidated"] is False, "cross-condition interpolation is not validated")

    fields = evaluation["worstCaseMapFields"]
    require(digest(fields["predicted"]) == fields["predictedSha256"], "predicted fields digest mismatch")
    require(digest(fields["error"]) == fields["errorSha256"], "error fields digest mismatch")
    visuals = evaluation["visualEvidence"]
    for key, hash_key in (
        ("directMap", "directMapSha256"),
        ("predictedMap", "predictedMapSha256"),
        ("errorMap", "errorMapSha256"),
        ("decisionImage", "decisionImageSha256"),
    ):
        require(digest(visuals[key]) == visuals[hash_key], f"visual digest mismatch: {key}")
    predicted_manifest = str(Path(visuals["predictedMap"]).parent / "visual-manifest.json")
    error_manifest = str(Path(visuals["errorMap"]).parent / "visual-manifest.json")
    require(digest(predicted_manifest) == visuals["predictedManifestSha256"], "predicted manifest mismatch")
    require(digest(error_manifest) == visuals["errorManifestSha256"], "error manifest mismatch")

    for source in (manifest, report, evaluation):
        safeguards = source["safeguards"]
        require(safeguards["additionalPhysicalRunPerformed"] is False, "additional physical run recorded")
        require(safeguards["publicSimulatorConnected"] is False, "public simulator must remain disconnected")
        require(safeguards["mainMergeAuthorized"] is False, "main merge must remain unauthorized")
        require(safeguards["physicalValidationClaimAllowed"] is False, "physical validation claim must remain forbidden")
    require(report["timing"]["browserTimingClaimAllowed"] is False, "Node timing must not become a browser claim")
    require(evaluation["nextDecision"]["additionalPhysicalRunAuthorized"] is False, "next decision must not authorize a run")

    print(
        json.dumps(
            {
                "status": "passed",
                "evaluation": evaluation_path,
                "exactHourlySnapshotPath": "passed",
                "missingHourLinearFallback": "rejected",
                "crossConditionInterpolationValidated": False,
                "additionalPhysicalRunPerformed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
