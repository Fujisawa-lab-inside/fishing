from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "tools/validate_stage20_runtime_baseline_v2.py"
SPEC = importlib.util.spec_from_file_location(
    "validate_stage20_runtime_baseline_v2",
    VALIDATOR_PATH,
)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def runtime_inputs():
    manifest = validator.read_json(validator.DEFAULT_MANIFEST)
    assets = validator.read_json(ROOT / manifest["assetRegistryPath"])
    asset_by_path = {asset["path"]: asset for asset in assets["assets"]}
    closure = manifest["importClosure"]
    imports = validator.javascript_closure(
        closure["javascriptEntrypoints"],
        closure["javascriptExtensions"],
    ) | validator.python_closure(
        closure["pythonEntrypoints"],
        closure["pythonModuleRoots"],
    )
    return manifest, assets, asset_by_path, imports


class RuntimeBaselineV2Test(unittest.TestCase):
    def test_approved_fishway_candidate_keeps_exact_inert_path_exemption(
        self,
    ) -> None:
        manifest = validator.read_json(validator.DEFAULT_MANIFEST)
        candidate_path = (
            ROOT
            / "config/stage20_fishway_constant_weak_flow_coupling_candidate_v1.json"
        )
        candidate = validator.read_json(candidate_path)
        self.assertEqual(candidate_path.stat().st_size, 60680)
        self.assertEqual(
            validator.sha256(candidate_path),
            "7afe958520537b4f0ca2c1bf493160919b85a897cabb63639b83b07104be5313",
        )
        exemption = manifest["absolutePathPolicy"]["jsonValueExemptions"]
        self.assertEqual(len(exemption), 1)
        self.assertEqual(
            exemption[0]["path"],
            candidate_path.relative_to(ROOT).as_posix(),
        )
        self.assertEqual(
            exemption[0]["jsonPointer"],
            "/judgmentVisual/inlinePath",
        )
        user_prefix = "/" + "Users/"
        self.assertEqual(exemption[0]["forbiddenPrefix"], user_prefix)
        self.assertEqual(
            exemption[0]["valueSha256"],
            "d5970922e07ddeba3a9db77b28aeeaf59b35cc213176f8699820c5a4a4bacc4a",
        )
        self.assertIs(exemption[0]["runtimeConsumed"], False)
        values = dict(validator.json_string_values(candidate))
        self.assertEqual(
            values[exemption[0]["jsonPointer"]],
            candidate["judgmentVisual"]["inlinePath"],
        )

    def test_dynamic_inventory_classifies_the_current_fetch_closure(self) -> None:
        manifest, assets, asset_by_path, imports = runtime_inputs()
        report = validator.validate_dynamic_browser_runtime(
            manifest,
            assets,
            asset_by_path,
            validator.git_paths(),
            imports,
            False,
        )
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["requiredPathCount"], 31)
        self.assertEqual(report["bindingManifestCount"], 3)
        self.assertEqual(report["localLiteralCount"], 35)
        self.assertEqual(report["apiLiteralCount"], 5)
        self.assertEqual(report["templateLiteralCount"], 10)
        self.assertEqual(report["optionalExternalAssetCount"], 4)
        self.assertEqual(report["optionalRuntimeCollectionCount"], 1)
        self.assertEqual(report["runtimeGeneratedUrlCount"], 2)

    def test_release_mode_rejects_an_untracked_dynamic_dependency(self) -> None:
        manifest, assets, asset_by_path, imports = runtime_inputs()
        tracked = validator.git_paths()
        required = "public/data/onga/stage20/mesh-v2.json"
        self.assertIn(required, tracked)
        tracked.remove(required)
        report = validator.validate_dynamic_browser_runtime(
            manifest,
            assets,
            asset_by_path,
            tracked,
            imports,
            True,
        )
        self.assertIn(
            f"E_UNTRACKED_DYNAMIC_REQUIRED: {required}",
            report["errors"],
        )

    def test_runtime_literal_scan_covers_lazy_and_generated_paths(self) -> None:
        _, _, _, imports = runtime_inputs()
        literals = validator.javascript_runtime_literals(imports)
        self.assertIn(
            "docs/results/stage20-R1C-browser-replay-candidate-v1/replay-fields.bin",
            literals["local"],
        )
        self.assertIn(
            "docs/results/stage20-reference-v2-browser-sidecar-20260730-s8a1-v1/",
            literals["local"],
        )
        self.assertIn(
            "data/external/gsi/seamlessphoto/z",
            literals["local"],
        )
        self.assertIn("/api/stage20/local/jobs/${jobId}", literals["api"])
        self.assertIn("./${binding.path}", literals["templates"])

    def test_source_only_uri_policy_does_not_require_scanning_docs(self) -> None:
        user_prefix = "/" + "Users/"
        home_prefix = "/" + "home/"
        temporary_prefix = "/" + "tmp/"
        file_uri_prefix = "file" + "://"
        prefixes = [user_prefix, home_prefix, temporary_prefix, file_uri_prefix]
        hits = validator.forbidden_prefix_hits(
            f"const source = '{file_uri_prefix}{user_prefix}example/runtime.json';",
            prefixes,
        )
        self.assertEqual(hits, [user_prefix, file_uri_prefix])

    def test_optional_runtime_collection_may_be_absent_in_clean_checkout(self) -> None:
        manifest, assets, asset_by_path, imports = runtime_inputs()
        optional_prefix = (ROOT / "data/external/gsi/seamlessphoto").resolve()
        path_exists = Path.exists

        def exists_except_optional_prefix(path: Path) -> bool:
            if path == optional_prefix:
                return False
            return path_exists(path)

        with mock.patch.object(Path, "exists", new=exists_except_optional_prefix):
            report = validator.validate_dynamic_browser_runtime(
                manifest,
                assets,
                asset_by_path,
                validator.git_paths(),
                imports,
                False,
            )

        self.assertEqual(report["errors"], [])
        self.assertEqual(report["optionalRuntimeCollectionCount"], 1)

    def test_external_runtime_assets_are_ignored_from_normal_git_add(self) -> None:
        _, assets, _, _ = runtime_inputs()
        external = [
            asset
            for asset in assets["assets"]
            if asset["trackingPolicy"] == "must_not_be_added_to_normal_git"
        ]
        self.assertGreater(len(external), 0)
        for asset in external:
            with self.subTest(asset=asset["id"]):
                self.assertTrue(validator.git_path_is_ignored(asset["path"]))


if __name__ == "__main__":
    unittest.main()
