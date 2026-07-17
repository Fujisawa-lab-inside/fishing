#!/usr/bin/env python3
"""Analyze one completed Stage 20 barrage recovery from local artifacts only.

Exit status:
  0  evidence valid and all 20 hour/region comparisons passed
  1  evidence valid but at least one interpolation threshold failed
  2  evidence invalid, incomplete, or otherwise not evaluable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from stage20_barrage_holdout_postrun import (
    NotEvaluableError,
    collect_endpoint_snapshots,
    evaluate_holdout,
    load_json,
    sha256_file,
    validate_heldout_reference,
    validate_recovery_segment,
    validate_region_masks,
    validate_restart_chain,
    validate_run_metadata,
    validate_static_inputs,
    write_json,
    write_worst_hour_fields,
)


DEFAULT_CONTRACT = Path("config/stage20_barrage_holdout_recovery_contract_v1.json")
DEFAULT_OUTPUT = Path("config/stage20_barrage_holdout_recovery_analysis_v1.json")
OUTPUT_SCHEMA = "onga-stage20-barrage-holdout-recovery-postrun-analysis-v1"


def _portable(value: Any, repo_root: Path) -> Any:
    """Make repository paths portable without changing arbitrary text."""

    if isinstance(value, dict):
        return {key: _portable(item, repo_root) for key, item in value.items()}
    if isinstance(value, list):
        return [_portable(item, repo_root) for item in value]
    if isinstance(value, tuple):
        return [_portable(item, repo_root) for item in value]
    if isinstance(value, str):
        prefix = str(repo_root) + "/"
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _base_record(result_root: Path, metadata_path: Path) -> dict[str, Any]:
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "not_evaluable_invalid_or_incomplete_evidence",
        "analysisMode": "offline_local_artifacts_only",
        "identity": {
            "resultRoot": str(result_root),
            "runMetadata": {"path": str(metadata_path)},
        },
        "staticInputValidation": {"passed": False},
        "artifactValidation": {
            "passed": False,
            "expectedSegmentCount": 5,
            "validatedSegmentCount": 0,
            "segments": [],
            "errors": [],
        },
        "restartChainValidation": {"passed": False, "links": []},
        "numericalValidation": {"passed": False, "segments": []},
        "snapshotInventory": {
            "passed": False,
            "expectedEndpointCount": 10,
            "newExpectedCount": 9,
            "retainedExpectedCount": 1,
            "actualEndpointCount": 0,
            "exactBasisHourSetMatched": False,
            "entries": [],
        },
        "heldOutReference": {"passed": False, "expectedSnapshotCount": 5, "validatedSnapshotCount": 0, "entries": []},
        "holdoutEvaluation": {
            "evaluable": False,
            "acceptanceResult": "not_evaluable_not_failed",
            "expectedComparisonCount": 20,
            "evaluatedComparisonCount": 0,
            "reason": "local evidence has not yet been completely validated",
        },
        "derivedArtifacts": {
            "createdThisInvocation": False,
            "mapReadyWorstHourFields": [],
            "mapsRendered": False,
        },
        "diagnostics": [],
        "safeguards": {
            "solverInvoked": False,
            "networkAccessAttempted": False,
            "githubActionsMutationAttempted": False,
            "automaticRetryPerformed": False,
            "additionalPhysicalRunPerformed": False,
            "publicSimulatorConnected": False,
            "physicalValidationClaimAllowed": False,
            "dailyForecastClaimAllowed": False,
        },
    }


def _preflight_output_path(output_path: Path) -> None:
    """Refuse to overwrite anything except an earlier record from this tool."""

    if output_path.is_symlink() or (output_path.exists() and not output_path.is_file()):
        raise NotEvaluableError("E_OUTPUT_LOCATION", "analysis output must be a regular file path, not a symlink or directory", path=str(output_path))
    if output_path.is_file():
        existing = load_json(output_path)
        if existing.get("schema") != OUTPUT_SCHEMA:
            raise NotEvaluableError("E_OUTPUT_LOCATION", "analysis output may only replace an earlier post-run analysis record", path=str(output_path), existingSchema=existing.get("schema"))
    for parent in output_path.resolve(strict=False).parents:
        if (parent / "evidence-manifest.json").is_file():
            raise NotEvaluableError("E_OUTPUT_LOCATION", "analysis output may not be written inside a sealed evidence tree", path=str(output_path), evidenceRoot=str(parent))


def _is_within(path: Path, root: Path) -> bool:
    return path.resolve(strict=False).is_relative_to(root.resolve(strict=False))


def _validate_output_locations(
    *,
    repo_root: Path,
    output_path: Path,
    derived_output_dir: Path,
    metadata_path: Path,
    static: dict[str, Any],
    artifact_roots: list[Path],
    create_derived_fields: bool,
) -> None:
    """Keep diagnostic/derived writes outside every sealed input tree."""

    contract = static["contract"]
    stopped_analysis = load_json(repo_root / contract["stoppedAnalysis"]["path"])
    protected_roots = artifact_roots + [repo_root / item["directory"] for item in contract["retainedInputs"]]
    protected_roots.append(repo_root / stopped_analysis["heldOutReference"]["root"])
    protected_files = {
        metadata_path.resolve(strict=False),
        Path(__file__).resolve(),
        (repo_root / "tools/stage20_barrage_holdout_postrun.py").resolve(strict=False),
        static["contractPath"].resolve(strict=False),
        static["authorizationPath"].resolve(strict=False),
        (repo_root / contract["control"]["gatePath"]).resolve(strict=False),
        (repo_root / contract["control"]["activationPath"]).resolve(strict=False),
    }
    for key in ("sourceContract", "stoppedResult", "stoppedAnalysis"):
        protected_files.add((repo_root / contract[key]["path"]).resolve(strict=False))
    for path in (
        contract["mesh"]["manifest"],
        contract["kernel"]["path"],
        contract["runner"]["path"],
        contract["runner"]["workflowPath"],
        contract["inputs"]["tideCandidate"],
        contract["inputs"]["waterMask"],
        contract["regionalMasks"]["manifest"],
        contract["regionalMasks"]["binary"],
        contract["regionalMasks"]["builder"],
    ):
        protected_files.add((repo_root / path).resolve(strict=False))
    resolved_output = output_path.resolve(strict=False)
    if output_path.is_symlink() or resolved_output in protected_files or any(_is_within(resolved_output, root) for root in protected_roots):
        raise NotEvaluableError("E_OUTPUT_LOCATION", "analysis output may not overwrite or enter a sealed input location", path=str(output_path))
    if create_derived_fields:
        resolved_derived = derived_output_dir.resolve(strict=False)
        if derived_output_dir.is_symlink() or resolved_derived in protected_files or any(_is_within(resolved_derived, root) for root in protected_roots):
            raise NotEvaluableError("E_OUTPUT_LOCATION", "derived output directory may not overwrite or enter a sealed input location", path=str(derived_output_dir))


def analyze(
    *,
    repo_root: Path,
    expected_run_id: int,
    result_root: Path,
    metadata_path: Path,
    contract_path: Path,
    output_path: Path,
    derived_output_dir: Path,
    create_derived_fields: bool,
) -> tuple[dict[str, Any], int]:
    repo_root = repo_root.resolve()
    result_root = result_root if result_root.is_absolute() else repo_root / result_root
    metadata_path = metadata_path if metadata_path.is_absolute() else repo_root / metadata_path
    output_path = output_path if output_path.is_absolute() else repo_root / output_path
    derived_output_dir = derived_output_dir if derived_output_dir.is_absolute() else repo_root / derived_output_dir
    _preflight_output_path(output_path)
    record = _base_record(result_root, metadata_path)
    phase = "static_inputs"
    try:
        expected_analyzer_path = repo_root / "tools/analyze_stage20_barrage_holdout_recovery_result.py"
        if Path(__file__).resolve() != expected_analyzer_path.resolve(strict=False):
            raise NotEvaluableError("E_REPO_ROOT", "--repo-root does not identify the repository containing this analyzer", path=str(repo_root))
        if expected_run_id <= 0:
            raise NotEvaluableError("E_RUN_ID", "explicit run ID must be positive", actual=expected_run_id)
        static = validate_static_inputs(repo_root, contract_path)
        contract = static["contract"]
        authorization = static["authorization"]
        record["staticInputValidation"] = {
            "passed": True,
            "contract": {"path": str(static["contractPath"]), "sha256": static["contractSha256"]},
            "authorization": {"id": authorization["authorizationId"], "path": str(static["authorizationPath"]), "sha256": static["authorizationSha256"]},
            "gateSha256": static["gateSha256"],
            "activationSha256": static["activationSha256"],
            "regionalMasks": static["regionalMasks"],
        }
        analyzer_path = Path(__file__).resolve()
        core_path = repo_root / "tools/stage20_barrage_holdout_postrun.py"
        record["toolchain"] = {
            "analyzer": {"path": str(analyzer_path), "sha256": sha256_file(analyzer_path)},
            "offlineCore": {"path": str(core_path), "sha256": sha256_file(core_path)},
        }
        expected_artifact_names = {f"{job['id']}-{expected_run_id}" for job in contract["jobs"]}
        artifact_roots = [result_root / name for name in sorted(expected_artifact_names)]
        _validate_output_locations(
            repo_root=repo_root,
            output_path=output_path,
            derived_output_dir=derived_output_dir,
            metadata_path=metadata_path,
            static=static,
            artifact_roots=artifact_roots,
            create_derived_fields=create_derived_fields,
        )
        phase = "run_metadata"
        metadata = load_json(metadata_path)
        metadata_sha = sha256_file(metadata_path)
        run = validate_run_metadata(metadata, contract["jobs"])
        if run["runId"] != expected_run_id:
            raise NotEvaluableError(
                "E_RUN_ID",
                "run metadata does not match the explicitly selected run ID",
                expected=expected_run_id,
                actual=run["runId"],
            )
        record["identity"].update(
            {
                **run,
                "authorizationId": authorization["authorizationId"],
                "contract": {"path": str(static["contractPath"]), "sha256": static["contractSha256"]},
                "runMetadata": {"path": str(metadata_path), "sha256": metadata_sha},
            }
        )
        phase = "segment_artifacts"
        if not result_root.is_dir() or result_root.is_symlink():
            raise NotEvaluableError("E_RESULT_ROOT", "local recovery result root is missing or is a symlink", path=str(result_root))
        expected_artifact_names = {f"{job['id']}-{run['runId']}" for job in contract["jobs"]}
        actual_artifact_names = {
            path.name
            for path in result_root.iterdir()
            if path.is_dir() and path.name.endswith(f"-{run['runId']}")
        }
        if actual_artifact_names != expected_artifact_names:
            raise NotEvaluableError(
                "E_ARTIFACT_SET",
                "downloaded recovery artifact directory set does not exactly match the five contracted jobs",
                missing=sorted(expected_artifact_names - actual_artifact_names),
                extra=sorted(actual_artifact_names - expected_artifact_names),
            )
        record["artifactValidation"]["expectedArtifactNames"] = sorted(expected_artifact_names)
        segments = []
        for job in contract["jobs"]:
            artifact_root = result_root / f"{job['id']}-{run['runId']}"
            segment = validate_recovery_segment(
                artifact_root,
                job,
                contract,
                authorization,
                run,
                authorization_sha256=static["authorizationSha256"],
                contract_sha256=static["contractSha256"],
            )
            segments.append(segment)
            record["artifactValidation"]["segments"].append(segment.summary)
            record["artifactValidation"]["validatedSegmentCount"] = len(segments)
        record["artifactValidation"]["passed"] = True
        record["numericalValidation"] = {
            "passed": True,
            "thresholds": {
                "maximumCfl": contract["acceptance"]["maximumCfl"],
                "maximumRelativeMassBalanceError": contract["acceptance"]["maximumRelativeMassBalanceError"],
                "nonFiniteValueCount": 0,
                "negativeDepthCount": 0,
            },
            "segments": [
                {"jobId": segment.job["id"], "simulatedSeconds": segment.summary["simulatedSeconds"], "diagnostics": segment.summary["diagnostics"], "passed": True}
                for segment in segments
            ],
        }
        phase = "restart_chain"
        links = validate_restart_chain(segments)
        record["restartChainValidation"] = {"passed": True, "links": links}
        phase = "endpoint_snapshots"
        endpoints, endpoint_records = collect_endpoint_snapshots(repo_root, contract, segments)
        record["snapshotInventory"] = {
            "passed": True,
            "expectedEndpointCount": 10,
            "newExpectedCount": 9,
            "retainedExpectedCount": 1,
            "actualEndpointCount": len(endpoint_records),
            "exactBasisHourSetMatched": True,
            "entries": endpoint_records,
        }
        phase = "heldout_reference"
        references, reference_record = validate_heldout_reference(repo_root, contract)
        record["heldOutReference"] = {
            "passed": True,
            "expectedSnapshotCount": 5,
            "validatedSnapshotCount": len(references),
            "root": reference_record["root"],
            "evidenceManifest": {
                "path": reference_record["path"],
                "sha256": reference_record["sha256"],
                "fileCount": reference_record["fileCount"],
                "allFileLengthsAndDigestsVerified": reference_record["allFileLengthsAndDigestsVerified"],
            },
            "entries": reference_record["snapshots"],
        }
        phase = "regional_masks"
        masks, mask_record = validate_region_masks(repo_root, contract)
        record["regionalMaskValidation"] = {"passed": True, **mask_record}
        phase = "holdout_metrics"
        evaluation = evaluate_holdout(endpoints, references, masks, contract)
        record["holdoutEvaluation"] = evaluation
        passed = evaluation["acceptanceResult"] == "passed"
        record["status"] = "evaluated_passed_thresholds" if passed else "evaluated_failed_thresholds"
        exit_status = 0 if passed else 1
        if create_derived_fields:
            phase = "derived_fields"
            worst_hour = evaluation["worstMapSelection"]["modelHour"]
            try:
                derived = write_worst_hour_fields(
                    derived_output_dir,
                    worst_hour,
                    endpoints,
                    references[worst_hour],
                    int(contract["mesh"]["cellCount"]),
                )
                record["derivedArtifacts"] = {
                    "createdThisInvocation": True,
                    "selectionConvention": evaluation["worstMapSelection"],
                    "mapReadyWorstHourFields": derived,
                    "mapsRendered": False,
                    "mapRenderingReason": "map-ready fields are prepared; rendering is a separate deterministic presentation step",
                }
            except Exception as error:
                diagnostic = {
                    "phase": phase,
                    "code": "E_DERIVED_WRITE",
                    "message": "the holdout decision is valid, but map-ready derived fields could not be written",
                    "exceptionType": type(error).__name__,
                    "error": str(error),
                }
                record["diagnostics"].append(diagnostic)
                record["derivedArtifacts"] = {
                    "createdThisInvocation": False,
                    "selectionConvention": evaluation["worstMapSelection"],
                    "mapReadyWorstHourFields": [],
                    "mapsRendered": False,
                    "error": diagnostic,
                }
        else:
            record["derivedArtifacts"]["reason"] = "disabled_by_cli"
    except NotEvaluableError as error:
        if error.code == "E_OUTPUT_LOCATION":
            raise
        diagnostic = {"phase": phase, **error.as_record()}
        record["diagnostics"].append(diagnostic)
        record["artifactValidation"]["errors"].append(diagnostic)
        record["holdoutEvaluation"] = {
            "evaluable": False,
            "acceptanceResult": "not_evaluable_not_failed",
            "expectedComparisonCount": 20,
            "evaluatedComparisonCount": 0,
            "reason": error.message,
            "diagnosticCode": error.code,
        }
        record["status"] = "not_evaluable_invalid_or_incomplete_evidence"
        exit_status = 2
    except Exception as error:  # Preserve a diagnostic JSON even for an implementation/I/O defect.
        diagnostic = {"phase": phase, "code": "E_INTERNAL", "message": str(error), "exceptionType": type(error).__name__}
        record["diagnostics"].append(diagnostic)
        record["artifactValidation"]["errors"].append(diagnostic)
        record["holdoutEvaluation"] = {
            "evaluable": False,
            "acceptanceResult": "not_evaluable_not_failed",
            "expectedComparisonCount": 20,
            "evaluatedComparisonCount": 0,
            "reason": "the offline analyzer encountered an internal or output error",
            "diagnosticCode": "E_INTERNAL",
        }
        record["status"] = "not_evaluable_invalid_or_incomplete_evidence"
        exit_status = 2
    portable = _portable(record, repo_root)
    write_json(output_path, portable)
    return portable, exit_status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--run-id", type=int, required=True, help="exact GitHub Actions run ID")
    parser.add_argument("--result-root", help="directory containing the five downloaded artifact directories")
    parser.add_argument("--run-metadata", help="normalized, locally saved run metadata JSON")
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--derived-output-dir")
    parser.add_argument("--no-derived-fields", action="store_true", help="validate and compare without writing map-ready NPZ files")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    default_root = Path(f"docs/results/stage20-barrage-holdout-recovery-{args.run_id}")
    result_root = Path(args.result_root) if args.result_root else default_root
    metadata_path = Path(args.run_metadata) if args.run_metadata else result_root / "run-metadata.json"
    derived_dir = Path(args.derived_output_dir) if args.derived_output_dir else result_root / "postrun"
    try:
        record, exit_status = analyze(
            repo_root=repo_root,
            expected_run_id=args.run_id,
            result_root=result_root,
            metadata_path=metadata_path,
            contract_path=Path(args.contract),
            output_path=Path(args.output),
            derived_output_dir=derived_dir,
            create_derived_fields=not args.no_derived_fields,
        )
    except NotEvaluableError as error:
        record = {
            "schema": OUTPUT_SCHEMA,
            "status": "not_evaluable_invalid_or_incomplete_evidence",
            "analysisMode": "offline_local_artifacts_only",
            "analysisOutputWritten": False,
            "holdoutEvaluation": {
                "evaluable": False,
                "acceptanceResult": "not_evaluable_not_failed",
                "reason": error.message,
                "diagnosticCode": error.code,
            },
            "diagnostics": [error.as_record()],
            "safeguards": {
                "solverInvoked": False,
                "networkAccessAttempted": False,
                "githubActionsMutationAttempted": False,
                "automaticRetryPerformed": False,
                "additionalPhysicalRunPerformed": False,
            },
        }
        exit_status = 2
    print(json.dumps(record, ensure_ascii=False, indent=2))
    raise SystemExit(exit_status)


if __name__ == "__main__":
    main()
