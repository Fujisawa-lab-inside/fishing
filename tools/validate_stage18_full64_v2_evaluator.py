#!/usr/bin/env python3
"""Metadata-only validation for the Stage 18 v2 evaluator and decision SVG."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from evaluate_stage18_full64_v2 import (
    AUTHORIZATION_SCHEMA,
    AUTHORIZATION_SCOPE,
    CASE_COUNT,
    CELL_COUNT,
    CLASSIFICATION,
    COMPARISON_BASIS,
    ENSEMBLE_SHA256,
    FIELDS_SCHEMA,
    MESH_PACKAGE_SHA256,
    REPORT_SCHEMA,
    ValidationError,
    evaluate_evidence,
    load_json_object,
    sha256_file,
    validate_contract,
    write_json_atomic,
)
from render_stage18_full64_decision_v2 import MAPS, render_files
from aggregate_stage18_full64_v2 import (
    BUNDLE_NAMES,
    build_cell_raster,
    compute_statistics,
    render_map,
    validate_reported_field_path,
    write_bundle_atomic,
)


ONE_PIXEL_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def digest_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def fixtures(contract_path: Path):
    contract = load_json_object(contract_path)
    validate_contract(contract)
    contract_digest = sha256_file(contract_path)
    authorization = {
        'schema': AUTHORIZATION_SCHEMA,
        'authorizationId': 'fixture-stage18-v2-one-time',
        'authorized': True,
        'oneTime': True,
        'approvedBy': 'Ryusuke Fujisawa',
        'approvedDate': '2026-07-14',
        'issuedAtUtc': '2026-07-14T00:00:00Z',
        'notAfterUtc': '2026-07-15T00:00:00Z',
        'sourceStatement': (
            '承認済み橋下補正v2上で、この判断資料に示された64条件×500ステップを、'
            '承認後24時間以内に一回限りの数値安定性確認として実行してよい。'
        ),
        'scope': AUTHORIZATION_SCOPE,
        'decisionImage': {
            'path': 'docs/visuals/stage18-v2-execution-decision.svg',
            'sha256': '1' * 64,
        },
        'executionContract': {
            'path': 'config/stage18_full64_execution_contract_v2.json',
            'sha256': contract_digest,
        },
        'reviewedCodeCommit': '2' * 40,
        'geometry': copy.deepcopy(contract['geometry']),
        'meshExpected': copy.deepcopy(contract['meshExpected']),
        'ensembleExpected': copy.deepcopy(contract['ensembleExpected']),
        'run': copy.deepcopy(contract['run']),
        'acceptance': copy.deepcopy(contract['acceptance']),
        'safeguards': {
            'automaticAdditionalRunsAllowed': False,
            'automaticRetryAllowed': False,
            'inferredParametersAreObservations': False,
            'physicalValidationClaimAllowed': False,
            'sensitivityClaimAllowed': False,
            'publicSimulatorConnectionAllowed': False,
            'legacyFlowCalculationMayChange': False,
            'failedCasesMayBeImputed': False,
        },
    }
    authorization_digest = digest_json(authorization)
    case_ids = [f'stage18-{index:04d}' for index in range(1, CASE_COUNT + 1)]
    field_digest = '3' * 64
    mesh_summary_digest = '4' * 64
    protected = {
        path: hashlib.sha256(path.encode('utf-8')).hexdigest()
        for path in contract['protectedPaths']
    }
    diagnostics = [{
        'caseId': case_id,
        'status': 'completed',
        'wallSeconds': 1.0,
        'stepsCompleted': contract['run']['maxStepsPerCase'],
        'simulatedTimeSeconds': 10.0,
        'minimumTimeStepSeconds': 0.01,
        'maximumTimeStepSeconds': 0.02,
        'massBalanceError': 1e-12,
        'maxCfl': 0.12,
        'minimumDepthM': 1.0,
    } for case_id in case_ids]
    report = {
        'schema': REPORT_SCHEMA,
        'classification': CLASSIFICATION,
        'geometry': copy.deepcopy(contract['geometry']),
        'ensembleSeed': contract['run']['ensembleSeed'],
        'requestedCaseCount': CASE_COUNT,
        'attemptedCaseIds': case_ids,
        'completedCaseCount': CASE_COUNT,
        'failedCaseCount': 0,
        'wallSeconds': 600.0,
        'caseWallSecondsTotal': 64.0,
        'peakResidentMemoryMiB': 512.0,
        'maxCfl': 0.12,
        'maxAbsoluteMassBalanceError': 1e-12,
        'minimumDepthM': 1.0,
        'minimumSimulatedTimeSeconds': 10.0,
        'maximumSimulatedTimeSeconds': 10.0,
        'nanCount': 0,
        'negativeDepthCount': 0,
        'comparisonBasis': COMPARISON_BASIS,
        'parameterCoverage': copy.deepcopy(contract['parameterCoverage']),
        'failures': [],
        'caseDiagnostics': diagnostics,
        'inputDigests': {
            'executionContractSha256': contract_digest,
            'authorizationSha256': authorization_digest,
            'meshSha256': MESH_PACKAGE_SHA256,
            'meshSummarySha256': mesh_summary_digest,
            'ensembleSha256': ENSEMBLE_SHA256,
        },
        'fieldArtifact': {
            'path': 'fixture/full64-fields.npz',
            'sha256': field_digest,
            'shape': {'caseCount': CASE_COUNT, 'cellCount': CELL_COUNT},
            'dtype': 'float64',
        },
        'safeguards': copy.deepcopy(authorization['safeguards']),
        'stopPolicy': copy.deepcopy(contract['stopPolicy']),
        'protectedSurfaceHashesBefore': protected,
        'protectedSurfaceHashesAfter': copy.deepcopy(protected),
        'protectedSurfaceHashesUnchanged': True,
    }
    fields = {
        'sha256': field_digest,
        'schema': FIELDS_SCHEMA,
        'shape': {'caseCount': CASE_COUNT, 'cellCount': CELL_COUNT},
        'dtype': 'float64',
        'caseIds': case_ids,
        'metrics': {
            'maxCfl': 0.12,
            'maxAbsoluteMassBalanceError': 1e-12,
            'minimumDepthM': 1.0,
        },
        'metadata': {
            'executionContractSha256': contract_digest,
            'authorizationSha256': authorization_digest,
            'meshSha256': MESH_PACKAGE_SHA256,
            'meshSummarySha256': mesh_summary_digest,
            'ensembleSha256': ENSEMBLE_SHA256,
            'comparisonBasis': COMPARISON_BASIS,
        },
    }
    return contract, authorization, report, fields, contract_digest, authorization_digest


def evaluate_fixture(contract, authorization, report, fields, contract_digest, authorization_digest):
    return evaluate_evidence(
        contract,
        authorization,
        report,
        fields,
        contract_digest=contract_digest,
        authorization_digest=authorization_digest,
        report_digest=digest_json(report),
    )


def expect_rejected(label, contract, authorization, report, fields, contract_digest, authorization_digest):
    try:
        evaluate_fixture(contract, authorization, report, fields, contract_digest, authorization_digest)
    except (ValidationError, KeyError, TypeError):
        return
    raise RuntimeError(f'negative fixture unexpectedly passed: {label}')


def require_failed(label, contract, authorization, report, fields, contract_digest, authorization_digest):
    evaluation = evaluate_fixture(contract, authorization, report, fields, contract_digest, authorization_digest)
    require(evaluation['passed'] is False, f'negative threshold unexpectedly passed: {label}')
    require(evaluation['status'] == 'failed', f'negative threshold status changed: {label}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-numeric-fixture', action='store_true')
    args = parser.parse_args()
    contract_path = Path('config/stage18_full64_execution_contract_v2.json')
    base = fixtures(contract_path)
    contract, authorization, report, fields, contract_digest, authorization_digest = base
    evaluation = evaluate_fixture(*base)
    require(evaluation['passed'] is True, 'positive metadata fixture did not pass')
    require(evaluation['fieldArtifact'] == {
        'shape': {'caseCount': CASE_COUNT, 'cellCount': CELL_COUNT},
        'dtype': 'float64',
    }, 'field shape evidence changed')
    require(evaluation['provenance']['executionContractSha256'] == contract_digest,
            'contract provenance changed')
    require(evaluation['provenance']['authorizationSha256'] == authorization_digest,
            'authorization provenance changed')

    signed_report = copy.deepcopy(report)
    for diagnostic in signed_report['caseDiagnostics']:
        diagnostic['massBalanceError'] = -1e-12
    signed_evaluation = evaluate_fixture(
        contract,
        authorization,
        signed_report,
        fields,
        contract_digest,
        authorization_digest,
    )
    require(signed_evaluation['passed'] is True,
            'valid signed mass-balance errors were rejected')

    bad_contract = copy.deepcopy(contract)
    bad_contract['geometry']['metricMeshCellCount'] = CELL_COUNT + 1
    expect_rejected('geometry cell count', bad_contract, authorization, report, fields,
                    contract_digest, authorization_digest)

    bad_contract = copy.deepcopy(contract)
    bad_contract['acceptance']['maxCflMax'] = 1.0
    expect_rejected('weakened acceptance', bad_contract, authorization, report, fields,
                    contract_digest, authorization_digest)

    bad_authorization = copy.deepcopy(authorization)
    bad_authorization['executionContract']['sha256'] = 'f' * 64
    expect_rejected('authorization contract binding', contract, bad_authorization, report, fields,
                    contract_digest, authorization_digest)

    bad_authorization = copy.deepcopy(authorization)
    bad_authorization['scope'] = 'broader-scope'
    expect_rejected('authorization scope', contract, bad_authorization, report, fields,
                    contract_digest, authorization_digest)

    bad_authorization = copy.deepcopy(authorization)
    bad_authorization['sourceStatement'] = '進めてください'
    expect_rejected('authorization visual source statement', contract, bad_authorization, report, fields,
                    contract_digest, authorization_digest)

    bad_authorization = copy.deepcopy(authorization)
    bad_authorization['decisionImage']['path'] = 'docs/visuals/other.svg'
    expect_rejected('authorization decision-image path', contract, bad_authorization, report, fields,
                    contract_digest, authorization_digest)

    bad_authorization = copy.deepcopy(authorization)
    bad_authorization['notAfterUtc'] = '2026-07-15T00:00:01Z'
    expect_rejected('authorization validity longer than 24 hours', contract, bad_authorization, report, fields,
                    contract_digest, authorization_digest)

    bad_authorization = copy.deepcopy(authorization)
    bad_authorization['issuedAtUtc'] = '2026-07-14 00:00:00Z'
    expect_rejected('authorization validity timestamp format', contract, bad_authorization, report, fields,
                    contract_digest, authorization_digest)

    bad_report = copy.deepcopy(report)
    bad_report['inputDigests']['authorizationSha256'] = 'f' * 64
    expect_rejected('report authorization binding', contract, authorization, bad_report, fields,
                    contract_digest, authorization_digest)

    bad_report = copy.deepcopy(report)
    bad_report['fieldArtifact']['sha256'] = 'f' * 64
    expect_rejected('report field binding', contract, authorization, bad_report, fields,
                    contract_digest, authorization_digest)

    bad_fields = copy.deepcopy(fields)
    bad_fields['metadata']['executionContractSha256'] = 'f' * 64
    expect_rejected('field contract binding', contract, authorization, report, bad_fields,
                    contract_digest, authorization_digest)

    bad_fields = copy.deepcopy(fields)
    bad_fields['shape']['cellCount'] = CELL_COUNT - 1
    expect_rejected('field shape', contract, authorization, report, bad_fields,
                    contract_digest, authorization_digest)

    bad_report = copy.deepcopy(report)
    bad_report['maxCfl'] = 0.13
    expect_rejected('field metric consistency', contract, authorization, bad_report, fields,
                    contract_digest, authorization_digest)

    failed_report = copy.deepcopy(report)
    failed_report['completedCaseCount'] = CASE_COUNT - 1
    failed_report['failedCaseCount'] = 1
    failed_report['failures'] = [{'caseId': failed_report['attemptedCaseIds'][-1], 'reason': 'fixture'}]
    failed_report['caseDiagnostics'][-1] = {
        'caseId': failed_report['attemptedCaseIds'][-1],
        'status': 'failed',
        'wallSeconds': 1.0,
        'reason': 'fixture',
    }
    require_failed('case failure', contract, authorization, failed_report, fields,
                   contract_digest, authorization_digest)

    for label, key, value in (
        ('NaN', 'nanCount', 1),
        ('negative depth', 'negativeDepthCount', 1),
        ('wall time', 'wallSeconds', 3600.01),
        ('memory', 'peakResidentMemoryMiB', 8192.01),
    ):
        changed = copy.deepcopy(report)
        changed[key] = value
        require_failed(label, contract, authorization, changed, fields,
                       contract_digest, authorization_digest)

    changed_report = copy.deepcopy(report)
    changed_fields = copy.deepcopy(fields)
    changed_report['maxCfl'] = 0.95001
    changed_fields['metrics']['maxCfl'] = 0.95001
    require_failed('CFL', contract, authorization, changed_report, changed_fields,
                   contract_digest, authorization_digest)

    changed_report = copy.deepcopy(report)
    changed_fields = copy.deepcopy(fields)
    changed_report['maxAbsoluteMassBalanceError'] = 1.0001e-8
    changed_fields['metrics']['maxAbsoluteMassBalanceError'] = 1.0001e-8
    require_failed('mass balance', contract, authorization, changed_report, changed_fields,
                   contract_digest, authorization_digest)

    changed = copy.deepcopy(report)
    first_path = contract['protectedPaths'][0]
    changed['protectedSurfaceHashesAfter'][first_path] = 'f' * 64
    changed['protectedSurfaceHashesUnchanged'] = False
    require_failed('protected surface', contract, authorization, changed, fields,
                   contract_digest, authorization_digest)

    with tempfile.TemporaryDirectory(prefix='stage18-full64-v2-evaluator-') as temporary:
        root = Path(temporary)
        atomic_path = root / 'evaluation.json'
        write_json_atomic(atomic_path, evaluation)
        original = atomic_path.read_bytes()
        try:
            write_json_atomic(atomic_path, {'replaced': True})
        except ValidationError:
            pass
        else:
            raise RuntimeError('atomic writer replaced an existing output')
        require(atomic_path.read_bytes() == original, 'atomic writer changed existing output')

        report_path = root / 'full64-report.json'
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        rendered_evaluation = evaluate_evidence(
            contract,
            authorization,
            report,
            fields,
            contract_digest=contract_digest,
            authorization_digest=authorization_digest,
            report_digest=sha256_file(report_path),
        )
        evaluation_path = root / 'full64-evaluation.json'
        evaluation_path.write_text(json.dumps(rendered_evaluation, ensure_ascii=False), encoding='utf-8')
        map_dir = root / 'maps'
        map_dir.mkdir()
        for filename, _ in MAPS:
            (map_dir / filename).write_bytes(ONE_PIXEL_PNG)
        manifest = {
            'schema': 'onga-stage18-full64-visual-manifest-v2',
            'status': 'generated',
            'sourceCaseCount': CASE_COUNT,
            'cellCount': CELL_COUNT,
            'comparisonBasis': COMPARISON_BASIS,
            'sources': {
                'executionContractSha256': contract_digest,
                'authorizationSha256': authorization_digest,
                'runReportSha256': sha256_file(report_path),
                'fieldArtifactSha256': fields['sha256'],
                'evaluationSha256': sha256_file(evaluation_path),
                'meshSha256': MESH_PACKAGE_SHA256,
                'meshSummarySha256': report['inputDigests']['meshSummarySha256'],
                'ensembleSha256': ENSEMBLE_SHA256,
                'statisticsSha256': '5' * 64,
                'statisticsSummarySha256': '6' * 64,
            },
            'outputs': {
                filename: {
                    'mediaType': 'image/png',
                    'sha256': sha256_file(map_dir / filename),
                    'units': 'fraction',
                    'paletteRgb': [[247, 242, 224], [143, 205, 181], [37, 139, 111], [6, 78, 59]],
                    'dataMinimum': 0.0,
                    'dataMaximum': 1.0,
                    'colorScaleMinimum': 0.0,
                    'colorScaleMaximum': 1.0,
                }
                for filename, _ in MAPS
            },
            'visualization': {
                'representedCellCount': CELL_COUNT,
                'coverageFraction': 1.0,
            },
        }
        manifest_path = root / 'full64-visual-manifest.json'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')

        pass_svg = root / 'pass.svg'
        pass_state = render_files(
            contract_path, report_path, evaluation_path, map_dir, pass_svg,
            manifest_path=manifest_path,
        )
        require(pass_state['passed'] is True, 'complete decision fixture did not render PASS')
        pass_text = pass_svg.read_text(encoding='utf-8')
        ET.fromstring(pass_text)
        for expected in (
            '判定: PASS / RESULT: PASS',
            '64 / 64',
            'NaN / 負の水深',
            'CFL',
            '質量収支 / Mass balance',
            '実行時間 / Wall time',
            'メモリ / Memory',
            '5地図の確認 / Five-map package: 5 / 5',
            '見る点: 空白、筋状ノイズ、孤立した極端値、流向サンプル不足',
            '人が判断すること / Human decision',
            '低 0  →  高 1',
            '物理的に正しいこと、観測との一致、追加計算の許可は示しません。',
        ):
            require(expected in pass_text, f'PASS decision SVG is missing: {expected}')
        require(pass_text.count('data:image/png;base64,') == len(MAPS),
                'PASS decision SVG does not embed all five inspected maps')

        incomplete_map_dir = root / 'incomplete-maps'
        incomplete_map_dir.mkdir()
        for filename, _ in MAPS[:-1]:
            (incomplete_map_dir / filename).write_bytes(ONE_PIXEL_PNG)
        stop_svg = root / 'stop.svg'
        stop_state = render_files(
            contract_path, report_path, evaluation_path, incomplete_map_dir, stop_svg,
            manifest_path=manifest_path,
        )
        require(stop_state['passed'] is False, 'missing-map fixture did not render STOP')
        stop_text = stop_svg.read_text(encoding='utf-8')
        ET.fromstring(stop_text)
        require('STOP — 結果として使用不可' in stop_text, 'STOP banner missing')
        require('5地図の確認 / Five-map package: 4 / 5' in stop_text, 'map count missing')
        require('自動で再実行しないでください' in stop_text, 'no-rerun warning missing')

        partial_progress = {
            'schema': 'onga-stage18-full64-progress-v2',
            'status': 'running',
            'completedCaseCount': 16,
            'failedCaseCount': 0,
            'wallSeconds': 120.0,
            'peakResidentMemoryMiB': 256.0,
            'caseDiagnostics': report['caseDiagnostics'][:16],
        }
        partial_progress_path = root / 'partial-progress.json'
        partial_progress_path.write_text(json.dumps(partial_progress), encoding='utf-8')
        partial_svg = root / 'partial.svg'
        partial_state = render_files(
            contract_path,
            root / 'missing-report.json',
            root / 'missing-evaluation.json',
            incomplete_map_dir,
            partial_svg,
            partial_progress_path,
        )
        require(partial_state['passed'] is False, 'partial fixture did not render STOP')
        require('16 / 64' in partial_svg.read_text(encoding='utf-8'), 'partial completion count missing')

        pass_digest = sha256_file(pass_svg)
        try:
            render_files(
                contract_path, report_path, evaluation_path, map_dir, pass_svg,
                manifest_path=manifest_path,
            )
        except ValidationError:
            pass
        else:
            raise RuntimeError('renderer replaced an existing SVG')
        require(sha256_file(pass_svg) == pass_digest, 'renderer changed existing SVG')

        bundle_dir = root / 'atomic-bundle'
        bundle_payloads = {name: f'fixture:{name}'.encode('utf-8') for name in BUNDLE_NAMES}
        write_bundle_atomic(bundle_dir, bundle_payloads)
        require({path.name for path in bundle_dir.iterdir()} == BUNDLE_NAMES,
                'atomic map/statistics bundle file set changed')
        original_bundle = {path.name: path.read_bytes() for path in bundle_dir.iterdir()}
        try:
            write_bundle_atomic(bundle_dir, {name: b'replaced' for name in BUNDLE_NAMES})
        except ValidationError:
            pass
        else:
            raise RuntimeError('bundle writer replaced an existing directory')
        require({path.name: path.read_bytes() for path in bundle_dir.iterdir()} == original_bundle,
                'bundle writer changed an existing directory')

        numeric_fixture_executed = False
        try:
            import numpy as np
            import rasterio  # noqa: F401
        except ModuleNotFoundError as error:
            if args.require_numeric_fixture:
                raise RuntimeError('numeric/raster fixture dependencies are unavailable') from error
        else:
            numeric_fixture_executed = True
            depth = np.ones((4, 2), dtype=np.float64)
            velocity_u = np.array([
                [-1.0, 0.0], [-1.0, 0.0], [-1.0, 0.0], [-1.0, 0.1],
            ], dtype=np.float64)
            velocity_v = np.array([
                [0.01, 0.0], [-0.01, 0.0], [0.01, 0.0], [-0.01, 0.0],
            ], dtype=np.float64)
            statistics = compute_statistics(depth, velocity_u, velocity_v)
            require(statistics['water_depth_median_m'].shape == (2,), 'small depth statistic shape changed')
            require(statistics['flow_direction_agreement_fraction'][0] > 0.999,
                    'wrapped direction agreement changed')
            require(int(statistics['active_direction_sample_count'][1]) == 1,
                    'small direction support count changed')
            require(statistics['direction_sample_support_fraction'][1] == 0.25,
                    'small direction support fraction changed')

            vertices = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
            triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
            grid, _, coverage = build_cell_raster(vertices, triangles, width=128, height=128)
            require(coverage['representedCellCount'] == 2 and coverage['coverageFraction'] == 1.0,
                    'small raster coverage changed')
            require(coverage['squarePixels'] is True, 'small raster pixels are not square')
            require(coverage['rasterization'] ==
                    'deterministic_triangle_cell_index_center_sample_square_pixel',
                    'small rasterization method changed')
            require(abs(coverage['pixelSizeLocalM'] - (1.05 / 128)) < 1e-15,
                    'small raster pixel size changed')
            require(coverage['boundsExpansionLocalM'] == {'xTotal': 0.0, 'yTotal': 0.0},
                    'square small fixture unexpectedly expanded bounds')
            png, metadata = render_map(
                grid,
                np.array([0.0, 1.0], dtype=np.float64),
                ((220, 247, 246), (107, 207, 211), (42, 130, 186), (8, 48, 107)),
                fixed_range=(0.0, 1.0),
            )
            require(png.startswith(b'\x89PNG\r\n\x1a\n'), 'small map PNG signature changed')
            require(metadata['excludedCellCount'] == 0, 'small map exclusion count changed')

            original_fields = root / 'original' / 'full64-fields.npz'
            relocated_fields = root / 'downloaded' / 'full64-fields.npz'
            validate_reported_field_path(
                str(original_fields), relocated_fields, allow_relocated_fields=True,
            )
            rejected_field_paths = 0
            for supplied, allow_relocated in (
                (relocated_fields, False),
                (root / 'downloaded' / 'renamed-fields.npz', True),
            ):
                try:
                    validate_reported_field_path(
                        str(original_fields), supplied,
                        allow_relocated_fields=allow_relocated,
                    )
                except ValidationError:
                    rejected_field_paths += 1
            require(rejected_field_paths == 2,
                    'field relocation path policy did not fail closed')

    print(json.dumps({
        'schema': 'onga-stage18-full64-v2-evaluator-validation-v1',
        'status': 'passed',
        'caseCount': CASE_COUNT,
        'cellCount': CELL_COUNT,
        'npzFixtureCreated': False,
        'smallNumericFixtureExecuted': numeric_fixture_executed,
        'verified': [
            'contract-authorization-report-field digest chain',
            'exact visual authorization statement and decision-image path',
            'authorization timestamp format and maximum 24-hour validity',
            '64 by 50129 field metadata contract',
            'all numerical acceptance thresholds',
            'protected public and legacy surfaces',
            'atomic evaluation output',
            'PASS and fail-closed STOP decision SVGs',
            'five-map presence gate',
            'atomic statistics and five-map bundle publication',
            'small numerical statistics and raster fixture when dependencies are available',
            'square-pixel raster bounds preserve complete cell coverage',
            'v3 checkpoint field relocation preserves the fixed filename while v2 stays strict',
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
