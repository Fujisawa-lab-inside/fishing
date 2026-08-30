from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_physical_source_provenance_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_physical_source_provenance_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
PROVENANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVENANCE)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Stage20BarragePhysicalSourceProvenanceV1Tests(unittest.TestCase):
    def test_empty_input_fails_closed(self) -> None:
        result = PROVENANCE.assess({})
        self.assertFalse(result["staticChainPass"])
        self.assertFalse(result["physicalSourceAuthenticated"])
        self.assertIn("TRUSTED_CUSTODIAN_REGISTRY_MISSING", result["issues"])

    def test_well_formed_self_attested_chain_is_not_authenticated(self) -> None:
        contract = PROVENANCE.verified_contract()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            manifest = {
                "schema": contract["sourceManifestSchema"],
                "sourceClass": "instrument_export",
                "instrumentIds": ["fixture-instrument"],
                "units": contract["requiredUnits"],
                "sourceFiles": [{"path": "fixture.csv", "sha256": "1" * 64}],
            }
            manifest_path = base / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            approval = {
                "schema": contract["approvalSchema"],
                "sourceManifestSha256": digest(manifest_path),
                "decision": "APPROVED_PHYSICAL_SOURCE",
                "custodianId": "self-attested-fixture-custodian",
            }
            approval_path = base / "approval.json"
            approval_path.write_text(json.dumps(approval))
            dataset = {
                "sourceManifestPath": "manifest.json",
                "sourceManifestSha256": digest(manifest_path),
                "sourceApprovalPath": "approval.json",
                "sourceApprovalSha256": digest(approval_path),
            }
            result = PROVENANCE.assess(dataset, base, contract)
        self.assertTrue(result["staticChainPass"])
        self.assertFalse(result["physicalSourceAuthenticated"])
        self.assertEqual(result["issues"], ["TRUSTED_CUSTODIAN_REGISTRY_MISSING"])

    def test_manifest_sha_mismatch_fails_static_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / "manifest.json").write_text("{}")
            result = PROVENANCE.assess(
                {
                    "sourceManifestPath": "manifest.json",
                    "sourceManifestSha256": "0" * 64,
                    "sourceApprovalPath": "missing.json",
                    "sourceApprovalSha256": "0" * 64,
                },
                base,
            )
        self.assertFalse(result["staticChainPass"])
        self.assertIn("SOURCE_MANIFEST_SHA_MISMATCH", result["issues"])
        self.assertFalse(result["solverRunPermitted"])

    def test_contract_grants_no_execution_authority(self) -> None:
        contract = PROVENANCE.verified_contract()
        boundary = contract["decisionBoundary"]
        self.assertFalse(boundary["physicalSourceAuthenticationPermitted"])
        self.assertFalse(boundary["parameterFitPermitted"])
        self.assertFalse(boundary["solverRunPermitted"])
        self.assertFalse(boundary["yodaLaunchPermitted"])
        self.assertFalse(boundary["releasePermitted"])


if __name__ == "__main__":
    unittest.main()
