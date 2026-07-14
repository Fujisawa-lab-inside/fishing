#!/usr/bin/env python3
"""Render one fail-closed decision SVG for a corrected-geometry full64 result."""

from __future__ import annotations

import argparse
import base64
import html
import json
import math
import os
from pathlib import Path
from typing import Any

from evaluate_stage18_full64_v2 import (
    CASE_COUNT,
    CELL_COUNT,
    CONTRACT_SCHEMA,
    ENSEMBLE_SHA256,
    EVALUATION_SCHEMA,
    EXPECTED_ACCEPTANCE,
    MESH_PACKAGE_SHA256,
    REPORT_SCHEMA,
    ValidationError,
    sha256_file,
    validate_contract,
)


MAPS = (
    ('full64-depth-median.png', '水深中央値 / Median water depth'),
    ('full64-velocity-median.png', '流速中央値 / Median velocity'),
    ('full64-wet-probability.png', '湿潤確率 / Wet probability'),
    ('full64-direction-agreement.png', '流向一致度 / Direction agreement'),
    ('full64-direction-support.png', '流向サンプル率 / Direction sample support'),
)
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_PNG_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024


def xml(value: Any) -> str:
    return html.escape(str(value), quote=True)


def load_optional_json(path: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    candidate = Path(path)
    try:
        if candidate.is_symlink() or not candidate.is_file():
            return None, f'{candidate.name} is missing'
        if candidate.stat().st_size > MAX_JSON_BYTES:
            return None, f'{candidate.name} is too large'
        value = json.loads(
            candidate.read_text(encoding='utf-8'),
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f'nonstandard JSON constant: {constant}')
            ),
        )
        if not isinstance(value, dict):
            return None, f'{candidate.name} is not a JSON object'
        return value, None
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None, f'{candidate.name} is malformed'


def safe_number(value: Any, *, nonnegative: bool = True) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0):
        return None
    return result


def safe_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= CASE_COUNT:
        return value
    return None


def safe_anomaly_count(value: Any) -> int | None:
    maximum = CASE_COUNT * CELL_COUNT
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum:
        return value
    return None


def load_valid_png(path: Path) -> bytes | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        size = path.stat().st_size
        if size <= len(PNG_SIGNATURE) or size > MAX_PNG_BYTES:
            return None
        payload = path.read_bytes()
        return payload if payload.startswith(PNG_SIGNATURE) else None
    except OSError:
        return None


def valid_png(path: Path) -> bool:
    return load_valid_png(path) is not None


def format_value(value: float | None, kind: str = 'plain') -> str:
    if value is None:
        return '—'
    if kind == 'mass':
        return f'{value:.3e}'
    if kind == 'seconds':
        return f'{value:,.1f} s'
    if kind == 'memory':
        return f'{value:,.1f} MiB'
    return f'{value:.4g}'


def collect_state(
    contract_path: str | Path,
    report_path: str | Path,
    evaluation_path: str | Path,
    map_dir: str | Path,
    progress_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []

    contract, contract_error = load_optional_json(contract_path)
    if contract_error:
        reasons.append('実行契約を確認できません / execution contract unavailable')
    else:
        try:
            validate_contract(contract)
        except (ValidationError, KeyError, TypeError):
            reasons.append('実行契約が一致しません / execution contract mismatch')
            contract = None
    limits = dict(contract.get('acceptance', EXPECTED_ACCEPTANCE)) if contract else dict(EXPECTED_ACCEPTANCE)

    report, report_error = load_optional_json(report_path)
    if report_error:
        reasons.append('計算レポートが未作成です / run report unavailable')
    elif report.get('schema') != REPORT_SCHEMA:
        reasons.append('計算レポートの形式が一致しません / run report schema mismatch')
        report = None

    progress = None
    if progress_path is not None:
        progress, progress_error = load_optional_json(progress_path)
        if progress_error:
            reasons.append('途中経過を確認できません / progress unavailable')
        elif progress.get('schema') != 'onga-stage18-full64-progress-v2':
            reasons.append('途中経過の形式が一致しません / progress schema mismatch')
            progress = None

    evaluation, evaluation_error = load_optional_json(evaluation_path)
    if evaluation_error:
        reasons.append('評価が未完了です / evaluation unavailable')
    elif evaluation.get('schema') != EVALUATION_SCHEMA:
        reasons.append('評価の形式が一致しません / evaluation schema mismatch')
        evaluation = None

    contract_digest = None
    report_digest = None
    try:
        if contract is not None:
            contract_digest = sha256_file(contract_path)
        if report is not None:
            report_digest = sha256_file(report_path)
    except OSError:
        reasons.append('入力の照合に失敗しました / source digest unavailable')

    provenance_ok = False
    if evaluation is not None and contract_digest and report_digest:
        provenance = evaluation.get('provenance')
        report_inputs = report.get('inputDigests') if report else None
        field_artifact = report.get('fieldArtifact') if report else None
        provenance_ok = (
            isinstance(provenance, dict)
            and isinstance(report_inputs, dict)
            and isinstance(field_artifact, dict)
            and provenance.get('executionContractSha256') == contract_digest
            and provenance.get('runReportSha256') == report_digest
            and provenance.get('authorizationSha256') == report_inputs.get('authorizationSha256')
            and provenance.get('fieldArtifactSha256') == field_artifact.get('sha256')
            and provenance.get('meshSha256') == MESH_PACKAGE_SHA256
            and provenance.get('meshSummarySha256') == report_inputs.get('meshSummarySha256')
            and provenance.get('ensembleSha256') == ENSEMBLE_SHA256
        )
        if not provenance_ok:
            reasons.append('評価と入力の対応が一致しません / evaluation provenance mismatch')

    evidence = report or progress
    completed = safe_count(evidence.get('completedCaseCount')) if evidence else None
    failed = safe_count(evidence.get('failedCaseCount')) if evidence else None
    nan_count = safe_anomaly_count(report.get('nanCount')) if report else None
    negative_count = safe_anomaly_count(report.get('negativeDepthCount')) if report else None
    diagnostics = evidence.get('caseDiagnostics') if isinstance(evidence, dict) else None
    diagnostics = diagnostics if isinstance(diagnostics, list) else []
    if report is None and diagnostics:
        diagnostic_nan = [
            safe_anomaly_count(item.get('nanCount'))
            for item in diagnostics if isinstance(item, dict)
        ]
        diagnostic_negative = [
            safe_anomaly_count(item.get('negativeDepthCount'))
            for item in diagnostics if isinstance(item, dict)
        ]
        if any(value is not None for value in diagnostic_nan):
            nan_count = sum(value or 0 for value in diagnostic_nan)
        if any(value is not None for value in diagnostic_negative):
            negative_count = sum(value or 0 for value in diagnostic_negative)
    diagnostic_cfl = [
        value for item in diagnostics if isinstance(item, dict)
        for value in [safe_number(item.get('maxCfl'))] if value is not None
    ]
    diagnostic_mass = [
        abs(value) for item in diagnostics if isinstance(item, dict)
        for value in [safe_number(item.get('massBalanceError'), nonnegative=False)] if value is not None
    ]
    metrics = {
        'maxCfl': safe_number(report.get('maxCfl')) if report else (max(diagnostic_cfl) if diagnostic_cfl else None),
        'maxAbsoluteMassBalanceError': (
            safe_number(report.get('maxAbsoluteMassBalanceError'))
            if report else (max(diagnostic_mass) if diagnostic_mass else None)
        ),
        'wallSeconds': safe_number(evidence.get('wallSeconds')) if evidence else None,
        'peakResidentMemoryMiB': safe_number(evidence.get('peakResidentMemoryMiB')) if evidence else None,
    }

    if report is not None and (completed != CASE_COUNT or failed != 0):
        reasons.append('64ケースがすべて完了していません / 64 cases not completed')
    evaluation_passed = (
        evaluation is not None
        and evaluation.get('passed') is True
        and evaluation.get('status') == 'passed'
        and isinstance(evaluation.get('checks'), dict)
        and bool(evaluation['checks'])
        and all(value is True for value in evaluation['checks'].values())
    )
    if evaluation is not None and not evaluation_passed:
        reasons.append('数値受入条件が不合格です / numerical acceptance failed')

    directory = Path(map_dir)
    map_status = []
    map_previews = {}
    for filename, label in MAPS:
        payload = load_valid_png(directory / filename)
        present = payload is not None
        map_status.append((filename, label, present))
        map_previews[filename] = {
            'dataUri': (
                f'data:image/png;base64,{base64.b64encode(payload).decode("ascii")}'
                if payload is not None else None
            ),
            'metadata': {},
        }
    present_map_count = sum(present for _, _, present in map_status)
    if present_map_count != len(MAPS):
        reasons.append('5枚の地図が揃っていません / five-map package incomplete')

    manifest = None
    manifest_ok = False
    if manifest_path is None:
        reasons.append('地図の証明書がありません / visual manifest unavailable')
    else:
        manifest, manifest_error = load_optional_json(manifest_path)
        if manifest_error:
            reasons.append('地図の証明書を確認できません / visual manifest unavailable')
        else:
            outputs = manifest.get('outputs')
            sources = manifest.get('sources')
            visualization = manifest.get('visualization')
            expected_names = {filename for filename, _ in MAPS}
            manifest_ok = (
                manifest.get('schema') == 'onga-stage18-full64-visual-manifest-v2'
                and manifest.get('status') == 'generated'
                and manifest.get('sourceCaseCount') == CASE_COUNT
                and manifest.get('cellCount') == CELL_COUNT
                and manifest.get('comparisonBasis') == 'equal_step_count_not_equal_simulated_time'
                and isinstance(outputs, dict) and set(outputs) == expected_names
                and isinstance(sources, dict)
                and sources.get('executionContractSha256') == contract_digest
                and sources.get('runReportSha256') == report_digest
                and evaluation is not None
                and sources.get('evaluationSha256') == sha256_file(evaluation_path)
                and report is not None
                and sources.get('authorizationSha256') == report.get('inputDigests', {}).get('authorizationSha256')
                and sources.get('fieldArtifactSha256') == report.get('fieldArtifact', {}).get('sha256')
                and sources.get('meshSha256') == MESH_PACKAGE_SHA256
                and sources.get('meshSummarySha256') == report.get('inputDigests', {}).get('meshSummarySha256')
                and sources.get('ensembleSha256') == ENSEMBLE_SHA256
                and isinstance(visualization, dict)
                and visualization.get('representedCellCount') == CELL_COUNT
                and visualization.get('coverageFraction') == 1.0
            )
            if manifest_ok:
                for filename, _, present in map_status:
                    entry = outputs.get(filename)
                    if (
                        not present
                        or not isinstance(entry, dict)
                        or entry.get('mediaType') != 'image/png'
                        or entry.get('sha256') != sha256_file(directory / filename)
                    ):
                        manifest_ok = False
                        break
            if isinstance(outputs, dict):
                for filename, _, _ in map_status:
                    entry = outputs.get(filename)
                    if isinstance(entry, dict):
                        map_previews[filename]['metadata'] = entry
            if not manifest_ok:
                reasons.append('地図と証明書が一致しません / map manifest mismatch')

    passed = (
        contract is not None
        and report is not None
        and evaluation_passed
        and provenance_ok
        and completed == CASE_COUNT
        and failed == 0
        and present_map_count == len(MAPS)
        and manifest_ok
    )
    return {
        'passed': passed,
        'completed': completed,
        'failed': failed,
        'nanCount': nan_count,
        'negativeDepthCount': negative_count,
        'metrics': metrics,
        'limits': limits,
        'maps': map_status,
        'mapPreviews': map_previews,
        'presentMapCount': present_map_count,
        'manifestVerified': manifest_ok,
        'reasons': reasons[:4],
        'contractDigest': contract_digest,
        'reportDigest': report_digest,
    }


def metric_cards(state: dict[str, Any]) -> str:
    limits = state['limits']
    completed = state['completed']
    failed = state['failed']
    completed_value = f'{completed} / {CASE_COUNT}' if completed is not None else f'— / {CASE_COUNT}'
    completed_note = f'失敗 {failed if failed is not None else "—"} / Failed {failed if failed is not None else "—"}'
    nan_value = state['nanCount'] if state['nanCount'] is not None else '—'
    negative_value = state['negativeDepthCount'] if state['negativeDepthCount'] is not None else '—'
    metrics = state['metrics']
    cards = [
        ('完了ケース / Completed', completed_value, completed_note),
        ('NaN / 負の水深', f'{nan_value} / {negative_value}', '許容値 0 / 0'),
        ('CFL', f"{format_value(metrics['maxCfl'])} ≤ {format_value(float(limits['maxCflMax']))}", '最大値 / Maximum'),
        ('質量収支 / Mass balance',
         f"{format_value(metrics['maxAbsoluteMassBalanceError'], 'mass')} ≤ {format_value(float(limits['maxAbsoluteMassBalanceErrorMax']), 'mass')}",
         '最大絶対誤差 / Maximum absolute error'),
        ('実行時間 / Wall time',
         f"{format_value(metrics['wallSeconds'], 'seconds')} ≤ {format_value(float(limits['maxWallSeconds']), 'seconds')}",
         '実測 ≤ 許容値 / Actual ≤ limit'),
        ('メモリ / Memory',
         f"{format_value(metrics['peakResidentMemoryMiB'], 'memory')} ≤ {format_value(float(limits['maxResidentMemoryMiB']), 'memory')}",
         '最大常駐メモリ / Peak RSS'),
    ]
    payload = []
    for index, (label, value, note) in enumerate(cards):
        column = index % 3
        row = index // 3
        x = 60 + column * 500
        y = 245 + row * 145
        payload.append(f'''<g transform="translate({x} {y})">
  <rect width="460" height="120" rx="18" class="card"/>
  <text x="24" y="31" class="card-label">{xml(label)}</text>
  <text x="24" y="70" class="card-value">{xml(value)}</text>
  <text x="24" y="100" class="card-note">{xml(note)}</text>
</g>''')
    return ''.join(payload)


def map_cards(state: dict[str, Any]) -> str:
    payload = []
    for index, (filename, label, present) in enumerate(state['maps']):
        column = index % 3
        row = index // 3
        x = 70 + column * 505
        y = 650 + row * 410
        preview = state['mapPreviews'].get(filename, {})
        metadata = preview.get('metadata') if isinstance(preview, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        data_minimum = safe_number(metadata.get('dataMinimum'))
        data_maximum = safe_number(metadata.get('dataMaximum'))
        scale_minimum = safe_number(metadata.get('colorScaleMinimum'))
        scale_maximum = safe_number(metadata.get('colorScaleMaximum'))
        units = metadata.get('units') if isinstance(metadata.get('units'), str) else ''
        if data_minimum is not None and data_maximum is not None:
            suffix = f' {units}' if units else ''
            range_label = f'データ / data: {data_minimum:.4g} – {data_maximum:.4g}{suffix}'
        else:
            range_label = 'データ / data: —'
        palette = metadata.get('paletteRgb')
        palette_ok = (
            isinstance(palette, list) and 2 <= len(palette) <= 8
            and all(
                isinstance(color, list) and len(color) == 3
                and all(isinstance(channel, int) and not isinstance(channel, bool) and 0 <= channel <= 255
                        for channel in color)
                for color in palette
            )
        )
        swatches = ''
        if palette_ok:
            width = 160 / len(palette)
            swatches = ''.join(
                f'<rect x="{16 + position * width:.2f}" y="337" width="{width + 0.2:.2f}" height="13" '
                f'fill="rgb({color[0]},{color[1]},{color[2]})"/>'
                for position, color in enumerate(palette)
            )
        if scale_minimum is not None and scale_maximum is not None:
            scale_label = f'低 {scale_minimum:.3g}  →  高 {scale_maximum:.3g}'
        else:
            scale_label = '低 / low  →  高 / high'
        if present and preview.get('dataUri'):
            image = (
                f'<image x="10" y="48" width="430" height="285" '
                f'preserveAspectRatio="xMidYMid meet" href="{preview["dataUri"]}"/>'
            )
        else:
            image = '''<rect x="10" y="48" width="430" height="285" class="map-missing"/>
  <text x="225" y="195" text-anchor="middle" class="missing">画像なし / missing</text>'''
        payload.append(f'''<g transform="translate({x} {y})">
  <rect width="450" height="380" rx="18" class="card"/>
  <text x="16" y="31" class="map-label">{xml(label)}</text>
  {image}
  {swatches}
  <text x="190" y="349" class="map-range">{xml(scale_label)}</text>
  <text x="16" y="372" class="map-range">{xml(range_label)}</text>
</g>''')
    return ''.join(payload)


def render_svg(state: dict[str, Any]) -> bytes:
    passed = state['passed']
    header_fill = '#08783f' if passed else '#b91c1c'
    background = '#edf3f0' if passed else '#fff7f7'
    title = '判定: PASS / RESULT: PASS' if passed else 'STOP — 結果として使用不可'
    subtitle = (
        '64条件の数値安定性確認に合格 / Numerical stability checks passed'
        if passed else
        '未完了・不合格・成果物不足のいずれか / Incomplete, failed, or missing evidence'
    )
    reason_lines = state['reasons'] or ['—']
    reasons = ''.join(
        f'<text x="95" y="{1620 + index * 34}" class="reason">• {xml(reason)}</text>'
        for index, reason in enumerate(reason_lines)
    )
    decision_title = '人が判断すること / Human decision' if passed else '停止後の扱い / After STOP'
    decision_lines = (
        (
            '5枚を見て、空白・筋状ノイズ・孤立した極端値がなければ次の検証へ進められます。',
            '物理的に正しいこと、観測との一致、追加計算の許可は示しません。',
        ) if passed else (
            'この成果物を結果として使用せず、自動で再実行しないでください。',
            '再実行には原因確認後の新しい画像と新しい明示承認が必要です。',
        )
    )
    provenance = ''
    if state['contractDigest'] and state['reportDigest']:
        provenance = (
            f"contract {state['contractDigest'][:12]}… • report {state['reportDigest'][:12]}…"
        )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1600" height="2050" viewBox="0 0 1600 2050" role="img" aria-labelledby="title description">
<title id="title">{xml(title)}</title>
<desc id="description">Corrected-geometry 64-case numerical acceptance and five-map availability summary. This is not physical validation.</desc>
<style>
text {{ font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", Meiryo, sans-serif; fill: #15352a; }}
.banner {{ font-size: 54px; font-weight: 800; fill: #ffffff; }}
.subtitle {{ font-size: 24px; fill: #ffffff; }}
.card {{ fill: #ffffff; stroke: #cddbd4; stroke-width: 2; }}
.card-label {{ font-size: 20px; font-weight: 700; fill: #3f6255; }}
.card-value {{ font-size: 29px; font-weight: 800; fill: #123b2b; }}
.card-note {{ font-size: 16px; fill: #607c71; }}
.section-title {{ font-size: 30px; font-weight: 800; }}
.map-label {{ font-size: 23px; font-weight: 700; }}
.map-range {{ font-size: 17px; fill: #607c71; }}
.map-missing {{ fill: #e5ebe8; stroke: #aab9b2; stroke-width: 2; }}
.present {{ font-size: 22px; font-weight: 800; fill: #08783f; }}
.missing {{ font-size: 22px; font-weight: 800; fill: #b91c1c; }}
.reason {{ font-size: 20px; fill: #7f1d1d; }}
.decision-title {{ font-size: 27px; font-weight: 800; fill: #164e63; }}
.decision {{ font-size: 21px; font-weight: 650; fill: #164e63; }}
.limit {{ font-size: 19px; font-weight: 650; fill: #7f1d1d; }}
.provenance {{ font-size: 15px; fill: #607c71; }}
</style>
<rect width="1600" height="2050" fill="{background}"/>
<rect x="40" y="35" width="1520" height="150" rx="28" fill="{header_fill}"/>
<text x="85" y="105" class="banner">{xml(title)}</text>
<text x="88" y="148" class="subtitle">{xml(subtitle)}</text>
{metric_cards(state)}
<rect x="60" y="555" width="1480" height="955" rx="22" fill="#ffffff" stroke="#cddbd4" stroke-width="2"/>
<text x="85" y="605" class="section-title">5地図の確認 / Five-map package: {state['presentMapCount']} / {len(MAPS)}</text>
<text x="85" y="635" class="card-note">見る点: 空白、筋状ノイズ、孤立した極端値、流向サンプル不足 / Check gaps, streaks, isolated extremes, direction support</text>
{map_cards(state)}
<rect x="60" y="1535" width="1480" height="200" rx="22" fill="#fff4f2" stroke="#d97766" stroke-width="3"/>
<text x="95" y="1580" class="section-title">停止理由・不足 / Stop reasons or missing evidence</text>
{reasons}
<rect x="60" y="1760" width="1480" height="210" rx="22" fill="#ecfeff" stroke="#4aa3b6" stroke-width="3"/>
<text x="95" y="1810" class="decision-title">{xml(decision_title)}</text>
<text x="95" y="1855" class="decision">{xml(decision_lines[0])}</text>
<text x="95" y="1900" class="decision">{xml(decision_lines[1])}</text>
<text x="60" y="2015" class="provenance">{xml(provenance)}</text>
</svg>
'''.encode('utf-8')


def write_atomic(path: str | Path, payload: bytes) -> None:
    destination = Path(path)
    if destination.exists():
        raise ValidationError(f'decision SVG already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f'.{destination.name}.{os.getpid()}.tmp')
    try:
        with temporary.open('xb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def render_files(
    contract_path: str | Path,
    report_path: str | Path,
    evaluation_path: str | Path,
    map_dir: str | Path,
    output_path: str | Path,
    progress_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    output = Path(output_path).resolve()
    inputs = [Path(contract_path).resolve(), Path(report_path).resolve(), Path(evaluation_path).resolve()]
    inputs.extend((Path(map_dir) / name).resolve() for name, _ in MAPS)
    if progress_path is not None:
        inputs.append(Path(progress_path).resolve())
    if manifest_path is not None:
        inputs.append(Path(manifest_path).resolve())
    if output in inputs:
        raise ValidationError('decision SVG output overlaps an inspected input')
    if Path(output_path).exists():
        raise ValidationError(f'decision SVG already exists: {output_path}')
    state = collect_state(
        contract_path, report_path, evaluation_path, map_dir, progress_path, manifest_path,
    )
    write_atomic(output_path, render_svg(state))
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract')
    parser.add_argument('report')
    parser.add_argument('evaluation')
    parser.add_argument('--map-dir', required=True)
    parser.add_argument('--progress')
    parser.add_argument('--manifest')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    state = render_files(
        args.contract, args.report, args.evaluation, args.map_dir, args.output,
        args.progress, args.manifest,
    )
    print(json.dumps({
        'output': args.output,
        'status': 'pass' if state['passed'] else 'stop',
        'presentMapCount': state['presentMapCount'],
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValidationError) as error:
        print(f'[stage18-full64-v2-decision] {error}', file=__import__('sys').stderr)
        raise SystemExit(2)
