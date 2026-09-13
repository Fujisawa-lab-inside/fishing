#!/usr/bin/env python3
"""Rank explainable A1--A8 opening combinations from low-cost evidence.

Official total release constrains only the aggregate effective opening.  It
cannot identify a gate.  This diagnostic therefore enumerates all 256 main-
gate subsets and ranks them using the published *inflow* operation band,
positive-only image cues, and optional temporal continuity.  The result is a
relative candidate ranking, never a gate-state label or calibrated
probability.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import uuid
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/stage20_gate_configuration_candidate_estimator_v1.json"
DEFAULT_BAND_CONFIG = ROOT / "config/stage20_barrage_official_operation_band_dispatch_v1.json"
SCHEMA = "onga-stage20-gate-configuration-candidate-estimator-v1-result"
STATUS = "PASS_DIAGNOSTIC_GATE_CONFIGURATION_CANDIDATES_NOT_GATE_LABEL"
GATE_IDS = tuple(f"A{index}" for index in range(1, 9))
GRAVITY_M_S2 = 9.80665


class CandidateEstimatorError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateEstimatorError(
            f"[stage20-gate-configuration-candidate-estimator-v1] {message}"
        )


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CandidateEstimatorError(
            f"[stage20-gate-configuration-candidate-estimator-v1] invalid {label}: {path}"
        ) from error
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _finite(value: Any, label: str, *, minimum: float | None = None) -> float:
    require(not isinstance(value, bool), f"{label} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise CandidateEstimatorError(
            f"[stage20-gate-configuration-candidate-estimator-v1] {label} must be numeric"
        ) from error
    require(math.isfinite(result), f"{label} must be finite")
    if minimum is not None:
        require(result >= minimum, f"{label} must be at least {minimum}")
    return result


def _unit_interval(value: Any, label: str) -> float:
    result = _finite(value, label)
    require(0.0 <= result <= 1.0, f"{label} must remain within 0..1")
    return result


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = _load_json(path, "estimator config")
    require(
        config.get("schema") == "onga-stage20-gate-configuration-candidate-estimator-v1",
        "estimator config schema changed",
    )
    require(
        config.get("status") == "DIAGNOSTIC_CANDIDATE_NOT_PHYSICAL_GATE_STATE",
        "estimator classification changed",
    )
    require(tuple(config.get("gateIds", ())) == GATE_IDS, "gate IDs must be A1 through A8")
    boundary = config.get("boundary", {})
    require(boundary.get("candidateRankingPermitted") is True, "candidate ranking is disabled")
    for forbidden in (
        "perGateOpeningDeclared",
        "trainingLabelGenerated",
        "openingFractionInferred",
        "microGateDischargeResolved",
        "fishwayDischargeResolved",
        "physicalValidation",
        "hydraulicSolverExecuted",
        "forecastAuthorized",
        "fishingDecisionAuthorized",
    ):
        require(boundary.get(forbidden) is False, f"forbidden boundary enabled: {forbidden}")
    return config


def load_band_config(path: Path = DEFAULT_BAND_CONFIG) -> dict[str, Any]:
    config = _load_json(path, "operation-band config")
    require(
        config.get("schema") == "onga-stage20-barrage-official-operation-band-dispatch-v1",
        "operation-band config schema changed",
    )
    require(isinstance(config.get("bands"), list), "operation bands are absent")
    return config


def classify_inflow(inflow_m3_s: float, band_config: Mapping[str, Any]) -> dict[str, Any]:
    value = _finite(inflow_m3_s, "barrage inflow", minimum=0.0)
    below = band_config.get("belowPublishedMinimum", {})
    if value < _finite(below.get("maximumExclusiveM3S"), "below-band maximum"):
        return dict(below)
    for band in band_config["bands"]:
        minimum = _finite(band.get("minimumInclusiveM3S"), "band minimum")
        maximum_raw = band.get("maximumExclusiveM3S")
        maximum = None if maximum_raw is None else _finite(maximum_raw, "band maximum")
        if value >= minimum and (maximum is None or value < maximum):
            return dict(band)
    raise CandidateEstimatorError(
        "[stage20-gate-configuration-candidate-estimator-v1] no operation band matched"
    )


def _expected_count_and_priors(
    inflow_m3_s: float,
    band: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[float, float, dict[str, float]]:
    control_class = str(band.get("controlClass"))
    model = config["bandModel"].get(control_class)
    require(isinstance(model, Mapping), f"band model is absent for {control_class}")
    if control_class == "STAGED_CONTROL_MAIN_GATE_DRIVE_BAND":
        lower = _finite(band.get("minimumInclusiveM3S"), "staged-band minimum")
        upper = _finite(band.get("maximumExclusiveM3S"), "staged-band maximum")
        fraction = min(1.0, max(0.0, (inflow_m3_s - lower) / (upper - lower)))
        expected = _finite(model["minimumExpectedOpenMainGateCount"], "minimum expected count") + fraction * (
            _finite(model["maximumExpectedOpenMainGateCount"], "maximum expected count")
            - _finite(model["minimumExpectedOpenMainGateCount"], "minimum expected count")
        )
        base = min(0.94, max(0.06, expected / len(GATE_IDS)))
        priors = {gate_id: base for gate_id in GATE_IDS}
    else:
        expected = _finite(model["expectedOpenMainGateCount"], "expected open count")
        base = _unit_interval(model["baseOpenSupport"], "base open support")
        priors = {gate_id: base for gate_id in GATE_IDS}
        if "a8OpenSupport" in model:
            priors["A8"] = _unit_interval(model["a8OpenSupport"], "A8 open support")
    sigma = _finite(model["countSigma"], "count sigma", minimum=0.01)
    return expected, sigma, priors


def normalize_image_evidence(value: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if value is None:
        return {gate_id: {} for gate_id in GATE_IDS}
    require(isinstance(value, Mapping), "image evidence must be an object")
    raw_by_gate = value.get("byGateId", value)
    require(isinstance(raw_by_gate, Mapping), "image evidence byGateId must be an object")
    unknown = set(raw_by_gate) - set(GATE_IDS)
    require(not unknown, f"unknown image-evidence gate IDs: {sorted(unknown)}")
    normalized: dict[str, dict[str, Any]] = {}
    for gate_id in GATE_IDS:
        raw = raw_by_gate.get(gate_id, {})
        require(isinstance(raw, Mapping), f"image evidence for {gate_id} must be an object")
        lamp = raw.get("pairedOrangeLampsVisible")
        require(lamp is None or type(lamp) is bool, f"paired-orange-lamp cue for {gate_id} must be boolean or null")
        item: dict[str, Any] = {"pairedOrangeLampsVisible": lamp}
        for field in ("gateLeafOpeningSupport0To1", "downstreamPlumeSupport0To1"):
            item[field] = None if raw.get(field) is None else _unit_interval(raw[field], f"{field} for {gate_id}")
        normalized[gate_id] = item
    return normalized


def normalize_previous_support(value: Mapping[str, Any] | None) -> dict[str, float] | None:
    if value is None:
        return None
    if "gateOpenSupportByGateId" in value:
        value = value["gateOpenSupportByGateId"]
    require(isinstance(value, Mapping), "previous gate support must be an object")
    require(set(value) == set(GATE_IDS), "previous gate support must contain exactly A1 through A8")
    return {gate_id: _unit_interval(value[gate_id], f"previous support for {gate_id}") for gate_id in GATE_IDS}


def _log_bernoulli(is_open: bool, probability: float) -> float:
    bounded = min(1.0 - 1e-9, max(1e-9, probability))
    return math.log(bounded if is_open else 1.0 - bounded)


def _centered_support_log_score(is_open: bool, support: float, weight: float) -> float:
    signed = 2.0 * (support - 0.5)
    return weight * signed * (1.0 if is_open else -1.0)


def _configuration_log_score(
    open_gates: frozenset[str],
    *,
    expected_count: float,
    count_sigma: float,
    priors: Mapping[str, float],
    image_evidence: Mapping[str, Mapping[str, Any]],
    previous_support: Mapping[str, float] | None,
    config: Mapping[str, Any],
) -> tuple[float, list[str]]:
    weights = config["evidenceWeights"]
    score = -0.5 * ((len(open_gates) - expected_count) / count_sigma) ** 2
    reasons: list[str] = []
    for gate_id in GATE_IDS:
        is_open = gate_id in open_gates
        score += _log_bernoulli(is_open, priors[gate_id])
        evidence = image_evidence[gate_id]
        if evidence.get("pairedOrangeLampsVisible") is True:
            if is_open:
                score += _finite(weights["pairedOrangeLampsVisibleOpenLogBonus"], "lamp bonus")
                reasons.append(f"{gate_id}:paired-orange-lamps")
            else:
                score -= _finite(weights["pairedOrangeLampsContradictedClosedPenalty"], "lamp contradiction penalty")
        leaf = evidence.get("gateLeafOpeningSupport0To1")
        if leaf is not None:
            score += _centered_support_log_score(
                is_open,
                float(leaf),
                _finite(weights["gateLeafOpeningSupportLogWeight"], "gate-leaf weight"),
            )
        plume = evidence.get("downstreamPlumeSupport0To1")
        if plume is not None:
            score += _centered_support_log_score(
                is_open,
                float(plume),
                _finite(weights["downstreamPlumeSupportLogWeight"], "plume weight"),
            )
        if previous_support is not None:
            score += _finite(weights["previousGateSupportLogWeight"], "temporal weight") * _log_bernoulli(
                is_open, previous_support[gate_id]
            )

    weak_order = list(config["weakOpeningOrder"]["gateIds"])
    maximum_bonus = _finite(config["weakOpeningOrder"]["logScoreBonusMaximum"], "weak-order bonus")
    preferred_count = max(0, min(len(GATE_IDS), round(expected_count)))
    preferred = set(weak_order[:preferred_count])
    if preferred:
        score += maximum_bonus * len(open_gates & preferred) / len(preferred)
    return score, reasons


def rank_candidates(
    *,
    inflow_m3_s: float,
    release_m3_s: float,
    upstream_level_m: float,
    downstream_level_m: float,
    image_evidence: Mapping[str, Any] | None = None,
    previous_support: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
    band_config: Mapping[str, Any] | None = None,
    top_k: int = 3,
) -> dict[str, Any]:
    estimator = dict(config or load_config())
    bands = dict(band_config or load_band_config())
    inflow = _finite(inflow_m3_s, "barrage inflow", minimum=0.0)
    release = _finite(release_m3_s, "barrage release", minimum=0.0)
    upstream = _finite(upstream_level_m, "upstream level")
    downstream = _finite(downstream_level_m, "downstream level")
    require(type(top_k) is int and 1 <= top_k <= 20, "top_k must be an integer within 1..20")
    band = classify_inflow(inflow, bands)
    expected_count, count_sigma, priors = _expected_count_and_priors(inflow, band, estimator)
    image = normalize_image_evidence(image_evidence)
    previous = normalize_previous_support(previous_support)

    scored: list[dict[str, Any]] = []
    for flags in itertools.product((False, True), repeat=len(GATE_IDS)):
        open_gates = frozenset(gate_id for gate_id, flag in zip(GATE_IDS, flags, strict=True) if flag)
        log_score, reasons = _configuration_log_score(
            open_gates,
            expected_count=expected_count,
            count_sigma=count_sigma,
            priors=priors,
            image_evidence=image,
            previous_support=previous,
            config=estimator,
        )
        scored.append({"openGateIds": sorted(open_gates, key=lambda item: int(item[1:])), "logScore": log_score, "positiveReasons": reasons})
    maximum = max(row["logScore"] for row in scored)
    denominator = sum(math.exp(row["logScore"] - maximum) for row in scored)
    for row in scored:
        row["candidateWeight"] = math.exp(row["logScore"] - maximum) / denominator
    scored.sort(key=lambda row: (-row["candidateWeight"], row["openGateIds"]))

    marginal = {
        gate_id: sum(row["candidateWeight"] for row in scored if gate_id in row["openGateIds"])
        for gate_id in GATE_IDS
    }
    head = upstream - downstream
    equivalent_cd_area = None
    if head > 0.0:
        equivalent_cd_area = release / math.sqrt(2.0 * GRAVITY_M_S2 * head)
    positive_lamps = [
        gate_id for gate_id in GATE_IDS if image[gate_id].get("pairedOrangeLampsVisible") is True
    ]
    top_rows = []
    for rank, row in enumerate(scored[:top_k], start=1):
        top_rows.append(
            {
                "rank": rank,
                "openGateIds": row["openGateIds"],
                "openMainGateCount": len(row["openGateIds"]),
                "relativeCandidateWeight": round(row["candidateWeight"], 9),
                "positiveEvidence": row["positiveReasons"],
            }
        )
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "classification": estimator["status"],
        "inputs": {
            "barrageInflowM3S": inflow,
            "barrageReleaseM3S": release,
            "barrageUpstreamLevelM": upstream,
            "barrageDownstreamLevelM": downstream,
            "headDifferenceM": head,
        },
        "operationBand": {
            "controlClass": band["controlClass"],
            "classifiedFrom": "barrageInflowM3S",
            "expectedOpenMainGateCountHeuristic": expected_count,
            "countUncertaintySigmaGates": count_sigma,
        },
        "aggregateHydraulicConstraint": {
            "equivalentDischargeCoefficientTimesAreaM2": equivalent_cd_area,
            "equation": "Q/sqrt(2*g*(upstreamLevel-downstreamLevel))",
            "gateIdentityResolvedByConstraint": False,
            "perGateCapacityCalibrationApplied": False,
            "unresolvedContributors": ["micro-adjustment gate", "fishway", "storage and timing mismatch"],
        },
        "evidenceSummary": {
            "positivePairedOrangeLampGateIds": positive_lamps,
            "unlitOrMissingLampInterpretedAsClosed": False,
            "previousStateSupportApplied": previous is not None,
            "weakOpeningOrderAppliedAsGroundTruth": False,
        },
        "topConfigurations": top_rows,
        "gateOpenSupportByGateId": {gate_id: round(marginal[gate_id], 9) for gate_id in GATE_IDS},
        "ambiguity": {
            "enumeratedMainGateConfigurations": len(scored),
            "topCandidateWeight": round(scored[0]["candidateWeight"], 9),
            "topTwoWeightGap": round(scored[0]["candidateWeight"] - scored[1]["candidateWeight"], 9),
            "singleConfigurationEstablished": False,
        },
        "boundary": {
            "perGateStateLabelGenerated": False,
            "candidateWeightsAreCalibratedProbabilities": False,
            "openingFractionsInferred": False,
            "physicalGateStateEstablished": False,
            "hydraulicSolverExecuted": False,
        },
    }


def estimate_observation(
    observation_path: Path,
    *,
    image_evidence_path: Path | None = None,
    previous_report_path: Path | None = None,
    config_path: Path = DEFAULT_CONFIG,
    band_config_path: Path = DEFAULT_BAND_CONFIG,
    top_k: int = 3,
) -> dict[str, Any]:
    observation = _load_json(observation_path, "observation")
    point = observation.get("parsed", {}).get("barragePoint", {})
    values = point.get("values", {})
    require(isinstance(values, Mapping), "barrage point values are absent")
    image_evidence = None if image_evidence_path is None else _load_json(image_evidence_path, "image evidence")
    previous = None if previous_report_path is None else _load_json(previous_report_path, "previous report")
    result = rank_candidates(
        inflow_m3_s=values.get("barrageInflowM3S"),
        release_m3_s=values.get("barrageReleaseM3S"),
        upstream_level_m=values.get("barrageUpstreamLevelM"),
        downstream_level_m=values.get("barrageDownstreamLevelM"),
        image_evidence=image_evidence,
        previous_support=previous,
        config=load_config(config_path),
        band_config=load_band_config(band_config_path),
        top_k=top_k,
    )
    result["observation"] = {
        "runId": observation.get("runId"),
        "pointObservedAt": point.get("observedAt"),
        "path": str(observation_path.resolve()),
        "sha256": sha256_file(observation_path),
    }
    result["imageEvidence"] = None if image_evidence_path is None else {
        "path": str(image_evidence_path.resolve()),
        "sha256": sha256_file(image_evidence_path),
    }
    return result


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(canonical_bytes(value))
    os.replace(temporary, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--image-evidence", type=Path)
    parser.add_argument("--previous-report", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--band-config", type=Path, default=DEFAULT_BAND_CONFIG)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = estimate_observation(
            args.observation.resolve(),
            image_evidence_path=None if args.image_evidence is None else args.image_evidence.resolve(),
            previous_report_path=None if args.previous_report is None else args.previous_report.resolve(),
            config_path=args.config.resolve(),
            band_config_path=args.band_config.resolve(),
            top_k=args.top_k,
        )
        _atomic_write(args.output.resolve(), result)
        print(json.dumps({"status": result["status"], "output": str(args.output.resolve()), "topConfigurations": result["topConfigurations"]}, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "FAILED_NO_GATE_STATE_LABEL", "errorType": type(error).__name__, "message": str(error)}, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
