#!/usr/bin/env python3
"""Validate every Stage 18 v2 input without starting a numerical case."""

import json
import sys

from run_stage18_full64_v2 import (
    ExecutionNotAuthorized,
    PreflightError,
    build_parser,
    control_plane_preflight,
    data_plane_preflight,
)


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        control = control_plane_preflight(args)
    except (ExecutionNotAuthorized, PreflightError) as error:
        print(f'V2 CONTROL-PLANE STOP: {error}', file=sys.stderr)
        print('No numerical cases were started; NumPy and numerical inputs were not loaded.', file=sys.stderr)
        return 2

    try:
        context = data_plane_preflight(args, control)
    except (PreflightError, OSError, ValueError) as error:
        print(f'V2 PREFLIGHT STOP: {error}', file=sys.stderr)
        print('No numerical cases were started and no outputs were created.', file=sys.stderr)
        return 3
    finally:
        package = locals().get('context', {}).get('package')
        if package is not None:
            package.close()

    print(json.dumps({
        'schema': 'onga-stage18-full64-preflight-v2',
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
