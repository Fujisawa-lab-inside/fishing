#!/usr/bin/env python3
"""Fail-closed telemetry contract for a bounded Stage 20 mesh canary.

This observer remains deliberately disconnected from every solver and runner.
It accepts only limiter identity and quantities already computed by a future
successor runner, recomputes the frozen Stage 20 time-step formula, and
aggregates evidence in memory. It changes no numerical equation and performs
no filesystem I/O while proposals are recorded.

The exact accepted-dt array is intentionally bounded to a 900--1200 model-
second comparison. It is not a 36-hour telemetry design.
"""

from __future__ import annotations

from array import array
from collections import Counter
from dataclasses import dataclass
import math
import re
from time import perf_counter_ns
from typing import Any, Mapping

import numpy as np


SCHEMA = "onga-stage20-dynamic-mesh-comparison-telemetry-v1"
PHASES = ("flux", "source", "control", "wetdry", "output")
CANARY_MIN_MODEL_SECONDS = 900.0
CANARY_MAX_MODEL_SECONDS = 1200.0
ABSOLUTE_MAX_ACCEPTED_STEP_COUNT = 500_000
ABSOLUTE_MAX_ACCEPTED_DT_STORAGE_BYTES = 4_000_000

# Current Stage 20 kernels form ``denominator[cell]`` by summing Rusanov
# spectral speed times face length, then use
#   min(cfl_target * min_cell(area / max(denominator, 1e-30)), maximum_dt).
# The telemetry names are frozen to those two actual kernel operands. Generic
# labels such as "advective" or "wetdry" are not accepted as substitutes.
APPROVED_LIMITER_FORMULA_ID = (
    "stage20_min_cfl_target_times_cell_area_over_"
    "spectral_radius_face_length_sum_and_maximum_dt_v1"
)
CFL_DT_BOUND_NAME = "cfl_target_times_time_step_limit"
MAXIMUM_DT_BOUND_NAME = "maximum_dt"
APPROVED_DT_BOUND_NAMES = (CFL_DT_BOUND_NAME, MAXIMUM_DT_BOUND_NAME)
APPROVED_CFL_TARGET = 0.12

# The observed R1C step is about 0.005 s. A 0.05 s absolute ceiling leaves a
# ten-fold margin while preventing a synthetic one-step 900 s "canary". The
# 20k floor is still an order of magnitude below the expected 180k--240k steps.
ABSOLUTE_MAX_ACCEPTED_DT_SECONDS = 0.05
ABSOLUTE_MIN_ACCEPTED_STEP_COUNT = 20_000
ABSOLUTE_MAX_EXPECTED_CANDIDATE_COUNT = 10_000_000

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class TelemetryEvidenceError(RuntimeError):
    """Raised when telemetry would otherwise accept incomplete evidence."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TelemetryEvidenceError(message)


def _finite(value: Any, label: str) -> float:
    require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{label} is not numeric",
    )
    number = float(value)
    require(math.isfinite(number), f"{label} must be finite")
    return number


def _positive(value: Any, label: str) -> float:
    number = _finite(value, label)
    require(number > 0.0, f"{label} must be positive")
    return number


def _nonnegative(value: Any, label: str) -> float:
    number = _finite(value, label)
    require(number >= 0.0, f"{label} must be nonnegative")
    return number


def _positive_integer(value: Any, label: str) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{label} is not an integer",
    )
    require(value > 0, f"{label} must be positive")
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{label} is not an integer",
    )
    require(value >= 0, f"{label} must be nonnegative")
    return value


def _nonempty_text(value: Any, label: str, maximum_length: int = 160) -> str:
    require(isinstance(value, str), f"{label} is not text")
    text = value.strip()
    require(bool(text), f"{label} is empty")
    require(len(text) <= maximum_length, f"{label} is too long")
    return text


def _sha256(value: Any, label: str) -> str:
    require(isinstance(value, str), f"{label} is not text")
    require(
        _SHA256_RE.fullmatch(value) is not None,
        f"{label} is not a lowercase SHA256 digest",
    )
    require(value != "0" * 64, f"{label} cannot be the all-zero placeholder")
    return value


def _close(actual: float, expected: float) -> bool:
    tolerance = max(1.0e-15, abs(expected) * 1.0e-12)
    return abs(actual - expected) <= tolerance


@dataclass(frozen=True, slots=True)
class TelemetryConfig:
    """Immutable identity and evidence contract fixed before the canary."""

    run_id: str
    mesh_id: str
    run_manifest_sha256: str
    mesh_sha256: str
    checkpoint_sha256: str
    forcing_sha256: str
    solver_source_sha256: str
    control_contract_sha256: str
    bathymetry_sha256: str
    approved_limiter_formula_id: str
    required_dt_bound_names: tuple[str, ...]
    cfl_target: float
    expected_candidate_count: int
    max_accepted_step_count: int
    max_accepted_dt_storage_bytes: int
    limiter_top_k: int = 16
    zero_phase_time_exceptions: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class LimiterSample:
    """Global limiting-cell evidence for one fully scanned proposal."""

    cell_id: int
    cell_area_m2: float
    spectral_radius_face_length_sum_m2_per_s: float
    cfl_target: float
    maximum_dt_s: float
    expected_candidate_count: int
    evaluated_candidate_count: int
    coverage_complete: bool
    dt_bounds_s: Mapping[str, float]
    selected_bound_name: str


class _PhaseTimer:
    __slots__ = ("collector", "phase", "started_ns", "closed")

    def __init__(self, collector: "DynamicMeshTelemetry", phase: str):
        self.collector = collector
        self.phase = phase
        self.started_ns = 0
        self.closed = False

    def __enter__(self) -> "_PhaseTimer":
        require(not self.closed, "phase timer cannot be reused")
        self.collector._active_phase_timers += 1
        self.started_ns = perf_counter_ns()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        elapsed_ns = perf_counter_ns() - self.started_ns
        self.collector._phase_ns[self.phase] += elapsed_ns
        self.collector._phase_seen.add(self.phase)
        self.collector._active_phase_timers -= 1
        self.closed = True
        return False


class DynamicMeshTelemetry:
    """In-memory telemetry collector for one successor-runner process."""

    def __init__(self, config: TelemetryConfig):
        require(
            isinstance(config, TelemetryConfig),
            "telemetry config has the wrong type",
        )
        run_id = _nonempty_text(config.run_id, "run id")
        mesh_id = _nonempty_text(config.mesh_id, "mesh id")
        identities = {
            "runManifestSha256": _sha256(
                config.run_manifest_sha256, "run manifest SHA256"
            ),
            "meshSha256": _sha256(config.mesh_sha256, "mesh SHA256"),
            "checkpointSha256": _sha256(
                config.checkpoint_sha256, "checkpoint SHA256"
            ),
            "forcingSha256": _sha256(config.forcing_sha256, "forcing SHA256"),
            "solverSourceSha256": _sha256(
                config.solver_source_sha256, "solver source SHA256"
            ),
            "controlContractSha256": _sha256(
                config.control_contract_sha256, "control contract SHA256"
            ),
            "bathymetrySha256": _sha256(
                config.bathymetry_sha256, "bathymetry SHA256"
            ),
        }
        formula_id = _nonempty_text(
            config.approved_limiter_formula_id,
            "approved limiter formula id",
            240,
        )
        require(
            formula_id == APPROVED_LIMITER_FORMULA_ID,
            "approved limiter formula id does not match the frozen Stage 20 kernel formula",
        )
        require(
            isinstance(config.required_dt_bound_names, tuple),
            "required dt bound names must be a tuple",
        )
        names = tuple(
            _nonempty_text(name, "dt bound name", 80)
            for name in config.required_dt_bound_names
        )
        require(
            names == APPROVED_DT_BOUND_NAMES,
            "dt bound names do not exactly match the frozen Stage 20 kernel operands",
        )
        cfl_target = _positive(config.cfl_target, "CFL target")
        require(
            _close(cfl_target, APPROVED_CFL_TARGET),
            "CFL target does not match the approved Stage 20 value",
        )
        expected_candidates = _positive_integer(
            config.expected_candidate_count, "expected candidate count"
        )
        require(
            expected_candidates <= ABSOLUTE_MAX_EXPECTED_CANDIDATE_COUNT,
            "expected candidate count exceeds the telemetry contract limit",
        )
        require(
            isinstance(config.limiter_top_k, int)
            and not isinstance(config.limiter_top_k, bool),
            "limiter top-k must be an integer",
        )
        require(
            1 <= config.limiter_top_k <= 1024,
            "limiter top-k is outside 1..1024",
        )
        require(
            isinstance(config.max_accepted_step_count, int)
            and not isinstance(config.max_accepted_step_count, bool),
            "maximum accepted step count must be an integer",
        )
        require(
            ABSOLUTE_MIN_ACCEPTED_STEP_COUNT
            <= config.max_accepted_step_count
            <= ABSOLUTE_MAX_ACCEPTED_STEP_COUNT,
            (
                "maximum accepted step count is outside the bounded-canary range "
                f"{ABSOLUTE_MIN_ACCEPTED_STEP_COUNT}.."
                f"{ABSOLUTE_MAX_ACCEPTED_STEP_COUNT}"
            ),
        )
        require(
            isinstance(config.max_accepted_dt_storage_bytes, int)
            and not isinstance(config.max_accepted_dt_storage_bytes, bool),
            "maximum accepted-dt storage bytes must be an integer",
        )
        itemsize = array("d").itemsize
        minimum_storage = ABSOLUTE_MIN_ACCEPTED_STEP_COUNT * itemsize
        require(
            minimum_storage
            <= config.max_accepted_dt_storage_bytes
            <= ABSOLUTE_MAX_ACCEPTED_DT_STORAGE_BYTES,
            (
                "maximum accepted-dt storage bytes is outside the bounded-canary range "
                f"{minimum_storage}..{ABSOLUTE_MAX_ACCEPTED_DT_STORAGE_BYTES}"
            ),
        )
        require(
            isinstance(config.zero_phase_time_exceptions, tuple),
            "zero phase-time exceptions must be a tuple fixed before the run",
        )
        zero_phase_time_exceptions: list[tuple[str, str]] = []
        seen_exception_phases: set[str] = set()
        for index, entry in enumerate(config.zero_phase_time_exceptions):
            require(
                isinstance(entry, tuple) and len(entry) == 2,
                f"zero phase-time exception {index} must be a (phase, reason) tuple",
            )
            phase, reason = entry
            phase = _nonempty_text(
                phase, f"zero phase-time exception {index} phase", 80
            )
            require(
                phase in PHASES,
                f"zero phase-time exception uses unknown phase: {phase}",
            )
            require(
                phase not in seen_exception_phases,
                f"duplicate zero phase-time exception: {phase}",
            )
            reason = _nonempty_text(
                reason, f"zero phase-time exception {phase} reason", 240
            )
            seen_exception_phases.add(phase)
            zero_phase_time_exceptions.append((phase, reason))

        self.config = TelemetryConfig(
            run_id=run_id,
            mesh_id=mesh_id,
            run_manifest_sha256=identities["runManifestSha256"],
            mesh_sha256=identities["meshSha256"],
            checkpoint_sha256=identities["checkpointSha256"],
            forcing_sha256=identities["forcingSha256"],
            solver_source_sha256=identities["solverSourceSha256"],
            control_contract_sha256=identities["controlContractSha256"],
            bathymetry_sha256=identities["bathymetrySha256"],
            approved_limiter_formula_id=formula_id,
            required_dt_bound_names=names,
            cfl_target=cfl_target,
            expected_candidate_count=expected_candidates,
            max_accepted_step_count=config.max_accepted_step_count,
            max_accepted_dt_storage_bytes=config.max_accepted_dt_storage_bytes,
            limiter_top_k=config.limiter_top_k,
            zero_phase_time_exceptions=tuple(zero_phase_time_exceptions),
        )
        self._identity_report = identities
        self._required_bound_set = frozenset(names)
        self._accepted_dt = array("d")
        self._accepted_count = 0
        self._accepted_model_seconds = 0.0
        self._accepted_model_seconds_compensation = 0.0
        self._rejected_count = 0
        self._rejected_by_reason: Counter[str] = Counter()
        self._candidate_counts: Counter[str] = Counter()
        self._candidate_accepted_counts: Counter[str] = Counter()
        self._candidate_rejected_counts: Counter[str] = Counter()
        self._candidate_identity: dict[str, dict[str, Any]] = {}
        self._global_minimum_event: dict[str, Any] | None = None
        self._minimum_by_bound: dict[str, dict[str, Any] | None] = {
            name: None for name in names
        }
        self._phase_ns = {phase: 0 for phase in PHASES}
        self._phase_seen: set[str] = set()
        self._active_phase_timers = 0
        self._event_index = 0
        self._full_scan_proposal_count = 0
        self._finalized = False

    def _validate_sample(
        self, sample: LimiterSample
    ) -> tuple[str, dict[str, float], float, dict[str, Any]]:
        require(
            isinstance(sample, LimiterSample),
            "limiter sample has the wrong type",
        )
        cell_id = _nonnegative_integer(sample.cell_id, "limiting cell id")
        require(
            cell_id < self.config.expected_candidate_count,
            "limiting cell id is outside the frozen candidate set",
        )
        cell_area = _positive(sample.cell_area_m2, "limiting cell area")
        spectral_sum = _nonnegative(
            sample.spectral_radius_face_length_sum_m2_per_s,
            "spectral-radius times face-length sum",
        )
        cfl_target = _positive(sample.cfl_target, "sample CFL target")
        require(
            _close(cfl_target, self.config.cfl_target),
            "sample CFL target differs from the frozen config",
        )
        maximum_dt = _positive(sample.maximum_dt_s, "maximum dt")

        expected = _positive_integer(
            sample.expected_candidate_count, "sample expected candidate count"
        )
        evaluated = _positive_integer(
            sample.evaluated_candidate_count, "evaluated candidate count"
        )
        require(
            expected == self.config.expected_candidate_count,
            "sample expected candidate count differs from config",
        )
        require(
            evaluated == expected,
            "full candidate scan is incomplete: evaluated does not equal expected",
        )
        require(
            isinstance(sample.coverage_complete, bool),
            "candidate scan coverage-complete flag is not boolean",
        )
        require(
            sample.coverage_complete,
            "full candidate scan coverage is not complete",
        )

        cfl_bound = cfl_target * cell_area / max(spectral_sum, 1.0e-30)
        cfl_bound = _positive(
            cfl_bound, f"recomputed {CFL_DT_BOUND_NAME} bound"
        )
        recomputed = {
            CFL_DT_BOUND_NAME: cfl_bound,
            MAXIMUM_DT_BOUND_NAME: maximum_dt,
        }
        require(
            isinstance(sample.dt_bounds_s, Mapping),
            "dt bounds are not a mapping",
        )
        require(
            frozenset(sample.dt_bounds_s) == self._required_bound_set,
            "dt bound names do not exactly match the frozen Stage 20 kernel operands",
        )
        bounds: dict[str, float] = {}
        for name in APPROVED_DT_BOUND_NAMES:
            bounds[name] = _positive(sample.dt_bounds_s[name], f"dt bound {name}")
            require(
                _close(bounds[name], recomputed[name]),
                (
                    f"dt bound {name} disagrees with the independently "
                    "recomputed Stage 20 formula"
                ),
            )
        selected = _nonempty_text(
            sample.selected_bound_name, "selected dt bound name", 80
        )
        require(
            selected in bounds,
            "selected dt bound is not a frozen Stage 20 operand",
        )
        minimum = min(bounds.values())
        require(
            _close(bounds[selected], minimum),
            "selected dt bound is not the smallest recomputed bound",
        )

        key = f"cell:{cell_id}"
        self._candidate_identity.setdefault(
            key, {"candidateKind": "cell", "cellId": cell_id}
        )
        evidence = {
            "candidateKind": "cell",
            "cellId": cell_id,
            "cellAreaM2": cell_area,
            "spectralRadiusFaceLengthSumM2PerS": spectral_sum,
            "cflTarget": cfl_target,
            "maximumDtSeconds": maximum_dt,
            "expectedCandidateCount": expected,
            "evaluatedCandidateCount": evaluated,
            "coverageComplete": True,
            "dtBoundsSeconds": bounds,
            "selectedBoundName": selected,
            "selectedBoundSeconds": bounds[selected],
        }
        return key, bounds, bounds[selected], evidence

    def _record(
        self,
        *,
        outcome: str,
        step_dt_s: float,
        sample: LimiterSample,
        rejection_reason: str | None,
    ) -> None:
        require(not self._finalized, "telemetry is already finalized")
        dt = _positive(step_dt_s, "step dt")
        if outcome == "accepted":
            require(
                dt <= ABSOLUTE_MAX_ACCEPTED_DT_SECONDS + 1.0e-15,
                "accepted dt exceeds the absolute bounded-canary upper limit",
            )
            prospective_count = self._accepted_count + 1
            require(
                prospective_count <= self.config.max_accepted_step_count,
                "accepted step count would exceed the frozen bounded-canary limit",
            )
            prospective_storage_bytes = (
                prospective_count * self._accepted_dt.itemsize
            )
            require(
                prospective_storage_bytes
                <= self.config.max_accepted_dt_storage_bytes,
                (
                    "accepted-dt storage would exceed the frozen "
                    "bounded-canary memory limit"
                ),
            )
        key, bounds, selected_value, evidence = self._validate_sample(sample)
        if outcome == "accepted":
            tolerance = max(1.0e-15, abs(selected_value) * 1.0e-12)
            require(
                dt <= selected_value + tolerance,
                "accepted dt exceeds the selected minimum dt bound",
            )
        self._event_index += 1
        self._full_scan_proposal_count += 1
        event = {
            "eventIndex": self._event_index,
            "outcome": outcome,
            "stepDtSeconds": dt,
            **evidence,
        }
        if rejection_reason is not None:
            event["rejectionReason"] = rejection_reason

        self._candidate_counts[key] += 1
        if outcome == "accepted":
            self._accepted_count += 1
            self._accepted_dt.append(dt)
            corrected = dt - self._accepted_model_seconds_compensation
            updated = self._accepted_model_seconds + corrected
            self._accepted_model_seconds_compensation = (
                updated - self._accepted_model_seconds
            ) - corrected
            self._accepted_model_seconds = updated
            self._candidate_accepted_counts[key] += 1
        else:
            self._rejected_count += 1
            assert rejection_reason is not None
            self._rejected_by_reason[rejection_reason] += 1
            self._candidate_rejected_counts[key] += 1

        if (
            self._global_minimum_event is None
            or selected_value
            < self._global_minimum_event["selectedBoundSeconds"]
        ):
            self._global_minimum_event = event
        for name, value in bounds.items():
            current = self._minimum_by_bound[name]
            if current is None or value < current["boundSeconds"]:
                self._minimum_by_bound[name] = {
                    "boundName": name,
                    "boundSeconds": value,
                    "event": event,
                }

    def record_accepted_step(
        self, accepted_dt_s: float, limiter: LimiterSample
    ) -> None:
        """Record one accepted step without logging or filesystem I/O."""

        self._record(
            outcome="accepted",
            step_dt_s=accepted_dt_s,
            sample=limiter,
            rejection_reason=None,
        )

    def record_rejected_step(
        self,
        proposed_dt_s: float,
        reason: str,
        limiter: LimiterSample,
    ) -> None:
        """Record a rejected proposal and its complete limiter evidence."""

        normalized_reason = _nonempty_text(reason, "rejection reason", 128)
        self._record(
            outcome="rejected",
            step_dt_s=proposed_dt_s,
            sample=limiter,
            rejection_reason=normalized_reason,
        )

    def add_phase_wall_ns(self, phase: str, elapsed_ns: int) -> None:
        require(not self._finalized, "telemetry is already finalized")
        require(phase in PHASES, f"unknown phase: {phase}")
        require(
            isinstance(elapsed_ns, int) and not isinstance(elapsed_ns, bool),
            "phase ns is not an integer",
        )
        require(elapsed_ns >= 0, "phase ns must be nonnegative")
        self._phase_ns[phase] += elapsed_ns
        self._phase_seen.add(phase)

    def add_phase_wall_seconds(
        self, phase: str, elapsed_seconds: float
    ) -> None:
        seconds = _nonnegative(elapsed_seconds, "phase wall seconds")
        self.add_phase_wall_ns(phase, int(round(seconds * 1.0e9)))

    def time_phase(self, phase: str) -> _PhaseTimer:
        require(not self._finalized, "telemetry is already finalized")
        require(phase in PHASES, f"unknown phase: {phase}")
        return _PhaseTimer(self, phase)

    def finalize(
        self, *, total_runner_wall_seconds: float | None = None
    ) -> dict[str, Any]:
        """Validate completeness and return a JSON-safe snapshot."""

        require(not self._finalized, "telemetry is already finalized")
        require(self._active_phase_timers == 0, "a phase timer is still active")
        require(self._accepted_count > 0, "no accepted steps were recorded")
        require(
            self._accepted_count >= ABSOLUTE_MIN_ACCEPTED_STEP_COUNT,
            "accepted step count is below the absolute bounded-canary minimum",
        )
        missing_phases = sorted(set(PHASES) - self._phase_seen)
        require(
            not missing_phases,
            f"phase wall time is missing: {', '.join(missing_phases)}",
        )
        require(
            self._global_minimum_event is not None,
            "no limiter event was recorded",
        )
        require(
            self._full_scan_proposal_count
            == self._accepted_count + self._rejected_count,
            "full candidate scan accounting does not cover every proposal",
        )

        accepted = np.frombuffer(self._accepted_dt, dtype=np.float64)
        accepted_model_seconds = math.fsum(self._accepted_dt)
        accumulation_tolerance = max(
            1.0e-9, abs(accepted_model_seconds) * 1.0e-12
        )
        require(
            abs(accepted_model_seconds - self._accepted_model_seconds)
            <= accumulation_tolerance,
            (
                "incremental accepted model-time accounting disagrees with "
                "the exact dt array"
            ),
        )
        duration_tolerance = max(
            1.0e-9, CANARY_MAX_MODEL_SECONDS * 1.0e-12
        )
        require(
            accepted_model_seconds + duration_tolerance
            >= CANARY_MIN_MODEL_SECONDS,
            (
                "accepted cumulative model seconds are below the frozen "
                f"{CANARY_MIN_MODEL_SECONDS:.0f} second canary minimum"
            ),
        )
        require(
            accepted_model_seconds
            <= CANARY_MAX_MODEL_SECONDS + duration_tolerance,
            (
                "accepted cumulative model seconds exceed the frozen "
                f"{CANARY_MAX_MODEL_SECONDS:.0f} second canary maximum"
            ),
        )
        quantiles = np.quantile(
            accepted, [0.01, 0.50, 0.95], method="linear"
        )
        phase_seconds = {
            phase: self._phase_ns[phase] / 1.0e9 for phase in PHASES
        }
        phase_total = sum(phase_seconds.values())
        zero_phase_exceptions = dict(self.config.zero_phase_time_exceptions)
        for phase in PHASES:
            require(
                self._phase_ns[phase] > 0 or phase in zero_phase_exceptions,
                (
                    "phase wall time is zero without a predeclared exception: "
                    f"{phase}"
                ),
            )
        require(phase_total > 0.0, "all phase wall times are zero")
        require(
            total_runner_wall_seconds is not None,
            "total runner wall seconds are required",
        )
        runner_total = _positive(
            total_runner_wall_seconds, "total runner wall seconds"
        )
        tolerance = max(1.0e-9, runner_total * 1.0e-9)
        require(
            runner_total + tolerance >= phase_total,
            "phase wall total exceeds total runner wall time",
        )
        unclassified = max(0.0, runner_total - phase_total)

        top = sorted(
            self._candidate_counts,
            key=lambda key: (-self._candidate_counts[key], key),
        )[: self.config.limiter_top_k]
        top_candidates = [
            {
                **self._candidate_identity[key],
                "selectionCount": self._candidate_counts[key],
                "acceptedSelectionCount": self._candidate_accepted_counts[key],
                "rejectedSelectionCount": self._candidate_rejected_counts[key],
            }
            for key in top
        ]
        report = {
            "schema": SCHEMA,
            "version": 1,
            "status": (
                "FINALIZED_ALL_TELEMETRY_CONTRACT_CHECKS_PASSED_"
                "NOT_CANARY_COMPLETION"
            ),
            "classification": (
                "VALIDATED_900_TO_1200_ACCEPTED_MODEL_SECOND_TELEMETRY_ONLY_"
                "NOT_36H_OPERATIONAL_DEFAULT_NOT_CONNECTED_NOT_SOLVER_RUN_"
                "NOT_CANARY_COMPLETION_NOT_MESH_ADOPTION"
            ),
            "scope": {
                "requiredCanaryDurationModelSeconds": [
                    CANARY_MIN_MODEL_SECONDS,
                    CANARY_MAX_MODEL_SECONDS,
                ],
                "actualAcceptedModelSeconds": accepted_model_seconds,
                "absoluteMaximumAcceptedDtSeconds": (
                    ABSOLUTE_MAX_ACCEPTED_DT_SECONDS
                ),
                "absoluteMinimumAcceptedStepCount": (
                    ABSOLUTE_MIN_ACCEPTED_STEP_COUNT
                ),
                "acceptedDtStorage": "EXACT_ARRAY_D_FOR_BOUNDED_CANARY",
                "acceptedDtBytesPerStep": self._accepted_dt.itemsize,
                "actualAcceptedDtStorageBytes": (
                    len(self._accepted_dt) * self._accepted_dt.itemsize
                ),
                "maximumAcceptedDtStorageBytes": (
                    self.config.max_accepted_dt_storage_bytes
                ),
                "maximumAcceptedStepCount": (
                    self.config.max_accepted_step_count
                ),
                "approvedAs36HourOperationalDefault": False,
                "required36HourSuccessor": (
                    "SEPARATELY_REVIEWED_BOUNDED_MEMORY_QUANTILE_COLLECTOR"
                ),
            },
            "identity": {
                "runId": self.config.run_id,
                "meshId": self.config.mesh_id,
                "validationScope": (
                    "REQUIRED_LOWERCASE_NONZERO_SHA256_DECLARATIONS_"
                    "NOT_FILE_READBACK_NOT_SOLVER_CONNECTION"
                ),
                **self._identity_report,
            },
            "configuration": {
                "approvedLimiterFormulaId": (
                    self.config.approved_limiter_formula_id
                ),
                "requiredDtBoundNames": list(
                    self.config.required_dt_bound_names
                ),
                "cflTarget": self.config.cfl_target,
                "expectedCandidateCount": self.config.expected_candidate_count,
                "limiterTopK": self.config.limiter_top_k,
                "maxAcceptedStepCount": self.config.max_accepted_step_count,
                "maxAcceptedDtStorageBytes": (
                    self.config.max_accepted_dt_storage_bytes
                ),
                "zeroPhaseTimeExceptions": [
                    {"phase": phase, "reason": reason}
                    for phase, reason in self.config.zero_phase_time_exceptions
                ],
            },
            "stepAccounting": {
                "acceptedCount": self._accepted_count,
                "acceptedCumulativeModelSeconds": accepted_model_seconds,
                "rejectedCount": self._rejected_count,
                "totalProposalCount": (
                    self._accepted_count + self._rejected_count
                ),
                "rejectedByReason": dict(
                    sorted(self._rejected_by_reason.items())
                ),
            },
            "acceptedDtSeconds": {
                "count": self._accepted_count,
                "minimum": float(np.min(accepted)),
                "p01": float(quantiles[0]),
                "p50": float(quantiles[1]),
                "p95": float(quantiles[2]),
                "maximum": float(np.max(accepted)),
                "mean": float(np.mean(accepted)),
                "quantileMethod": (
                    "numpy_linear_exact_over_all_accepted_dt_values"
                ),
                "storageBoundary": (
                    "BOUNDED_900_TO_1200_SECOND_CANARY_ONLY_NOT_36H_DEFAULT"
                ),
            },
            "candidateScan": {
                "expectedCandidateCountPerProposal": (
                    self.config.expected_candidate_count
                ),
                "proposalCountWithCompleteCoverage": (
                    self._full_scan_proposal_count
                ),
                "evaluatedEqualsExpectedForEveryProposal": True,
                "coverageCompleteForEveryProposal": True,
            },
            "limiter": {
                "formulaId": self.config.approved_limiter_formula_id,
                "globalMinimumSelectedBoundEvent": (
                    self._global_minimum_event
                ),
                "minimumByBoundName": {
                    name: self._minimum_by_bound[name]
                    for name in self.config.required_dt_bound_names
                },
                "uniqueCandidateCount": len(self._candidate_counts),
                "topCandidates": top_candidates,
            },
            "wallTime": {
                "phaseSeconds": phase_seconds,
                "phaseTotalSeconds": phase_total,
                "totalRunnerWallSeconds": runner_total,
                "unclassifiedWallSeconds": unclassified,
                "phaseOrder": list(PHASES),
                "zeroPhaseTimeExceptionsApplied": [
                    {"phase": phase, "reason": zero_phase_exceptions[phase]}
                    for phase in PHASES
                    if self._phase_ns[phase] == 0
                    and phase in zero_phase_exceptions
                ],
            },
            "integration": {
                "connectedToLegacyOneHourRunner": False,
                "connectedToSolver": False,
                "intendedConnection": "future_per_gate_v2_successor_runner",
                "intendedCanaryDurationModelSeconds": [900, 1200],
            },
            "safeguards": {
                "solverEquationsChanged": False,
                "perStepFilesystemIo": False,
                (
                    "sha256RunMeshCheckpointForcingSolverControl"
                    "BathymetryRequired"
                ): True,
                (
                    "limiterFormulaRecomputedFromCellAreaAnd"
                    "SpectralRadiusFaceLengthSum"
                ): True,
                "approvedLimiterFormulaIdRequired": True,
                "exactKernelDtBoundNamesRequired": True,
                "fullCandidateScanRequiredForEveryProposal": True,
                "missingEvidenceFailsClosed": True,
                "acceptedDtCannotExceedSelectedMinimumBound": True,
                "absoluteAcceptedDtUpperLimitEnforced": True,
                "absoluteMinimumAcceptedStepCountEnforced": True,
                "acceptedModelDurationRangeValidatedAtFinalize": True,
                "acceptedStepCountLimitEnforcedBeforeAppend": True,
                "acceptedDtMemoryLimitEnforcedBeforeAppend": True,
                "positiveRunnerWallTimeRequired": True,
                "zeroPhaseTimeRequiresPredeclaredException": True,
                "allZeroPhaseAccountingRejected": True,
                "exactDtStorageApprovedFor36HourOperation": False,
            },
        }
        self._finalized = True
        return report
