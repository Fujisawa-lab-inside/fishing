#!/usr/bin/env python3
"""Render the result decision SVG for the fixed v3 recovery path."""

from __future__ import annotations

import argparse
import json

import evaluate_stage18_full64_v2 as evaluator
from stage18_full64_v3_profile import configure_evaluator


configure_evaluator(evaluator)

import render_stage18_full64_decision_v2 as core  # noqa: E402


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
    state = core.render_files(
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
    except (OSError, core.ValidationError) as error:
        print(f'[stage18-full64-v3-decision] {error}', file=__import__('sys').stderr)
        raise SystemExit(2)
