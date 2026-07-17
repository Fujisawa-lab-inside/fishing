#!/usr/bin/env python3
"""Validate the adopted, isolated Stage 20 barrage piecewise candidate record."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = ROOT / "config/stage20_barrage_piecewise_candidate_v1.json"
ADOPTION_PATH = ROOT / "config/stage20_barrage_piecewise_candidate_adoption_v1.json"
EXPECTED_ANALYSIS_SHA256 = "82ce4ece4dda010b846204266e604c01d26eaffba041bd4b04329a353fc834c2"
EXPECTED_RESULT_SHA256 = "fe4be9be3112eafff9965abc68bf254c78d560344c99cb2d5f31e1e75af519ab"
EXPECTED_PACK_SHA256 = "d3a0b315d7fb3bf17c04a4715b1595242b501a50dacc163ae8716013ed638047"
EXPECTED_MESH_SHA256 = "09dd7e6b667fcdb334ec6db8daa72851d8cba78b7a823ca828980ec0a5ed7659"
EXPECTED_RECORD_SHA256 = "64f3c829f66d6d067b5e4892e8bcd9bac84d9c099ae7c41b008a89b039c46af3"
EXPECTED_SELECTED_STATEMENT = (
    "A：50%を固定できる利点を優先し、変化率の折れを明示した内部コード候補として保持する"
)
EXPECTED_REGIONS = ("estuary", "barrage", "confluence", "fishway")
EXPECTED_PANELS = (
    "direct_0",
    "interpolated_25",
    "direct_50",
    "interpolated_75",
    "direct_100",
    "canonical_kink",
)


class ValidationError(RuntimeError):
    """The candidate record or one of its evidence links is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"missing JSON: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def repo_file(value: object, label: str) -> Path:
    require(isinstance(value, str) and value, f"{label} path is missing")
    path = (ROOT / value).resolve()
    require(path.is_relative_to(ROOT), f"{label} path escapes repository")
    require(path.is_file() and not path.is_symlink(), f"{label} file is unsafe")
    return path


def validate_file_record(record: Mapping[str, Any], label: str) -> Path:
    path = repo_file(record.get("path"), label)
    require(sha256_file(path) == record.get("sha256"), f"{label} digest mismatch")
    if "byteLength" in record:
        require(path.stat().st_size == record["byteLength"], f"{label} byte length mismatch")
    return path


def require_false_safeguards(
    safeguards: Mapping[str, Any],
    label: str,
    keys: tuple[str, ...],
) -> None:
    for key in keys:
        require(safeguards.get(key) is False, f"{label} safeguard {key} is not false")


def main() -> int:
    try:
        record = load_json(RECORD_PATH)
        require(record.get("schema") == "onga-stage20-barrage-piecewise-candidate-v1", "record schema mismatch")
        require(
            record.get("status")
            == "adopted_as_isolated_internal_code_candidate_not_public_simulator",
            "record status mismatch",
        )
        require(sha256_file(RECORD_PATH) == EXPECTED_RECORD_SHA256, "candidate record identity changed")
        decision = record.get("decision", {})
        require(decision.get("selectedChoice") == "A", "candidate selected choice mismatch")
        require(decision.get("selectedDate") == "2026-07-17", "candidate selected date mismatch")
        require(
            decision.get("selectedStatement") == EXPECTED_SELECTED_STATEMENT,
            "candidate selected statement mismatch",
        )
        require(
            decision.get("selectedEffect")
            == "retain_candidate_files_and_evidence_on_the_work_branch_without_runtime_or_public_connection",
            "candidate selected effect mismatch",
        )
        for key in (
            "choiceAConnectsPublicSimulator",
            "choiceAStartsPhysicalRun",
            "choiceAAuthorizesMainMerge",
        ):
            require(decision.get(key) is False, f"candidate decision {key} is not false")

        adoption = load_json(ADOPTION_PATH)
        require(
            adoption.get("schema")
            == "onga-stage20-barrage-piecewise-candidate-adoption-v1",
            "adoption schema mismatch",
        )
        require(
            adoption.get("status")
            == "adopted_as_isolated_internal_code_candidate_not_public_simulator",
            "adoption status mismatch",
        )
        require(adoption.get("selectedChoice") == "A", "adoption selected choice mismatch")
        require(adoption.get("selectedDate") == "2026-07-17", "adoption selected date mismatch")
        require(
            adoption.get("selectedStatement") == EXPECTED_SELECTED_STATEMENT,
            "adoption selected statement mismatch",
        )
        adoption_candidate_path = validate_file_record(
            adoption["candidateRecord"],
            "adopted candidate record",
        )
        require(adoption_candidate_path == RECORD_PATH, "adoption points to another candidate record")
        require(
            adoption["candidateRecord"].get("sha256") == EXPECTED_RECORD_SHA256,
            "adoption candidate identity changed",
        )
        require(
            adoption["candidateRecord"].get("status")
            == "adopted_as_isolated_internal_code_candidate_not_public_simulator",
            "adoption candidate status mismatch",
        )
        accepted = adoption.get("acceptedProperties", {})
        for key in (
            "direct50PercentPackedAnchorFixed",
            "valueContinuousAt50Percent",
            "responseRateKinkAt50PercentExplicit",
        ):
            require(accepted.get(key) is True, f"accepted property {key} is not true")
        require(
            accepted.get("modelHours") == [-12, -11, -10, -9, -8],
            "accepted model hours changed",
        )
        for key in (
            "directPhysicalValidationAt25And75Percent",
            "openingTimeSeriesAllowed",
            "differentTideDischargeOrRainInputsAllowed",
            "observedAccuracyValidated",
            "forecastAccuracyValidated",
        ):
            require(accepted.get(key) is False, f"accepted limitation {key} is not false")
        effects = adoption.get("effects", {})
        require(effects.get("retainOnWorkingBranch") is True, "working-branch retention not authorized")
        require(effects.get("internalCodeCandidateOnly") is True, "internal-only effect not recorded")
        require(effects.get("workBranchCommitAndPushAuthorized") is True, "work-branch recording not authorized")
        for key in (
            "runtimeIntegrationAuthorized",
            "publicSimulatorConnectionAuthorized",
            "additionalPhysicalRunAuthorized",
            "automaticRetryAuthorized",
            "referenceS03Authorized",
            "thirtySixHourServiceUseAuthorized",
            "mainMergeAuthorized",
        ):
            require(effects.get(key) is False, f"adoption effect {key} is not false")
        adoption_validator_path = repo_file(
            adoption["toolchain"]["validator"],
            "adoption validator",
        )
        require(adoption_validator_path == Path(__file__).resolve(), "adoption validator path mismatch")
        require(
            adoption["toolchain"]["validatorSha256"] == sha256_file(adoption_validator_path),
            "adoption validator digest mismatch",
        )
        source_decision_path = validate_file_record(record["sourceDecision"], "source decision")
        require(record["sourceDecision"]["sha256"] == EXPECTED_RESULT_SHA256, "source decision identity changed")
        source_decision = load_json(source_decision_path)
        require(
            source_decision.get("decision", {}).get("optionA")
            == "retain_direct_50_percent_s02_as_middle_anchor_and_prepare_code_only_piecewise_0_50_50_100_interpolation_candidate",
            "source option A changed",
        )
        analysis_path = validate_file_record(record["sourceEvidence"]["analysis"], "source analysis")
        require(record["sourceEvidence"]["analysis"]["sha256"] == EXPECTED_ANALYSIS_SHA256, "analysis identity changed")
        analysis = load_json(analysis_path)
        require(analysis.get("status") == "evaluated_failed_thresholds", "analysis status mismatch")
        require(record["sourceEvidence"]["meshBinarySha256"] == EXPECTED_MESH_SHA256, "record mesh identity changed")
        require(record["sourceEvidence"]["snapshotCount"] == 15, "record source count mismatch")

        pack_manifest_path = validate_file_record(record["anchorPack"]["manifest"], "pack manifest")
        pack_binary_path = validate_file_record(record["anchorPack"]["binary"], "pack binary")
        require(record["anchorPack"]["binary"]["sha256"] == EXPECTED_PACK_SHA256, "pack identity changed")
        pack_manifest = load_json(pack_manifest_path)
        require(pack_manifest["binary"]["sha256"] == sha256_file(pack_binary_path), "pack binary link mismatch")
        require(pack_manifest["mesh"]["binarySha256"] == EXPECTED_MESH_SHA256, "pack mesh identity mismatch")
        require(pack_manifest["openingContract"]["anchorFractions"] == [0.0, 0.5, 1.0], "pack anchors changed")
        require(pack_manifest["timeContract"]["anchorHours"] == [-12, -11, -10, -9, -8], "pack hours changed")
        require(pack_manifest["openingContract"]["timeVaryingScheduleAllowed"] is False, "time-varying opening enabled")
        require(pack_manifest["timeContract"]["timeInterpolationAllowed"] is False, "time interpolation enabled")
        require(pack_manifest["timeContract"]["timeExtrapolationAllowed"] is False, "time extrapolation enabled")
        require(pack_manifest["float32Quantization"]["passed"] is True, "pack quantization did not pass")
        builder_path = repo_file(pack_manifest["builder"]["path"], "pack builder")
        require(
            sha256_file(builder_path) == pack_manifest["builder"]["sha256"],
            "pack builder digest mismatch",
        )
        with tempfile.TemporaryDirectory(
            prefix=".stage20-piecewise-builder-negative-",
            dir=ROOT,
        ) as temporary_output:
            output_path = Path(temporary_output)
            output_relative = output_path.relative_to(ROOT).as_posix()
            escaped_name = f"../{output_path.name}-escape.json"
            negative_name_cases = (
                ["--manifest-name", escaped_name],
                [
                    "--manifest-name",
                    "same-name.bin",
                    "--binary-name",
                    "same-name.bin",
                ],
                ["--binary-name", str(output_path / "absolute.bin")],
            )
            for arguments in negative_name_cases:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(builder_path),
                        "--output-dir",
                        output_relative,
                        *arguments,
                    ],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                require(
                    completed.returncode == 2,
                    f"unsafe builder output names were accepted: {arguments}",
                )
            require(
                not any(output_path.iterdir()),
                "unsafe builder-name tests wrote inside the temporary output",
            )
            require(
                not (output_path.parent / f"{output_path.name}-escape.json").exists(),
                "unsafe builder-name tests escaped the output directory",
            )

        source_validation_path = validate_file_record(
            record["anchorPack"]["sourcePayloadReconstruction"],
            "source-pack validation",
        )
        source_validation = load_json(source_validation_path)
        require(
            source_validation.get("status")
            == "passed_exact_source_to_pack_reconstruction_not_physical_validation",
            "source-pack validation status mismatch",
        )
        checks = source_validation.get("checks", {})
        require(checks.get("sourceAnchorCount") == 15, "source-pack anchor count mismatch")
        require(
            checks.get("payloadMatchedIndependentFloat32ReconstructionByteForByte") is True,
            "source-pack byte reconstruction did not pass",
        )
        require(
            checks.get("reconstructedPayloadSha256") == EXPECTED_PACK_SHA256,
            "source-pack reconstructed digest mismatch",
        )
        source_validator_path = repo_file(
            source_validation["toolchain"]["validator"],
            "source-pack validator",
        )
        require(
            sha256_file(source_validator_path)
            == source_validation["toolchain"]["validatorSha256"],
            "source-pack validator digest mismatch",
        )
        live_source_validation = subprocess.run(
            [
                sys.executable,
                "-B",
                str(source_validator_path),
                "--no-write",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        require(
            live_source_validation.returncode == 0,
            "live source-pack reconstruction failed: "
            + live_source_validation.stderr.strip(),
        )
        live_source_report = json.loads(live_source_validation.stdout)
        require(
            live_source_report == source_validation,
            "live source-pack reconstruction differs from the saved report",
        )

        module_path = validate_file_record(record["browserCandidate"]["module"], "piecewise module")
        worker_path = validate_file_record(record["browserCandidate"]["worker"], "piecewise worker")
        browser_validation_path = validate_file_record(
            record["browserCandidate"]["validation"],
            "browser-candidate validation",
        )
        browser_validation = load_json(browser_validation_path)
        require(
            browser_validation.get("status")
            == "passed_code_only_piecewise_browser_candidate_validation_not_physical_validation",
            "browser-candidate validation status mismatch",
        )
        require(
            browser_validation["toolchain"]["moduleSha256"] == sha256_file(module_path),
            "browser-candidate module link mismatch",
        )
        require(
            browser_validation["toolchain"]["workerSha256"] == sha256_file(worker_path),
            "browser-candidate worker link mismatch",
        )
        browser_validator_path = repo_file(
            browser_validation["toolchain"]["validator"],
            "browser-candidate validator",
        )
        require(
            browser_validation["toolchain"]["validatorSha256"]
            == sha256_file(browser_validator_path),
            "browser-candidate validator digest mismatch",
        )
        direct = browser_validation["directModuleValidation"]
        require(direct["exactAnchorReproduction"] is True, "packed anchors are not exact")
        require(direct["adjacentMidpointsExactFloat32"] is True, "packed adjacent midpoints are not exact")
        require(direct["deterministic"] is True, "piecewise output is not deterministic")
        require(browser_validation["negativeCases"]["status"] == "passed", "negative cases failed")

        map_manifest_path = validate_file_record(record["visualEvidence"]["manifest"], "map manifest")
        map_manifest = load_json(map_manifest_path)
        require(
            map_manifest.get("schema") == "onga-stage20-barrage-piecewise-map-manifest-v1",
            "map manifest schema mismatch",
        )
        require(
            map_manifest.get("status")
            == "rendered_inactive_code_only_piecewise_candidate_not_physical_validation",
            "map manifest status mismatch",
        )
        require(map_manifest.get("modelHour") == -9, "map model hour changed")
        require(map_manifest["display"]["panelOrder"] == list(EXPECTED_PANELS), "map panel order changed")
        require(
            map_manifest["candidate"]["valueContinuityAt50Percent"]
            == "guaranteed_by_construction",
            "map continuity statement changed",
        )
        require(
            map_manifest["candidate"]["slopeSmoothnessAt50Percent"]
            == "not_achieved",
            "map slope limitation changed",
        )
        require(
            map_manifest["candidate"]["directPhysicalValidationAt25And75Percent"] is False,
            "map claims direct 25/75 physical validation",
        )
        algebra = map_manifest["algebraValidation"]
        for key in (
            "canonicalKinkDepthMatchesExistingErrorExactly",
            "canonicalKinkVelocityMatchesExistingErrorExactly",
            "directMiddleAnchorReusedWithoutEndpointMidpointReplacement",
            "interpolatedDepthsNonnegative",
            "interpolatedFieldsFinite",
            "leftSegmentReturnsDirect50Exactly",
            "rightSegmentReturnsDirect50Exactly",
            "stepExpressionAllclose",
            "valueContinuousAt50Percent",
        ):
            require(algebra.get(key) is True, f"map algebra check failed: {key}")
        require(map_manifest["source"]["analysis"]["sha256"] == EXPECTED_ANALYSIS_SHA256, "map analysis changed")
        require(map_manifest["browserPackContext"]["sha256"] == sha256_file(pack_manifest_path), "map pack link mismatch")
        require(map_manifest["mesh"]["binarySha256"] == EXPECTED_MESH_SHA256, "map mesh changed")
        require(map_manifest["satelliteBackdrop"]["networkUsed"] is False, "map used network")
        require(map_manifest["display"]["arrowAggregation"]["positionAndVectorWeights"] == "direct_50_percent_water_depth_times_cell_area_for_all_panels", "map arrow weighting changed")

        overview_path = validate_file_record(record["visualEvidence"]["judgmentImage"], "judgment image")
        adoption_overview_path = validate_file_record(
            adoption["judgmentImage"],
            "adoption judgment image",
        )
        require(adoption_overview_path == overview_path, "adoption uses another judgment image")
        require(
            record["visualEvidence"]["judgmentImage"]["sha256"]
            == map_manifest["display"]["overview"]["sha256"],
            "record and map overview differ",
        )
        with Image.open(overview_path) as image:
            require(image.size == (2000, 1490), "overview dimensions changed")
            image.verify()
        views = map_manifest["display"]["views"]
        require([view["id"] for view in views] == list(EXPECTED_REGIONS), "map region order changed")
        output_count = 1
        for view in views:
            require(view["panelCount"] == 6, f"{view['id']} panel count mismatch")
            require(view["panelOrder"] == list(EXPECTED_PANELS), f"{view['id']} panel order mismatch")
            for kind in ("jpg", "svg"):
                path = validate_file_record(view[kind], f"{view['id']} {kind}")
                output_count += 1
                if kind == "jpg":
                    with Image.open(path) as image:
                        require(image.size == (3240, 735), f"{view['id']} JPEG dimensions changed")
                        image.verify()
                else:
                    root = ET.parse(path).getroot()
                    require(root.attrib.get("width") == "3240", f"{view['id']} SVG width changed")
                    require(root.attrib.get("height") == "735", f"{view['id']} SVG height changed")
        require(output_count == 9, "visual output count mismatch")

        require(record["visualEvidence"]["deterministicRerenderPassed"] is True, "deterministic rerender not recorded")
        require(record["applicability"]["physicalAccuracyAt25And75PercentValidated"] is False, "25/75 physical accuracy claimed")
        require(record["applicability"]["thirtySixHourPast12Future24ServiceReady"] is False, "36-hour readiness claimed")
        common_safeguards = (
            "physicalSolverInvoked",
            "additionalPhysicalRunPerformed",
            "automaticRetryPerformed",
            "networkAccessAttempted",
            "publicSimulatorConnected",
            "mainMerged",
            "physicalValidationClaimAllowed",
            "forecastValidationClaimAllowed",
        )
        require_false_safeguards(record["safeguards"], "candidate record", common_safeguards)
        require_false_safeguards(pack_manifest["safeguards"], "pack manifest", common_safeguards)
        require_false_safeguards(browser_validation["safeguards"], "browser validation", common_safeguards)
        require_false_safeguards(map_manifest["safeguards"], "map manifest", common_safeguards)
        require_false_safeguards(source_validation["safeguards"], "source-pack validation", common_safeguards)
        require_false_safeguards(
            record["safeguards"],
            "candidate record",
            ("referenceS03RunPerformed", "existingHybridModulesModified"),
        )
        require_false_safeguards(
            pack_manifest["safeguards"],
            "pack manifest",
            ("referenceS03RunPerformed",),
        )
        require_false_safeguards(
            browser_validation["safeguards"],
            "browser validation",
            ("referenceS03RunPerformed", "existingHybridModulesModified"),
        )
        require_false_safeguards(
            map_manifest["safeguards"],
            "map manifest",
            ("sourceFilesModified",),
        )
        require_false_safeguards(
            source_validation["safeguards"],
            "source-pack validation",
            ("referenceS03RunPerformed",),
        )

        print(
            json.dumps(
                {
                    "status": "passed",
                    "record": RECORD_PATH.relative_to(ROOT).as_posix(),
                    "adoptionRecord": ADOPTION_PATH.relative_to(ROOT).as_posix(),
                    "selectedChoice": "A",
                    "retainedAsInternalCodeCandidate": True,
                    "sourceAnchorCount": 15,
                    "sourcePackByteReconstruction": "passed",
                    "sourcePackLiveReconstruction": "passed",
                    "builderUnsafeOutputNamesRejected": True,
                    "packedAnchorAndMidpointValidation": "passed",
                    "mapAlgebraAndDigestValidation": "passed",
                    "visualOutputCount": output_count,
                    "physicalRunPerformed": False,
                    "publicSimulatorConnected": False,
                    "mainMerged": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (
        ValidationError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        ET.ParseError,
        subprocess.TimeoutExpired,
    ) as error:
        print(
            json.dumps(
                {"status": "failed", "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
