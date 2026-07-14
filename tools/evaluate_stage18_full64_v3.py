#!/usr/bin/env python3
"""Evaluate v2-format numerical evidence under the fixed v3 control plane."""

from __future__ import annotations

import evaluate_stage18_full64_v2 as core
from stage18_full64_v3_profile import configure_evaluator


configure_evaluator(core)


if __name__ == '__main__':
    try:
        raise SystemExit(core.main())
    except (OSError, ValueError, core.ValidationError) as error:
        print(f'[stage18-full64-v3-evaluator] {error}', file=__import__('sys').stderr)
        raise SystemExit(2)
