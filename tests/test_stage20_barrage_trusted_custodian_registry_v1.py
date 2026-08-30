from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_trusted_custodian_registry_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_trusted_custodian_registry_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
REGISTRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REGISTRY)


class Stage20BarrageTrustedCustodianRegistryV1Tests(unittest.TestCase):
    def test_empty_template_is_valid_but_not_ready(self) -> None:
        contract = REGISTRY.verified_contract()
        result = REGISTRY.assess(contract["template"], contract)
        self.assertTrue(result["schemaPass"])
        self.assertEqual(result["trustedCustodianCount"], 0)
        self.assertFalse(result["registryReady"])
        self.assertFalse(result["physicalSourceAuthenticationPermitted"])

    def test_invented_candidate_cannot_activate_registry(self) -> None:
        contract = REGISTRY.verified_contract()
        candidate = {
            "schema": contract["registrySchema"],
            "classification": "candidate_untrusted",
            "entries": [{"custodianId": "invented"}],
            "revocations": [],
            "externalSignatureVerifier": None,
        }
        result = REGISTRY.assess(candidate, contract)
        self.assertIn("CANDIDATE_ENTRIES_REQUIRE_EXTERNAL_REVIEW", result["issues"])
        self.assertIn("ENTRY_0_REQUIRED_FIELDS_MISSING", result["issues"])
        self.assertEqual(result["trustedCustodianCount"], 0)
        self.assertFalse(result["registryReady"])

    def test_external_verifier_cannot_be_self_enabled(self) -> None:
        contract = REGISTRY.verified_contract()
        candidate = dict(contract["template"])
        candidate["externalSignatureVerifier"] = {"name": "unreviewed"}
        result = REGISTRY.assess(candidate, contract)
        self.assertIn("EXTERNAL_SIGNATURE_VERIFIER_NOT_AUTHORIZED", result["issues"])
        self.assertFalse(result["solverRunPermitted"])
        self.assertFalse(result["releasePermitted"])

    def test_contract_requires_two_independent_reviewers(self) -> None:
        contract = REGISTRY.verified_contract()
        requirements = contract["activationRequirements"]
        self.assertEqual(requirements["minimumIndependentReviewers"], 2)
        self.assertTrue(requirements["selfRegistrationForbidden"])
        self.assertTrue(requirements["externalSignatureVerificationReceiptRequired"])


if __name__ == "__main__":
    unittest.main()
