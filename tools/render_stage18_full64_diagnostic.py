#!/usr/bin/env python3
"""Render a fail-closed Stage 18 full64 diagnostic STOP image."""

import argparse
import html
import json
import math
import os
from pathlib import Path
import re
import textwrap


JSON_INPUTS = (
    'full64-progress.json',
    'full64-report.json',
    'full64-evaluation.json',
    'full64-statistics-summary.json',
)
KNOWN_ARTIFACTS = JSON_INPUTS + (
    'onga_stage16_metric_fv_mesh_v1.npz',
    'ensemble.json',
    'full64-fields.npz',
    'full64-statistics.npz',
    'full64-judgment.svg',
    'full64-visual-manifest.json',
)
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_REASON_CHARACTERS = 180
MAX_REASONS = 3


CHECK_LABELS = {
    'completionFraction': '64 cases were not all completed',
    'nanCount': 'NaN count exceeded the authorized limit',
    'negativeDepthCount': 'negative water depth exceeded the authorized limit',
    'maxCfl': 'CFL exceeded the authorized limit',
    'massBalance': 'mass-balance error exceeded the authorized limit',
    'wallTime': 'wall time exceeded the authorized limit',
    'memory': 'memory use exceeded the authorized limit',
    'minimumDepth': 'minimum depth check failed',
    'protectedSurfaces': 'a protected public or legacy surface changed',
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def reject_json_constant(value):
    raise ValueError(f'nonstandard JSON constant: {value}')


def redact(text):
    value = re.sub(r'[\x00-\x1f\x7f]+', ' ', str(text))
    value = re.sub(
        r'(?i)\b(token|secret|password|passwd|api[_-]?key|authorization)\s*[:=]\s*\S+',
        r'\1=[redacted]', value,
    )
    value = re.sub(r'(?i)\bBearer\s+\S+', 'Bearer [redacted]', value)
    value = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|AKIA[A-Z0-9]{16})\b', '[redacted]', value)
    value = re.sub(r'(?i)(https?://[^\s?#]+)[?#][^\s]+', r'\1?[redacted]', value)
    value = re.sub(r'\b[A-Za-z0-9_+/=-]{40,}\b', '[redacted]', value)
    value = re.sub(r'(?i)\bpass(?:ed)?\b', 'success-state', value)
    return ' '.join(value.split())


def capped_text(value, limit=MAX_REASON_CHARACTERS):
    cleaned = redact(value)
    if len(cleaned) <= limit:
        return cleaned
    return f'{cleaned[:limit - 1].rstrip()}…'


def xml(value):
    return html.escape(str(value), quote=True)


def load_optional_json(path):
    path = Path(path)
    if not path.exists():
        return None, None
    if path.is_symlink() or not path.is_file():
        return None, f'{path.name} is not a readable regular file'
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return None, f'{path.name} is too large to inspect safely'
        payload = json.loads(
            path.read_text(encoding='utf-8'),
            parse_constant=reject_json_constant,
        )
        if not isinstance(payload, dict):
            return None, f'{path.name} does not contain a JSON object'
        return payload, None
    except (OSError, UnicodeError, ValueError, RecursionError):
        return None, f'{path.name} is malformed or unreadable'


def safe_count(value):
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 64:
        return value
    return None


def finite_number(value, nonnegative=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(result) or (nonnegative and result < 0):
        return None
    return result


def diagnostic_values(progress, report, evaluation, summary):
    progress = progress or {}
    report = report or {}
    evaluation = evaluation or {}
    summary = summary or {}

    completed = safe_count(report.get('completedCaseCount'))
    if completed is None:
        completed = safe_count(progress.get('completedCaseCount'))
    failed = safe_count(report.get('failedCaseCount'))
    if failed is None:
        failed = safe_count(progress.get('failedCaseCount'))

    status_value = progress.get('status')
    raw_status = status_value.strip().lower() if isinstance(status_value, str) else ''
    status = {
        'failed': 'FAILED / 失敗',
        'cancelled': 'CANCELLED / キャンセル',
        'canceled': 'CANCELLED / キャンセル',
        'running': 'INTERRUPTED WHILE RUNNING / 実行中断',
        'completed': 'STOPPED AFTER COMPUTATION / 計算後に停止',
    }.get(raw_status, 'STOPPED OR CANCELLED / 停止またはキャンセル')

    diagnostics = report.get('caseDiagnostics')
    if not isinstance(diagnostics, list):
        diagnostics = progress.get('caseDiagnostics')
    if not isinstance(diagnostics, list):
        diagnostics = []
    diagnostic_cfl = [
        number for item in diagnostics if isinstance(item, dict)
        for number in [finite_number(item.get('maxCfl'))] if number is not None
    ]
    diagnostic_mass = [
        abs(number) for item in diagnostics if isinstance(item, dict)
        for number in [finite_number(item.get('massBalanceError'), nonnegative=False)] if number is not None
    ]
    run_diagnostics = summary.get('runDiagnostics')
    if not isinstance(run_diagnostics, dict):
        run_diagnostics = {}

    cfl = finite_number(report.get('maxCfl'))
    if cfl is None:
        cfl = finite_number(run_diagnostics.get('maxCfl'))
    if cfl is None and diagnostic_cfl:
        cfl = max(diagnostic_cfl)

    mass = finite_number(report.get('maxAbsoluteMassBalanceError'))
    if mass is None:
        mass = finite_number(run_diagnostics.get('massBalanceAbsoluteMaximum'))
    if mass is None and diagnostic_mass:
        mass = max(diagnostic_mass)

    wall = finite_number(report.get('wallSeconds'))
    if wall is None:
        wall = finite_number(progress.get('wallSeconds'))
    memory = finite_number(report.get('peakResidentMemoryMiB'))

    reasons = []

    def add_reason(value):
        reason = capped_text(value)
        if reason and reason not in reasons and len(reasons) < MAX_REASONS:
            reasons.append(reason)

    terminal = progress.get('terminalFailure')
    if isinstance(terminal, str):
        add_reason(terminal)
    for source in (report, progress):
        failures = source.get('failures')
        if not isinstance(failures, list):
            continue
        for failure in failures:
            if not isinstance(failure, dict):
                continue
            reason = failure.get('reason')
            if not isinstance(reason, str):
                continue
            case_id = capped_text(failure.get('caseId', ''), 30)
            add_reason(f'{case_id}: {reason}' if case_id else reason)
    checks = evaluation.get('checks')
    if isinstance(checks, dict):
        for key, label in CHECK_LABELS.items():
            if checks.get(key) is False:
                add_reason(label)
    return {
        'completed': completed,
        'failed': failed,
        'status': status,
        'cfl': cfl,
        'mass': mass,
        'wall': wall,
        'memory': memory,
        'reasons': reasons,
    }


def infer_stage(work_dir, present):
    if present.get('full64-judgment.svg') or present.get('full64-visual-manifest.json'):
        return 'Visual package created; a later workflow step stopped / 画像生成後の工程で停止'
    if present.get('full64-statistics-summary.json') or present.get('full64-statistics.npz'):
        return 'Statistics aggregation reached / 統計集約まで到達'
    if present.get('full64-evaluation.json'):
        return 'Evaluation reached / 評価まで到達'
    if present.get('full64-report.json'):
        return 'Numerical run report written / 数値計算report作成まで到達'
    if present.get('full64-fields.npz'):
        return 'Numerical field output written / 数値field出力まで到達'
    if present.get('full64-progress.json'):
        return 'Numerical run started / 64ケース数値計算を開始'
    if present.get('ensemble.json') or present.get('onga_stage16_metric_fv_mesh_v1.npz'):
        return 'Inputs prepared / 入力準備まで到達'
    if Path(work_dir).is_dir():
        return 'Work directory created / 作業directory作成まで到達'
    return 'No run artifact was preserved / run成果物なし'


def format_metric(value, kind):
    if value is None:
        return '— / unavailable'
    if kind == 'mass':
        return f'{value:.3e}'
    if kind == 'wall':
        return f'{value:,.1f} s'
    if kind == 'memory':
        return f'{value:,.1f} MiB'
    return f'{value:.4g}'


def line_tspans(value, x, y, width=70, max_lines=2, line_height=26, css_class='reason'):
    lines = textwrap.wrap(capped_text(value), width=width, break_long_words=True, break_on_hyphens=False) or ['—']
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = f'{lines[-1][:-1]}…' if lines[-1] else '…'
    return ''.join(
        f'<text x="{x}" y="{y + index * line_height}" class="{css_class}">{xml(line)}</text>'
        for index, line in enumerate(lines)
    )


def valid_run_link(repository, workflow_run_id):
    repository = str(repository)
    workflow_run_id = str(workflow_run_id)
    valid_repository = re.fullmatch(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}', repository)
    valid_run_id = re.fullmatch(r'[1-9][0-9]{0,19}', workflow_run_id)
    if not valid_repository or not valid_run_id:
        return capped_text(repository, 80), capped_text(workflow_run_id, 30), None
    return repository, workflow_run_id, f'https://github.com/{repository}/actions/runs/{workflow_run_id}'


def build_svg(work_dir, repository, workflow_run_id, documents, warnings):
    progress = documents.get('full64-progress.json')
    report = documents.get('full64-report.json')
    evaluation = documents.get('full64-evaluation.json')
    summary = documents.get('full64-statistics-summary.json')
    values = diagnostic_values(progress, report, evaluation, summary)
    present = {name: (Path(work_dir) / name).exists() for name in KNOWN_ARTIFACTS}
    stage = infer_stage(work_dir, present)
    repository_text, run_id_text, run_url = valid_run_link(repository, workflow_run_id)

    reasons = list(values['reasons'])
    for warning in warnings:
        if warning and warning not in reasons and len(reasons) < MAX_REASONS:
            reasons.append(capped_text(warning))
    if not reasons:
        reasons.append('Workflow stopped or was cancelled before a structured failure reason was recorded.')
    reasons = reasons[:MAX_REASONS]
    reason_svg = ''.join(
        f'<circle cx="96" cy="{912 + index * 58}" r="8" fill="#b91c1c"/>'
        + line_tspans(reason, 120, 920 + index * 58, width=105, max_lines=2, line_height=22)
        for index, reason in enumerate(reasons)
    )

    completed = f"{values['completed']} / 64" if values['completed'] is not None else '— / 64'
    failed = str(values['failed']) if values['failed'] is not None else '—'
    link_svg = (
        f'<text x="80" y="452" class="link">{xml(run_url)}</text>'
        if run_url else '<text x="80" y="452" class="muted">Run link unavailable because repository or run ID is invalid.</text>'
    )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1600" height="1500" viewBox="0 0 1600 1500" role="img" aria-labelledby="title description">
<title id="title">Stage 18 full64 diagnostic STOP</title>
<desc id="description">The one-time run stopped or was cancelled. This image is diagnostic evidence only and cannot be used as a numerical result.</desc>
<style>
text {{ font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", Meiryo, system-ui, sans-serif; fill: #341414; }}
.banner {{ font-size: 64px; font-weight: 900; fill: #ffffff; }}
.banner-sub {{ font-size: 27px; font-weight: 700; fill: #fee2e2; }}
.alert-title {{ font-size: 29px; font-weight: 850; fill: #7f1d1d; }}
.alert {{ font-size: 22px; font-weight: 700; fill: #7f1d1d; }}
.section {{ font-size: 27px; font-weight: 850; }}
.label {{ font-size: 18px; font-weight: 750; fill: #7c4a4a; }}
.value {{ font-size: 27px; font-weight: 850; }}
.small {{ font-size: 18px; fill: #6b4b4b; }}
.muted {{ font-size: 17px; fill: #7c6565; }}
.link {{ font-size: 17px; fill: #075985; text-decoration: underline; }}
.reason {{ font-size: 19px; font-weight: 650; }}
.decision {{ font-size: 22px; font-weight: 750; fill: #713f12; }}
.limit {{ font-size: 20px; font-weight: 700; fill: #7f1d1d; }}
</style>
<rect width="1600" height="1500" fill="#fff7f7"/>
<rect x="40" y="35" width="1520" height="175" rx="28" fill="#b91c1c"/>
<polygon points="105,72 151,160 59,160" fill="#ffffff" opacity="0.95"/>
<text x="92" y="143" font-size="62" font-weight="900" fill="#b91c1c">!</text>
<text x="185" y="112" class="banner" fill="#ffffff" style="fill:#ffffff">STOP — 結果として使用不可</text>
<text x="188" y="158" class="banner-sub" fill="#fee2e2" style="fill:#fee2e2">NOT USABLE AS A RESULT • failed or cancelled one-time full64 run</text>

<rect x="60" y="235" width="1480" height="118" rx="20" fill="#fee2e2" stroke="#b91c1c" stroke-width="3"/>
<text x="88" y="278" class="alert-title">一回限りの承認は消費済み / ONE-TIME AUTHORIZATION CONSUMED</text>
<text x="88" y="317" class="alert">自動で再実行しない / DO NOT RERUN AUTOMATICALLY — a new explicit authorization is required.</text>

<text x="70" y="398" class="section">Run evidence / 実行情報</text>
<text x="80" y="429" class="small">Repository: {xml(repository_text)}   •   Workflow run ID: {xml(run_id_text)}</text>
{link_svg}
<text x="80" y="486" class="small">Detected stage / 検出段階: {xml(capped_text(stage, 150))}</text>

<g transform="translate(60 520)">
  <rect width="480" height="118" rx="18" fill="#ffffff" stroke="#e2b8b8" stroke-width="2"/>
  <text x="24" y="35" class="label">Completed / 完了</text><text x="24" y="82" class="value">{xml(completed)}</text>
</g>
<g transform="translate(560 520)">
  <rect width="300" height="118" rx="18" fill="#ffffff" stroke="#e2b8b8" stroke-width="2"/>
  <text x="24" y="35" class="label">Failed / 失敗</text><text x="24" y="82" class="value">{xml(failed)}</text>
</g>
<g transform="translate(880 520)">
  <rect width="660" height="118" rx="18" fill="#ffffff" stroke="#e2b8b8" stroke-width="2"/>
  <text x="24" y="35" class="label">Status / 状態</text><text x="24" y="82" class="value">{xml(values['status'])}</text>
</g>

<g transform="translate(60 665)">
  <rect width="350" height="118" rx="18" fill="#ffffff" stroke="#e2b8b8" stroke-width="2"/>
  <text x="22" y="30" class="label">Available CFL</text><text x="22" y="70" class="value">{xml(format_metric(values['cfl'], 'cfl'))}</text>
  <text x="22" y="101" class="muted">Authorized limit: CFL ≤ 0.95</text>
</g>
<g transform="translate(430 665)">
  <rect width="350" height="118" rx="18" fill="#ffffff" stroke="#e2b8b8" stroke-width="2"/>
  <text x="22" y="30" class="label">Available mass balance</text><text x="22" y="70" class="value">{xml(format_metric(values['mass'], 'mass'))}</text>
  <text x="22" y="101" class="muted">Authorized limit: mass ≤ 1e-8</text>
</g>
<g transform="translate(800 665)">
  <rect width="350" height="118" rx="18" fill="#ffffff" stroke="#e2b8b8" stroke-width="2"/>
  <text x="22" y="30" class="label">Available wall time</text><text x="22" y="70" class="value">{xml(format_metric(values['wall'], 'wall'))}</text>
  <text x="22" y="101" class="muted">Authorized limit: wall ≤ 3,600 s</text>
</g>
<g transform="translate(1170 665)">
  <rect width="370" height="118" rx="18" fill="#ffffff" stroke="#e2b8b8" stroke-width="2"/>
  <text x="22" y="30" class="label">Available memory</text><text x="22" y="70" class="value">{xml(format_metric(values['memory'], 'memory'))}</text>
  <text x="22" y="101" class="muted">Authorized limit: memory ≤ 8,192 MiB</text>
</g>

<rect x="60" y="820" width="1480" height="250" rx="22" fill="#ffffff" stroke="#d8a0a0" stroke-width="3"/>
<text x="88" y="870" class="section">Why execution stopped / 保存された失敗情報（最大3件）</text>
{reason_svg}

<rect x="60" y="1100" width="1480" height="205" rx="22" fill="#fffbeb" stroke="#d97706" stroke-width="3"/>
<text x="88" y="1150" class="section" fill="#713f12">あなたが判断すること / Your decision</text>
<text x="96" y="1197" class="decision">① 原因と保存された証拠を確認する / Review the cause and preserved evidence.</text>
<text x="96" y="1242" class="decision">② 新しい明示承認に値するか判断する / Decide whether a NEW explicit authorization is warranted.</text>
<text x="96" y="1280" class="small">この画像自体は再実行を許可しません / This image does not authorize another run.</text>

<rect x="60" y="1335" width="1480" height="115" rx="20" fill="#fee2e2" stroke="#b91c1c" stroke-width="2"/>
<text x="88" y="1380" class="limit">物理的妥当性の検証ではありません。公開シミュレータには接続していません。</text>
<text x="88" y="1418" class="limit">Not physical validation. Not connected to the public simulator.</text>
</svg>
'''
    require('RESULT: PASS' not in svg.upper(), 'diagnostic SVG must never show a result success state')
    return svg.encode('utf-8')


def preflight(work_dir, output):
    work_dir = Path(work_dir)
    output = Path(output)
    resolved_output = output.resolve(strict=False)
    require(resolved_output != work_dir.resolve(strict=False), 'diagnostic output overlaps work directory')
    inputs = {(work_dir / name).resolve(strict=False) for name in KNOWN_ARTIFACTS}
    require(resolved_output not in inputs, 'diagnostic output overlaps an inspected input')
    require(not os.path.lexists(output), f'diagnostic output already exists: {output}')


def write_fresh_atomic(output, payload):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f'.{output.name}.{os.getpid()}.tmp')
    descriptor = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, 'wb') as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, output)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--workflow-run-id', required=True)
    parser.add_argument('--repository', required=True)
    args = parser.parse_args()

    preflight(args.work_dir, args.output)
    documents = {}
    warnings = []
    for name in JSON_INPUTS:
        documents[name], warning = load_optional_json(Path(args.work_dir) / name)
        if warning:
            warnings.append(warning)
    payload = build_svg(args.work_dir, args.repository, args.workflow_run_id, documents, warnings)
    write_fresh_atomic(args.output, payload)
    print(json.dumps({
        'status': 'generated',
        'judgment': 'stop',
        'output': str(args.output),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
