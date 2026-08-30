from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_external_verifier_activation_requirements_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_external_verifier_activation_requirements_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
ACTIVATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACTIVATION)


class Stage20BarrageExternalVerifierActivationRequirementsV1Tests(unittest.TestCase):
    def test_empty_template_fails_closed(self) -> None:
        contract = ACTIVATION.verified_contract()
        result = ACTIVATION.assess(contract["template"], contract)
        self.assertFalse(result["requirementsPass"])
        self.assertFalse(result["activationReady"])
        self.assertIn("VERIFIER_IDENTITY_MISSING", result["issues"])
        self.assertIn("INDEPENDENT_REVIEW_INSUFFICIENT", result["issues"])
        self.assertIn("REQUIRED_NEGATIVE_OR_VECTOR_TESTS_MISSING", result["issues"])

    def test_required_negative_tests_cover_substitution_and_revocation(self) -> None:
        contract = ACTIVATION.verified_contract()
        required = set(contract["requiredTests"])
        self.assertIn("tampered_payload_fails", required)
        self.assertIn("wrong_public_key_fails", required)
        self.assertIn("expired_key_fails", required)
        self.assertIn("revoked_key_fails", required)
        self.assertIn("wrong_data_scope_fails", required)
        self.assertIn("registry_sha_mismatch_fails", required)

    def test_single_reviewer_cannot_activate(self) -> None:
        contract = ACTIVATION.verified_contract()
        candidate = dict(contract["template"])
        candidate["classification"] = "candidate_untrusted"
        candidate["reviewEvidence"] = [{"reviewerId": "one-reviewer"}]
        result = ACTIVATION.assess(candidate, contract)
        self.assertIn("INDEPENDENT_REVIEW_INSUFFICIENT", result["issues"])
        self.assertFalse(result["verifierExecutionPermitted"])

    def test_contract_grants_no_execution_or_release_authority(self) -> None:
        contract = ACTIVATION.verified_contract()
        boundary = contract["decisionBoundary"]
        self.assertFalse(boundary["activationPresent"])
        self.assertFalse(boundary["verifierExecutionPermitted"])
        self.assertFalse(boundary["solverRunPermitted"])
        self.assertFalse(boundary["yodaLaunchPermitted"])
        self.assertFalse(boundary["releasePermitted"])


if __name__ == "__main__":
    unittest.main()
