from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import serve_stage20_local_simulator_v1 as service
import build_stage20_taskB_daily_tide_boundary_v1 as task_b
import run_stage20_local_R1C_simulation_v1 as local_runner


LOCAL_REQUIRED_ASSET_IDS = [
    "r1c_review_mesh",
    "r1c_initial_checkpoint",
    "r1c_diagnostic_replay_binary",
    "fishway_constant_weak_flow_coupling_candidate",
    "r1c_review_mesh_summary",
    "fishway_c2_storage_candidate",
    "physical_pilot_source_contract",
    "physical_pilot_source_mesh_manifest",
    "synthetic_mesh_binary",
    "onga_water_mask_manifest_r3",
    "onga_water_mask_rows_r3_0",
    "onga_water_mask_rows_r3_1",
    "onga_water_mask_rows_r3_2",
    "onga_water_mask_rows_r3_3",
    "physical_pilot_final_fields",
    "stage19_m_boundary_tide_candidate",
    "physical_pilot_report",
]


def make_handler(
    path: str,
    headers: dict[str, str],
    payload: dict[str, object] | None = None,
) -> service.Stage20Handler:
    body = json.dumps(payload or {}).encode("utf-8")
    handler = object.__new__(service.Stage20Handler)
    handler.path = path
    handler.headers = {**headers, "Content-Length": str(len(body))}
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.server = SimpleNamespace(server_port=4173)
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler.send_json = Mock()
    return handler


def valid_post_headers() -> dict[str, str]:
    return {
        "Host": "127.0.0.1:4173",
        "Origin": "http://127.0.0.1:4173",
        "Content-Type": "application/json; charset=utf-8",
        service.CSRF_HEADER_NAME: service.CSRF_TOKEN,
    }


class LocalServiceM0Test(unittest.TestCase):
    def test_direct_runner_uses_the_same_exact_runtime_asset_contract(self) -> None:
        self.assertEqual(
            list(local_runner.EXPECTED_RUNTIME_ASSETS),
            LOCAL_REQUIRED_ASSET_IDS,
        )
        self.assertEqual(
            list(service.LOCAL_RUNTIME_REQUIRED_ASSET_IDS),
            LOCAL_REQUIRED_ASSET_IDS,
        )
        registry = json.loads(
            (ROOT / "config/stage20_runtime_assets_v2.json").read_text(
                encoding="utf-8"
            )
        )
        asset_by_id = {asset["id"]: asset for asset in registry["assets"]}
        for asset_id, expected in local_runner.EXPECTED_RUNTIME_ASSETS.items():
            with self.subTest(asset_id=asset_id):
                asset = asset_by_id[asset_id]
                self.assertEqual(
                    (asset["path"], asset["byteLength"], asset["sha256"]),
                    expected,
                )

    def test_local_report_excludes_standard_cycle_only_authority(self) -> None:
        requested: list[Path] = []

        def fake_binding(path: Path) -> dict[str, object]:
            requested.append(path)
            return {"path": path.relative_to(ROOT).as_posix()}

        c22 = local_runner.c22
        with patch.object(c22, "binding", side_effect=fake_binding), patch.object(
            c22,
            "sha256",
            side_effect=AssertionError("standard-cycle SHA read in local context"),
        ):
            authority, tide = c22.stage_report_provenance(
                c22.LOCAL_REPORT_CONTEXT,
                23.25,
            )
        self.assertEqual(
            requested,
            [
                c22.c2.base.c1.short.SOURCE_CONTRACT,
                c22.c2.base.c1.short.SOURCE_REPORT,
                c22.c2.base.c1.short.TIDE_CANDIDATE,
            ],
        )
        self.assertNotIn(c22.PLAN, requested)
        self.assertNotIn(c22.APPROVAL, requested)
        self.assertNotIn(c22.TIDE_EXTENSION, requested)
        self.assertNotIn(c22.JMA_SNAPSHOT, requested)
        self.assertEqual(authority["reportContext"], c22.LOCAL_REPORT_CONTEXT)
        self.assertIs(authority["standardCyclePlanApplied"], False)
        self.assertIs(
            authority["standardCycleExecutionApprovalApplied"],
            False,
        )
        self.assertIs(tide["hour24ExtensionUsed"], False)
        self.assertIs(tide["JMASnapshotReadAtRuntime"], False)
        with self.assertRaisesRegex(RuntimeError, "undeclared tide extension"):
            c22.stage_report_provenance(c22.LOCAL_REPORT_CONTEXT, 24.01)

    def test_local_runner_passes_local_context_to_shared_core(self) -> None:
        sentinel = ({"outcome": "test"}, {}, object(), 0.0)
        stage = {"stageId": "LOCAL_TEST"}
        initial_state = object()
        with patch.object(
            local_runner.c22,
            "run_stage_solver",
            return_value=sentinel,
        ) as run_core:
            observed = local_runner.run_local_stage_solver(stage, initial_state)
        self.assertIs(observed, sentinel)
        run_core.assert_called_once_with(
            stage,
            initial_state,
            None,
            None,
            report_context=local_runner.c22.LOCAL_REPORT_CONTEXT,
        )

    def test_fishway_candidate_runtime_projection_ignores_visual_locator(
        self,
    ) -> None:
        e1 = local_runner.c22.e1
        selected = {"upstream": {"id": "u"}, "downstream": {"id": "d"}}
        document = {
            "candidatePairs": {"separated": selected},
            "judgmentVisual": {"inlinePath": "inert-provenance-only"},
        }
        with patch.object(e1, "read_json", return_value=document) as read_json:
            observed = e1.load_separated_p2_candidate()
        self.assertEqual(observed, selected)
        read_json.assert_called_once_with(e1.c1.short.P2_CANDIDATE)

    def test_runtime_paths_are_local_and_interpreter_is_inherited(self) -> None:
        self.assertEqual(service.PYTHON, Path(sys.executable).resolve())
        self.assertEqual(
            service.JOBS_ROOT,
            ROOT / ".stage20-local-only/stage20-local-simulator-jobs",
        )
        self.assertEqual(
            service.LEGACY_JOBS_ROOT,
            ROOT / "docs/results/stage20-local-simulator-jobs",
        )

    def test_capability_contract_keeps_local_boundary_narrow(self) -> None:
        capability = service.local_runtime_capability()
        self.assertEqual(capability["gateEffect"], "explicit_run_updates_local_solver")
        self.assertEqual(
            capability["riverTideBoundaryPhysics"],
            "unconnected_fixed_local_conditions",
        )
        self.assertEqual(
            capability["fishwayRepresentation"],
            "local_uncalibrated_lumped_C2_1",
        )
        for field in (
            "calibrated",
            "fieldPrediction",
            "catchProbability",
            "operationalFishingAdvice",
            "safetyAuthority",
            "publicRuntime",
        ):
            self.assertIs(capability[field], False)

    def test_legacy_job_fallback_is_read_only_and_uses_api_urls(self) -> None:
        job_id = "local-20260826T120000-012345abcdef"
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            current_root = temporary_root / "current"
            legacy_root = temporary_root / "legacy"
            legacy_job = legacy_root / job_id
            legacy_job.mkdir(parents=True)
            (legacy_job / "server-status.json").write_text(
                json.dumps({"status": "RUNNING", "completed": False}),
                encoding="utf-8",
            )
            (legacy_job / "status.json").write_text(
                json.dumps({"status": "PASS"}),
                encoding="utf-8",
            )
            with patch.object(service, "JOBS_ROOT", current_root), patch.object(
                service,
                "LEGACY_JOBS_ROOT",
                legacy_root,
            ):
                selected = service.job_output_dir(job_id)
                status = service.public_job_status(job_id)
            self.assertEqual(selected, legacy_job)
            self.assertTrue(status["resultUsable"])
            self.assertEqual(
                status["manifestUrl"],
                f"/api/stage20/local/jobs/{job_id}/artifacts/browser-manifest.json",
            )
            self.assertFalse(current_root.exists())

    def test_post_header_gate_rejects_before_solver_or_network_side_effects(self) -> None:
        cases = (
            (
                "missing Host",
                {
                    "Origin": "http://127.0.0.1:4173",
                    "Content-Type": "application/json",
                    service.CSRF_HEADER_NAME: service.CSRF_TOKEN,
                },
                HTTPStatus.FORBIDDEN,
            ),
            (
                "non-loopback Host",
                {
                    **valid_post_headers(),
                    "Host": "attacker.example:4173",
                    "Origin": "http://attacker.example:4173",
                },
                HTTPStatus.FORBIDDEN,
            ),
            (
                "missing Origin",
                {
                    key: value
                    for key, value in valid_post_headers().items()
                    if key != "Origin"
                },
                HTTPStatus.FORBIDDEN,
            ),
            (
                "cross-origin Origin",
                {
                    **valid_post_headers(),
                    "Origin": "http://localhost:4173",
                },
                HTTPStatus.FORBIDDEN,
            ),
            (
                "wrong media type",
                {**valid_post_headers(), "Content-Type": "text/plain"},
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            ),
            (
                "missing token",
                {
                    key: value
                    for key, value in valid_post_headers().items()
                    if key != service.CSRF_HEADER_NAME
                },
                HTTPStatus.FORBIDDEN,
            ),
            (
                "wrong token",
                {**valid_post_headers(), service.CSRF_HEADER_NAME: "wrong"},
                HTTPStatus.FORBIDDEN,
            ),
        )
        with patch.object(service.MANAGER, "create") as create_job, patch.object(
            service,
            "build_from_client_request",
        ) as build_forcing, patch.object(
            service.subprocess,
            "run",
        ) as run_solver, patch.object(
            task_b.urllib.request,
            "urlopen",
        ) as urlopen:
            for label, headers, expected_status in cases:
                for path, payload in (
                    (
                        "/api/stage20/local/jobs",
                        {
                            "gateCapacityFractionById": [0] * 8,
                            "durationS": 5,
                        },
                    ),
                    (
                        "/api/stage20/forcing/build",
                        {"schema": "blocked-before-payload-validation"},
                    ),
                ):
                    with self.subTest(label=label, path=path):
                        handler = make_handler(path, headers, payload)
                        handler.do_POST()
                        self.assertEqual(
                            handler.send_json.call_args.args[0],
                            expected_status,
                        )
            create_job.assert_not_called()
            build_forcing.assert_not_called()
            run_solver.assert_not_called()
            urlopen.assert_not_called()

    def test_authorized_post_reaches_job_creation_only_after_explicit_request(self) -> None:
        payload = {
            "gateCapacityFractionById": [0, 1, 0, 1, 0, 1, 0, 1],
            "durationS": 5,
        }
        handler = make_handler(
            "/api/stage20/local/jobs",
            valid_post_headers(),
            payload,
        )
        accepted = {
            "schema": service.JOB_SCHEMA,
            "status": "QUEUED",
            "completed": False,
        }
        with patch.object(
            service.MANAGER,
            "create",
            return_value=accepted,
        ) as create_job, patch.object(service.subprocess, "run") as run_solver:
            with patch.object(
                service,
                "local_runtime_asset_readiness",
                return_value={"ready": True},
            ):
                handler.do_POST()
        create_job.assert_called_once_with(payload)
        run_solver.assert_not_called()
        self.assertEqual(handler.send_json.call_args.args[0], HTTPStatus.ACCEPTED)

    def test_capability_token_is_returned_only_for_safe_get_context(self) -> None:
        safe = make_handler(
            "/api/stage20/forcing/capabilities",
            {"Host": "localhost:4173"},
        )
        safe.do_GET()
        status, payload = safe.send_json.call_args.args
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["csrfHeaderName"], service.CSRF_HEADER_NAME)
        self.assertEqual(payload["csrfToken"], service.CSRF_TOKEN)
        self.assertGreaterEqual(len(payload["csrfToken"]), 32)
        self.assertEqual(payload["status"], "READY_OFFLINE")
        self.assertEqual(payload["availableTideSnapshotYears"], [2026])
        self.assertEqual(
            payload["availableRequestedDateRanges"],
            [{"start": "2026-01-02", "end": "2026-12-30"}],
        )
        self.assertEqual(payload["defaultRequestedDate"], "2026-02-15")

        unsafe = make_handler(
            "/api/stage20/forcing/capabilities",
            {
                "Host": "localhost:4173",
                "Origin": "https://attacker.example",
            },
        )
        unsafe.do_GET()
        self.assertEqual(
            unsafe.send_json.call_args.args[0],
            HTTPStatus.FORBIDDEN,
        )

    def test_static_dot_paths_are_not_served_even_when_encoded(self) -> None:
        for path in (
            "/.git/config",
            "/%2egit/config",
            "/%252egit/config",
            "/.venv-stage20/bin/python",
            "/stage20-hybrid-gui.html?cache=ambiguous",
            "/stage20-hybrid-gui%2ehtml",
            "//stage20-hybrid-gui.html",
        ):
            with self.subTest(path=path):
                handler = make_handler(path, {"Host": "127.0.0.1:4173"})
                handler.do_GET()
                self.assertEqual(
                    handler.send_json.call_args.args[0],
                    HTTPStatus.NOT_FOUND,
                )

    def test_runtime_static_allowlist_contains_only_reviewed_browser_inputs(self) -> None:
        allowed_cases = (
            "stage20-hybrid-gui.html",
            "stage20-hybrid-gui.css",
            "onga_stage20_gui.mjs",
            "onga_stage20_hybrid_worker.mjs",
            "config/stage20_runtime_capabilities_v2.json",
            "public/data/onga/stage20/mesh-v2.bin",
        )
        for relative in allowed_cases:
            with self.subTest(relative=relative):
                resolved = service.resolve_runtime_static_path(f"/{relative}")
                self.assertEqual(resolved, (ROOT / relative).resolve())

        excluded_registered_inputs = (
            "docs/results/stage20-barrage-candidate-C-R1C-next-stage-review-approval-v1/review-mesh.npz",
            "docs/results/stage20-barrage-candidate-C-R1C-D2-full-history-v1/R1C-full-history-checkpoints.npz",
            "docs/results/practical-wetdry-f59-v19-public-sidecar-20260825-v1/f59-public-37hour-response-pack.bin",
            "docs/results/fishing-decision-sidecar-20260825-v1/decision-sidecar.json",
        )
        for relative in excluded_registered_inputs:
            with self.subTest(excluded=relative):
                self.assertNotIn(relative, service.RUNTIME_STATIC_ALLOWLIST)
                self.assertIsNone(service.resolve_runtime_static_path(f"/{relative}"))

    def test_optional_gsi_tiles_require_canonical_bounded_jpeg_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            relative = "data/external/gsi/seamlessphoto/z18/226229-104811.jpg"
            tile = root / relative
            tile.parent.mkdir(parents=True)
            tile.write_bytes(b"local-test-jpeg")
            prefixes = frozenset({"data/external/gsi/seamlessphoto/"})
            self.assertEqual(
                service.resolve_runtime_static_path(
                    f"/{relative}",
                    root=root,
                    allowlist=frozenset(),
                    gsi_prefixes=prefixes,
                ),
                tile.resolve(),
            )
            for path in (
                "/data/external/gsi/seamlessphoto/README.md",
                "/data/external/gsi/seamlessphoto/z018/226229-104811.jpg",
                "/data/external/gsi/seamlessphoto/z18/0226229-104811.jpg",
                "/data/external/gsi/seamlessphoto/z25/226229-104811.jpg",
                "/data/external/gsi/seamlessphoto/z18/262144-104811.jpg",
                "/data/external/gsi/seamlessphoto/z18/226229-104811.png",
            ):
                with self.subTest(path=path):
                    self.assertIsNone(
                        service.resolve_runtime_static_path(
                            path,
                            root=root,
                            allowlist=frozenset(),
                            gsi_prefixes=prefixes,
                        )
                    )

    def test_missing_local_assets_block_capability_and_post_before_job_creation(
        self,
    ) -> None:
        blocked = {
            "ready": False,
            "requiredAssetIds": list(LOCAL_REQUIRED_ASSET_IDS),
            "missingAssetIds": ["r1c_initial_checkpoint"],
            "invalidAssetIds": [],
            "evaluatedAtProcessStart": True,
        }
        capability_handler = make_handler(
            "/api/stage20/local/capabilities",
            {"Host": "127.0.0.1:4173"},
        )
        with patch.object(service, "LOCAL_RUNTIME_ASSET_READINESS", blocked):
            capability_handler.do_GET()
        status, payload = capability_handler.send_json.call_args.args
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["status"], "BLOCKED_LOCAL_ASSETS_UNAVAILABLE")
        self.assertFalse(payload["classification"]["physicalSolverConnected"])
        self.assertEqual(payload["maximumConcurrentJobs"], 0)
        self.assertEqual(payload["assetReadiness"], blocked)

        post_handler = make_handler(
            "/api/stage20/local/jobs",
            valid_post_headers(),
            {
                "gateCapacityFractionById": [0] * 8,
                "durationS": 5,
            },
        )
        with patch.object(
            service,
            "local_runtime_asset_readiness",
            return_value=blocked,
        ), patch.object(service.MANAGER, "create") as create_job, patch.object(
            service.subprocess,
            "run",
        ) as run_solver:
            post_handler.do_POST()
        self.assertEqual(
            post_handler.send_json.call_args.args[0],
            HTTPStatus.CONFLICT,
        )
        create_job.assert_not_called()
        run_solver.assert_not_called()

    def test_ready_capability_means_preflight_available_not_solver_connected(
        self,
    ) -> None:
        ready = {
            "ready": True,
            "requiredAssetIds": list(LOCAL_REQUIRED_ASSET_IDS),
            "missingAssetIds": [],
            "invalidAssetIds": [],
            "evaluatedAtProcessStart": True,
        }
        handler = make_handler(
            "/api/stage20/local/capabilities",
            {"Host": "127.0.0.1:4173"},
        )
        with patch.object(service, "LOCAL_RUNTIME_ASSET_READINESS", ready):
            handler.do_GET()
        status, payload = handler.send_json.call_args.args
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["status"], "READY_FOR_EXPLICIT_LOCAL_RUN")
        self.assertEqual(payload["maximumConcurrentJobs"], 1)
        classification = payload["classification"]
        self.assertIs(classification["localRunnerAvailable"], True)
        self.assertIs(classification["runtimeInputsVerified"], True)
        self.assertIs(classification["solverExecutionPreflightPassed"], False)
        self.assertIs(classification["physicalSolverConnected"], False)

    def test_local_asset_readiness_covers_every_declared_solver_dependency(
        self,
    ) -> None:
        capabilities = json.loads(
            (ROOT / "config/stage20_runtime_capabilities_v2.json").read_text(
                encoding="utf-8"
            )
        )
        registry = json.loads(
            (ROOT / "config/stage20_runtime_assets_v2.json").read_text(
                encoding="utf-8"
            )
        )
        expected_ids = list(LOCAL_REQUIRED_ASSET_IDS)
        local_mode = next(
            mode
            for mode in capabilities["modes"]
            if mode["id"] == "local_r1c_experiment"
        )
        self.assertEqual(local_mode["requiredAssets"], expected_ids)

        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            asset_by_id = {asset["id"]: asset for asset in registry["assets"]}
            payload_by_id: dict[str, bytes] = {}
            for asset_id in expected_ids:
                asset = asset_by_id[asset_id]
                payload = f"readiness-fixture:{asset_id}\n".encode("utf-8")
                payload_by_id[asset_id] = payload
                asset["byteLength"] = len(payload)
                asset["sha256"] = hashlib.sha256(payload).hexdigest()
                destination = temporary_root / asset["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)

            config_root = temporary_root / "config"
            config_root.mkdir(parents=True, exist_ok=True)
            (config_root / "stage20_runtime_capabilities_v2.json").write_text(
                json.dumps(capabilities),
                encoding="utf-8",
            )
            (config_root / "stage20_runtime_assets_v2.json").write_text(
                json.dumps(registry),
                encoding="utf-8",
            )

            ready = service.local_runtime_asset_readiness(temporary_root)
            self.assertTrue(ready["ready"])
            self.assertEqual(ready["requiredAssetIds"], expected_ids)
            runner_expected = {
                asset_id: (
                    asset_by_id[asset_id]["path"],
                    asset_by_id[asset_id]["byteLength"],
                    asset_by_id[asset_id]["sha256"],
                )
                for asset_id in expected_ids
            }
            runner_bindings = local_runner.validate_runtime_asset_closure(
                temporary_root,
                runner_expected,
            )
            self.assertEqual(
                [binding["id"] for binding in runner_bindings],
                expected_ids,
            )

            for asset_id in expected_ids:
                asset_path = temporary_root / asset_by_id[asset_id]["path"]
                with self.subTest(asset_id=asset_id, failure="missing"):
                    asset_path.unlink()
                    missing = service.local_runtime_asset_readiness(temporary_root)
                    self.assertFalse(missing["ready"])
                    self.assertEqual(missing["missingAssetIds"], [asset_id])
                    self.assertEqual(missing["invalidAssetIds"], [])
                    with self.assertRaisesRegex(RuntimeError, "asset is absent"):
                        local_runner.validate_runtime_asset_closure(
                            temporary_root,
                            runner_expected,
                        )
                    asset_path.write_bytes(payload_by_id[asset_id])

                with self.subTest(asset_id=asset_id, failure="modified"):
                    asset_path.write_bytes(payload_by_id[asset_id] + b"modified")
                    invalid = service.local_runtime_asset_readiness(temporary_root)
                    self.assertFalse(invalid["ready"])
                    self.assertEqual(invalid["missingAssetIds"], [])
                    self.assertEqual(invalid["invalidAssetIds"], [asset_id])
                    with self.assertRaisesRegex(RuntimeError, "size changed"):
                        local_runner.validate_runtime_asset_closure(
                            temporary_root,
                            runner_expected,
                        )
                    asset_path.write_bytes(payload_by_id[asset_id])

            local_mode["requiredAssets"] = expected_ids[:-1]
            (config_root / "stage20_runtime_capabilities_v2.json").write_text(
                json.dumps(capabilities),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "dependency closure changed"):
                service.local_runtime_asset_readiness(temporary_root)
            with self.assertRaisesRegex(RuntimeError, "dependency closure changed"):
                local_runner.validate_runtime_asset_closure(
                    temporary_root,
                    runner_expected,
                )

    def test_unreviewed_files_directories_and_forbidden_prefixes_are_not_served(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "allowed.json").write_text("{}\n", encoding="utf-8")
            (root / "allowed.bin").write_bytes(b"\x00\x01")
            (root / "rogue.html").write_text("<script></script>", encoding="utf-8")
            (root / "rogue.mjs").write_text("export default 1;\n", encoding="utf-8")
            (root / "directory").mkdir()
            (root / "tools").mkdir()
            (root / "tools" / "leak.json").write_text("{}\n", encoding="utf-8")
            with (root / "arbitrary-large.bin").open("wb") as stream:
                stream.truncate(12 * 1024 * 1024)
            allowlist = frozenset(
                {
                    "allowed.json",
                    "allowed.bin",
                    "directory",
                    "tools/leak.json",
                }
            )
            for relative in ("allowed.json", "allowed.bin"):
                with self.subTest(allowed=relative):
                    self.assertEqual(
                        service.resolve_runtime_static_path(
                            f"/{relative}",
                            root=root,
                            allowlist=allowlist,
                            gsi_prefixes=frozenset(),
                        ),
                        (root / relative).resolve(),
                    )
            for relative in (
                "rogue.html",
                "rogue.mjs",
                "directory",
                "tools/leak.json",
                "arbitrary-large.bin",
            ):
                with self.subTest(blocked=relative):
                    self.assertIsNone(
                        service.resolve_runtime_static_path(
                            f"/{relative}",
                            root=root,
                            allowlist=allowlist,
                            gsi_prefixes=frozenset(),
                        )
                    )

    def test_static_resolution_rejects_final_and_parent_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "payload.bin").write_bytes(b"outside")
            (root / "final.bin").symlink_to(outside / "payload.bin")
            (root / "linked-parent").symlink_to(outside, target_is_directory=True)
            allowlist = frozenset(
                {
                    "final.bin",
                    "linked-parent/payload.bin",
                }
            )
            for relative in allowlist:
                with self.subTest(relative=relative):
                    self.assertIsNone(
                        service.resolve_runtime_static_path(
                            f"/{relative}",
                            root=root,
                            allowlist=allowlist,
                            gsi_prefixes=frozenset(),
                        )
                    )

    def test_get_and_head_do_not_fall_back_to_repository_server(self) -> None:
        for path in (
            "/",
            "/tools/serve_stage20_local_simulator_v1.py",
            "/config/d3_spinup_plus_regeneration_preflight_20260809_s2_contract_v1.json",
        ):
            with self.subTest(method="GET", path=path):
                handler = make_handler(path, {"Host": "127.0.0.1:4173"})
                handler.do_GET()
                self.assertEqual(
                    handler.send_json.call_args.args[0],
                    HTTPStatus.NOT_FOUND,
                )
            with self.subTest(method="HEAD", path=path):
                handler = make_handler(path, {"Host": "127.0.0.1:4173"})
                handler.do_HEAD()
                handler.send_response.assert_called_once_with(HTTPStatus.NOT_FOUND)
                self.assertEqual(handler.wfile.getvalue(), b"")

        allowed_head = make_handler(
            "/stage20-hybrid-gui.html",
            {"Host": "127.0.0.1:4173"},
        )
        allowed_head.do_HEAD()
        allowed_head.send_response.assert_called_once_with(HTTPStatus.OK)
        self.assertEqual(allowed_head.wfile.getvalue(), b"")

        api_head = make_handler(
            "/api/stage20/local/capabilities",
            {"Host": "127.0.0.1:4173"},
        )
        api_head.do_HEAD()
        api_head.send_response.assert_called_once_with(HTTPStatus.METHOD_NOT_ALLOWED)

    def test_response_headers_block_framing_and_cross_origin_resources(self) -> None:
        handler = object.__new__(service.Stage20Handler)
        handler.send_header = Mock()
        with patch.object(service.BaseHTTPRequestHandler, "end_headers"):
            service.Stage20Handler.end_headers(handler)
        headers = dict(call.args for call in handler.send_header.call_args_list)
        self.assertEqual(headers["Content-Security-Policy"], "frame-ancestors 'none'")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")


if __name__ == "__main__":
    unittest.main()
