#!/usr/bin/env python3
"""Create the five-map bundle from sealed v2-format fields under v3 control."""

from __future__ import annotations

import argparse
import json

import evaluate_stage18_full64_v2 as evaluator
from stage18_full64_v3_profile import configure_evaluator


configure_evaluator(evaluator)

import aggregate_stage18_full64_v2 as core  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mesh')
    parser.add_argument('fields')
    parser.add_argument('report')
    parser.add_argument('evaluation')
    parser.add_argument('authorization')
    parser.add_argument('contract')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    result = core.aggregate_and_render(
        args.mesh, args.fields, args.report, args.evaluation,
        args.authorization, args.contract, args.output_dir,
        allow_relocated_fields=True,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, core.ValidationError) as error:
        print(f'[stage18-full64-v3-aggregate] {error}', file=__import__('sys').stderr)
        raise SystemExit(2)
