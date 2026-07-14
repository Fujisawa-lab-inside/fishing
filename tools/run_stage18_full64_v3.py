#!/usr/bin/env python3
"""Run the single reviewed Stage 18 v3 recovery profile fail closed."""

from __future__ import annotations

import json
import sys

import run_stage18_full64_v2 as core
from stage18_full64_v3_profile import configure_runner


configure_runner(core)


def main(argv=None) -> int:
    args = core.build_parser().parse_args(argv)
    try:
        control = core.control_plane_preflight(args)
    except (core.ExecutionNotAuthorized, core.PreflightError) as error:
        print(f'V3 CONTROL-PLANE STOP: {error}', file=sys.stderr)
        print('No numerical cases were started; NumPy and numerical inputs were not loaded.', file=sys.stderr)
        return 2

    try:
        context = core.data_plane_preflight(args, control)
    except (core.PreflightError, OSError, ValueError) as error:
        print(f'V3 PREFLIGHT STOP: {error}', file=sys.stderr)
        print('No numerical cases were started and no outputs were created.', file=sys.stderr)
        return 3

    try:
        report = core.execute_cases(args, context)
    except BaseException as error:
        print(f'V3 NUMERICAL STOP: {error}', file=sys.stderr)
        return 4
    print(json.dumps({
        'report': str(context['reportPath']),
        'completedCaseCount': report['completedCaseCount'],
        'failedCaseCount': report['failedCaseCount'],
        'wallSeconds': report['wallSeconds'],
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
