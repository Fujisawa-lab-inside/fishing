#!/usr/bin/env python3
"""Candidate-only continuous operating schedule for the eight Onga barrage gates.

This module converts a discharge time series into gradual gate-capacity
multipliers. It is deliberately separate from the fail-closed Stage 20 binary
interface and is not connected to the physical solver or GUI.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    ROOT / "config/stage20_barrage_sequential_operation_candidate_v1.json"
)
GATE_IDS = tuple(range(1, 9))
EPSILON = 1.0e-12


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(
            f"[onga-stage20-barrage-sequential-operation-v1] {message}"
        )


def strict_load(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_constant=invalid,
    )


def smoothstep01(value: float) -> float:
    """Return 3s²−2s³ after clamping *value* to [0, 1]."""

    s = min(1.0, max(0.0, float(value)))
    return s * s * (3.0 - 2.0 * s)


@dataclass(frozen=True)
class Transition:
    gate_id: int
    start_time_sec: float
    duration_sec: float
    start_value: float
    target_value: float
    reason: str
    override: bool


class GateOperationScheduler:
    """Stateful candidate controller evaluated on an increasing time grid."""

    def __init__(self, config: dict[str, Any]):
        require(
            config.get("schema")
            == "onga-stage20-barrage-sequential-operation-candidate-v1",
            "unexpected config schema",
        )
        schedule = config.get("gateSchedule")
        require(isinstance(schedule, list) and len(schedule) == 8, "eight gates required")
        self.config = config
        self.schedule = tuple(schedule)
        self.open_order = tuple(int(row["gateId"]) for row in schedule)
        require(set(self.open_order) == set(GATE_IDS), "gate order must cover 1 through 8")
        self.close_order = tuple(reversed(self.open_order))
        controller = config["controller"]
        self.window_sec = float(controller["causalMovingAverageWindowSec"])
        self.persistence_sec = float(controller["normalTriggerPersistenceSec"])
        self.duration_sec = float(controller["transition"]["durationSec"])
        self.minimum_interval_sec = float(
            controller["normalMinimumCommandStartIntervalSec"]
        )
        emergency = controller["emergencyFullOpenOverride"]
        self.emergency_enter = float(emergency["enterAtOrAboveDischargeM3S"])
        self.emergency_exit = float(emergency["exitBelowDischargeM3S"])
        self.emergency_duration_sec = float(emergency["durationSec"])
        self.open_threshold = {
            int(row["gateId"]): float(row["openThresholdM3S"])
            for row in schedule
        }
        self.close_threshold = {
            int(row["gateId"]): float(row["closeThresholdM3S"])
            for row in schedule
        }
        self.opening = {gate_id: 0.0 for gate_id in GATE_IDS}
        self.transitions: dict[int, Transition] = {}
        self.events: list[dict[str, Any]] = []
        self.flow_history: deque[tuple[float, float]] = deque()
        self.last_time_sec: float | None = None
        self.last_command_start_sec = -math.inf
        self.condition_key: tuple[str, int] | None = None
        self.condition_since_sec: float | None = None
        self.emergency_latched = False

    def _event(self, event_type: str, time_sec: float, **values: Any) -> None:
        row: dict[str, Any] = {
            "eventType": event_type,
            "timeSec": float(time_sec),
        }
        row.update(values)
        self.events.append(row)

    def _filtered_flow(self, time_sec: float, raw_flow_m3s: float) -> float:
        require(math.isfinite(raw_flow_m3s) and raw_flow_m3s >= 0.0,
                "raw discharge must be finite and nonnegative")
        self.flow_history.append((time_sec, raw_flow_m3s))
        cutoff = time_sec - self.window_sec
        while len(self.flow_history) > 1 and self.flow_history[0][0] < cutoff:
            self.flow_history.popleft()
        return sum(row[1] for row in self.flow_history) / len(self.flow_history)

    def _update_transitions(self, time_sec: float, filtered_flow_m3s: float) -> None:
        completed: list[int] = []
        for gate_id, transition in self.transitions.items():
            phase = (time_sec - transition.start_time_sec) / transition.duration_sec
            weight = smoothstep01(phase)
            value = transition.start_value + (
                transition.target_value - transition.start_value
            ) * weight
            self.opening[gate_id] = min(1.0, max(0.0, value))
            if phase >= 1.0:
                self.opening[gate_id] = transition.target_value
                completed.append(gate_id)
                self._event(
                    "transition_complete",
                    time_sec,
                    gateId=gate_id,
                    targetOpeningFraction=transition.target_value,
                    filteredDischargeM3S=filtered_flow_m3s,
                    reason=transition.reason,
                    override=transition.override,
                )
        for gate_id in completed:
            del self.transitions[gate_id]

    def _start_transition(
        self,
        gate_id: int,
        target_value: float,
        time_sec: float,
        filtered_flow_m3s: float,
        *,
        reason: str,
        override: bool,
        duration_sec: float,
    ) -> None:
        start_value = self.opening[gate_id]
        if abs(start_value - target_value) <= EPSILON:
            return
        transition = Transition(
            gate_id=gate_id,
            start_time_sec=time_sec,
            duration_sec=duration_sec,
            start_value=start_value,
            target_value=target_value,
            reason=reason,
            override=override,
        )
        self.transitions[gate_id] = transition
        self._event(
            "command_start",
            time_sec,
            gateId=gate_id,
            startOpeningFraction=start_value,
            targetOpeningFraction=target_value,
            durationSec=duration_sec,
            filteredDischargeM3S=filtered_flow_m3s,
            reason=reason,
            override=override,
        )

    def _reset_condition(self) -> None:
        self.condition_key = None
        self.condition_since_sec = None

    def _condition_persisted(
        self,
        key: tuple[str, int],
        time_sec: float,
        condition: bool,
    ) -> bool:
        if not condition:
            self._reset_condition()
            return False
        if self.condition_key != key:
            self.condition_key = key
            self.condition_since_sec = time_sec
            return self.persistence_sec <= 0.0
        require(self.condition_since_sec is not None, "missing persistence start")
        return time_sec - self.condition_since_sec + EPSILON >= self.persistence_sec

    def _enter_emergency(self, time_sec: float, filtered_flow_m3s: float) -> None:
        self.emergency_latched = True
        self._reset_condition()
        self.last_command_start_sec = time_sec
        self._event(
            "emergency_enter",
            time_sec,
            filteredDischargeM3S=filtered_flow_m3s,
        )
        for gate_id in self.open_order:
            self._start_transition(
                gate_id,
                1.0,
                time_sec,
                filtered_flow_m3s,
                reason="emergency_full_open",
                override=True,
                duration_sec=self.emergency_duration_sec,
            )

    def step(self, time_sec: float, raw_flow_m3s: float) -> dict[str, Any]:
        """Advance the scheduler and return a serialisable snapshot."""

        time_sec = float(time_sec)
        raw_flow_m3s = float(raw_flow_m3s)
        require(math.isfinite(time_sec) and time_sec >= 0.0,
                "time must be finite and nonnegative")
        if self.last_time_sec is not None:
            require(time_sec > self.last_time_sec, "time must be strictly increasing")
        filtered = self._filtered_flow(time_sec, raw_flow_m3s)
        self._update_transitions(time_sec, filtered)

        if not self.emergency_latched and filtered >= self.emergency_enter:
            self._enter_emergency(time_sec, filtered)
        elif self.emergency_latched and filtered < self.emergency_exit:
            self.emergency_latched = False
            self._reset_condition()
            self._event(
                "emergency_exit",
                time_sec,
                filteredDischargeM3S=filtered,
            )

        if not self.emergency_latched and not self.transitions:
            interval_ready = (
                time_sec - self.last_command_start_sec + EPSILON
                >= self.minimum_interval_sec
            )
            next_open = next(
                (
                    gate_id
                    for gate_id in self.open_order
                    if self.opening[gate_id] < 1.0 - EPSILON
                ),
                None,
            )
            next_close = next(
                (
                    gate_id
                    for gate_id in self.close_order
                    if self.opening[gate_id] > EPSILON
                ),
                None,
            )
            open_condition = (
                next_open is not None
                and filtered >= self.open_threshold[next_open]
            )
            close_condition = (
                next_close is not None
                and filtered <= self.close_threshold[next_close]
            )
            if next_open is not None and open_condition:
                key = ("open", next_open)
                persisted = self._condition_persisted(key, time_sec, True)
                if persisted and interval_ready:
                    self._start_transition(
                        next_open,
                        1.0,
                        time_sec,
                        filtered,
                        reason="normal_threshold_open",
                        override=False,
                        duration_sec=self.duration_sec,
                    )
                    self.last_command_start_sec = time_sec
                    self._reset_condition()
            elif next_close is not None and close_condition:
                key = ("close", next_close)
                persisted = self._condition_persisted(key, time_sec, True)
                if persisted and interval_ready:
                    self._start_transition(
                        next_close,
                        0.0,
                        time_sec,
                        filtered,
                        reason="normal_threshold_close",
                        override=False,
                        duration_sec=self.duration_sec,
                    )
                    self.last_command_start_sec = time_sec
                    self._reset_condition()
            else:
                self._reset_condition()

        self.last_time_sec = time_sec
        return {
            "timeSec": time_sec,
            "rawDischargeM3S": raw_flow_m3s,
            "filteredDischargeM3S": filtered,
            "emergencyFullOpen": self.emergency_latched,
            "openingFractionByGateId": {
                str(gate_id): self.opening[gate_id] for gate_id in GATE_IDS
            },
        }


def simulate(
    config: dict[str, Any],
    times_sec: list[float],
    discharges_m3s: list[float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run a complete hydrograph through a fresh scheduler."""

    require(len(times_sec) == len(discharges_m3s) and len(times_sec) >= 2,
            "time and discharge arrays must have equal length of at least two")
    scheduler = GateOperationScheduler(config)
    snapshots = [
        scheduler.step(time_sec, discharge)
        for time_sec, discharge in zip(times_sec, discharges_m3s, strict=True)
    ]
    return snapshots, scheduler.events
