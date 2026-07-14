#!/usr/bin/env python3
"""Validate every fixed v3 recovery input without starting a numerical case."""

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
    finally:
        package = locals().get('context', {}).get('package')
        if package is not None:
            package.close()

    print(json.dumps({
        'schema': 'onga-stage18-full64-preflight-v3',
        'status': 'passed',
        'numericalCasesStarted': 0,
        'outputsCreated': 0,
        'caseCount': len(context['cases']),
        'cellCount': context['contract']['geometry']['metricMeshCellCount'],
        'inputDigests': {
            'executionContractSha256': context['contractSha256'],
            'authorizationSha256': context['authorizationSha256'],
            'meshSha256': context['meshSha256'],
            'meshSummarySha256': context['meshSummarySha256'],
            'ensembleSha256': context['ensembleSha256'],
        },
    }))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
