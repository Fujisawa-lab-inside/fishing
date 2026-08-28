#!/usr/bin/env python3

from __future__ import annotations

import base64
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import build_stage20_taskB_daily_tide_boundary_v1 as task_b  # noqa: E402
import stage20_parallel_forcing_integration_v1 as integration  # noqa: E402
import stage20_taskA_uncalibrated_historical_inflow_v1 as task_a  # noqa: E402


JST = timezone(timedelta(hours=9))
MODEL = json.loads(
    (
        ROOT / "config/stage20_taskA_uncalibrated_inflow_model_reference_v1.json"
    ).read_text(encoding="utf-8")
)


def make_weather(anchor: datetime) -> dict:
    first = anchor + timedelta(hours=-12 - MODEL["warmupHours"])
    count = MODEL["warmupHours"] + len(integration.HOURS)
    station_ids = ["yahata", "iizuka", "soeda", "munakata"]
    return {
        "schema": task_a.WEATHER_SCHEMA,
        "status": "synthetic_test_fixture_shaped_like_preserved_official_input",
        "timezone": "Asia/Tokyo",
        "intervalSemantics": "preceding_hour_ending_at_timestamp",
        "source": {
            "provider": "Japan Meteorological Agency",
            "dataset": "synthetic_contract_fixture_not_observation",
            "url": "https://www.data.jma.go.jp/risk/obsdl/index.php",
            "retrievedAt": (anchor + timedelta(days=2)).isoformat(timespec="seconds"),
            "sourceFileSha256": "0" * 64,
        },
        "stations": [
            {
                "id": station_id,
                "name": station_id,
                "providerStationCode": f"fixture-{station_id}",
                "samples": [
                    {
                        "timestamp": (first + timedelta(hours=index)).isoformat(
                            timespec="seconds"
                        ),
                        "precipitationMm": (
                            10.0
                            if index == MODEL["warmupHours"] + 6
                            else 0.0
                        ),
                        "qualityCode": 8,
                    }
                    for index in range(count)
                ],
            }
            for station_id in station_ids
        ],
    }


def local_tide_result(requested_date: str = "2026-02-15") -> dict:
    request = {
        "schema": task_b.INPUT_SCHEMA,
        "requestedDate": requested_date,
        "station": {"code": "QF", "name": "博多"},
        "window": {"startHour": -12, "endHour": 24, "stepHours": 1},
        "source": {
            "mode": "local_snapshot_set",
            "yearFiles": {
                "2026": "data/jma_hakata_2026_hourly_tide_QF.txt"
            },
        },
        "failurePolicy": "fail_closed",
    }
    result, exit_code = task_b.execute_request(request, root=ROOT)
    if exit_code != 0:
        raise AssertionError(result)
    return result


def raw_jma_csv(anchor: datetime) -> bytes:
    station_names = ["八幡", "飯塚", "添田", "宗像"]
    first = anchor + timedelta(hours=-12 - MODEL["warmupHours"])
    count = MODEL["warmupHours"] + len(integration.HOURS)
    rows = [
        [
            "ダウンロードした時刻："
            + (anchor + timedelta(days=2)).strftime("%Y/%m/%d %H:%M:%S")
        ],
        [""] + [name for name in station_names for _ in range(3)],
        ["年月日時"]
        + ["降水量の合計(mm)" for _ in range(len(station_names) * 3)],
        [""] + ["", "現象なし情報", "品質情報"] * len(station_names),
    ]
    for index in range(count):
        timestamp = first + timedelta(hours=index)
        rows.append(
            [timestamp.strftime("%Y/%m/%d %H:%M")]
            + ["0.0", "1", "8"] * len(station_names)
        )
    return (
        "\n".join(",".join(row) for row in rows) + "\n"
    ).encode("utf-8")


class ParallelForcingIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.anchor = datetime(2026, 2, 15, 0, tzinfo=JST)
        self.inflow = task_a.estimate_historical_inflows(
            make_weather(self.anchor),
            MODEL,
            self.anchor.isoformat(timespec="seconds"),
        )
        self.tide = local_tide_result()

    def test_three_parallel_artifacts_merge_on_exact_37_hour_grid(self) -> None:
        result = integration.build_integrated_forcing(
            self.inflow,
            self.tide,
            created_at="2026-07-27T00:00:00+00:00",
        )
        self.assertEqual(result["schema"], integration.RESULT_SCHEMA)
        self.assertEqual(result["status"], "reference_forcing_ready")
        self.assertEqual(result["hours"], list(range(-12, 25)))
        self.assertEqual(len(result["timestampsJst"]), 37)
        for values in result["series"].values():
            self.assertEqual(len(values), 37)
        self.assertEqual(
            result["automaticGateOperation"]["openingOrder"],
            [5, 4, 6, 3, 7, 2, 8, 1],
        )
        self.assertEqual(
            len(result["automaticGateOperation"]["capacityFractionByGateId"]),
            37,
        )
        self.assertTrue(result["connection"]["guiDisplayConnected"])
        self.assertTrue(result["connection"]["automaticGateSelectionConnected"])
        self.assertTrue(result["connection"]["localR1CGateOnlyRunConnected"])
        self.assertFalse(result["connection"]["riverAndTideBoundaryPhysicsConnected"])

    def test_gate_patterns_are_binary_and_follow_the_fixed_order(self) -> None:
        for stage in range(9):
            pattern = integration.gate_pattern_for_stage(stage)
            expected_open = set(integration.GATE_OPENING_ORDER[:stage])
            actual_open = {
                index + 1 for index, value in enumerate(pattern) if value == 1
            }
            self.assertEqual(actual_open, expected_open)
            self.assertTrue(all(value in (0, 1) for value in pattern))

    def test_task_timestamp_mismatch_fails_closed(self) -> None:
        broken = json.loads(json.dumps(self.tide))
        broken["sourceSeries"]["timestampsJst"][0] = "2026-02-14T13:00:00+09:00"
        with self.assertRaisesRegex(integration.IntegrationError, "timestamps"):
            integration.build_integrated_forcing(self.inflow, broken)

    def test_response_pack_violations_are_reported_without_clipping(self) -> None:
        broken = json.loads(json.dumps(self.inflow))
        broken["rivers"]["O"]["samples"][0]["referenceDischargeM3S"] = 200.0
        broken["rivers"]["O"]["samples"][0]["sensitivityHighM3S"] = 220.0
        result = integration.build_integrated_forcing(broken, self.tide)
        self.assertEqual(result["series"]["ongaDischargeM3S"][0], 200.0)
        self.assertFalse(
            result["compatibility"]["responsePackEnvelopeCompatible"]
        )
        self.assertFalse(result["compatibility"]["valuesClipped"])

    def test_raw_jma_csv_and_tide_build_end_to_end_reference_document(self) -> None:
        request = {
            "schema": integration.REQUEST_SCHEMA,
            "requestedDate": "2026-02-15",
            "jmaCsvBase64": base64.b64encode(
                raw_jma_csv(self.anchor)
            ).decode("ascii"),
            "tideFailurePolicy": "fail_closed",
        }
        with patch.object(
            task_b.urllib.request,
            "urlopen",
            side_effect=AssertionError("network access is forbidden in M0"),
        ) as urlopen:
            result = integration.build_from_client_request(
                request,
                retrieved_at="2026-02-17T12:00:00+09:00",
            )
        urlopen.assert_not_called()
        self.assertEqual(result["status"], "reference_forcing_ready")
        self.assertEqual(result["requestedDate"], "2026-02-15")
        self.assertEqual(result["series"]["ongaDischargeM3S"], [15.0] * 37)
        self.assertEqual(result["series"]["nishiDischargeM3S"], [0.7] * 37)
        self.assertEqual(result["series"]["magariDischargeM3S"], [0.5] * 37)
        self.assertEqual(
            result["sourceArtifacts"]["tide"]["provenance"]["sourceFiles"][0]["locator"],
            "data/jma_hakata_2026_hourly_tide_QF.txt",
        )
        serialized = json.dumps(result, ensure_ascii=False)
        forbidden_prefixes = (
            "/" + "Users" + "/",
            "/" + "home" + "/",
            "/" + "private" + "/" + "tmp" + "/",
            "/" + "tmp" + "/",
            "C:" + "\\" + "Users" + "\\",
        )
        for prefix in forbidden_prefixes:
            self.assertNotIn(prefix, serialized)
        self.assertEqual(
            result["runtimePolicy"],
            {
                "offlineOnly": True,
                "networkFetchAttempted": False,
                "tideSourcePolicy": "preserved_local_snapshot_or_fail_closed",
                "tideSourceModeResolved": "local_snapshot_set",
            },
        )

    def test_missing_local_tide_snapshot_fails_without_network_fallback(self) -> None:
        anchor = datetime(2027, 2, 15, 0, tzinfo=JST)
        request = {
            "schema": integration.REQUEST_SCHEMA,
            "requestedDate": "2027-02-15",
            "jmaCsvBase64": base64.b64encode(raw_jma_csv(anchor)).decode("ascii"),
            "tideFailurePolicy": "fail_closed",
        }
        with patch.object(
            task_b.urllib.request,
            "urlopen",
            side_effect=AssertionError("network access is forbidden in M0"),
        ) as urlopen:
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "no complete registered offline tide snapshot window",
            ):
                integration.build_from_client_request(
                    request,
                    retrieved_at="2027-02-17T12:00:00+09:00",
                )
        urlopen.assert_not_called()

    def test_capability_reports_offline_only_forcing(self) -> None:
        capability = integration.capability_document()
        self.assertEqual(capability["status"], "READY_OFFLINE")
        self.assertIs(capability["offlineOnly"], True)
        self.assertIs(capability["networkFetchAllowed"], False)
        self.assertEqual(
            capability["tideSourcePolicy"],
            "preserved_local_snapshot_or_fail_closed",
        )
        self.assertEqual(capability["availableTideSnapshotYears"], [2026])
        self.assertEqual(
            capability["availableRequestedDateRanges"],
            [{"start": "2026-01-02", "end": "2026-12-30"}],
        )
        self.assertEqual(capability["defaultRequestedDate"], "2026-02-15")

    def test_offline_date_ranges_merge_only_contiguous_registered_years(self) -> None:
        self.assertEqual(
            integration.available_local_tide_date_ranges([2025, 2026, 2028]),
            [
                {"start": "2025-01-02", "end": "2026-12-30"},
                {"start": "2028-01-02", "end": "2028-12-30"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
