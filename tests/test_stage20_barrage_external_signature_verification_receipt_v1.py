from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_external_signature_verification_receipt_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_external_signature_verification_receipt_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
RECEIPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECEIPT)


def self_declared_candidate(contract):
    return {
        "schema": contract["receiptSchema"],
        "classification": "candidate_untrusted",
        "registrySha256": "1" * 64,
        "custodianId": "self-declared",
        "custodianKeyFingerprintSha256": "2" * 64,
        "sourceManifestSha256": "3" * 64,
        "sourceApprovalSha256": "4" * 64,
        "signedPayloadSha256": "5" * 64,
        "detachedSignatureSha256": "6" * 64,
        "algorithm": "Ed25519",
        "verifierIdentity": "self-declared-verifier",
        "verifierExecutableSha256": "7" * 64,
        "verifiedAt": "2026-08-30T14:00:00+09:00",
        "result": "PASS_SIGNATURE_VALID",
    }


class Stage20BarrageExternalSignatureVerificationReceiptV1Tests(unittest.TestCase):
    def test_empty_template_fails_closed(self) -> None:
        contract = RECEIPT.verified_contract()
        result = RECEIPT.assess(contract["template"], contract)
        self.assertFalse(result["receiptSchemaPass"])
        self.assertFalse(result["cryptographicallyVerified"])
        self.assertIn("TRUSTED_REGISTRY_MISSING", result["issues"])
        self.assertIn("EXTERNAL_VERIFIER_MISSING", result["issues"])

    def test_self_declared_pass_receipt_is_not_trusted(self) -> None:
        contract = RECEIPT.verified_contract()
        result = RECEIPT.assess(self_declared_candidate(contract), contract)
        self.assertTrue(result["receiptSchemaPass"])
        self.assertIn("CANDIDATE_RECEIPT_NOT_TRUSTED", result["issues"])
        self.assertFalse(result["cryptographicallyVerified"])
        self.assertFalse(result["physicalSourceAuthenticated"])

    def test_wrong_algorithm_is_rejected(self) -> None:
        contract = RECEIPT.verified_contract()
        candidate = self_declared_candidate(contract)
        candidate["algorithm"] = "unreviewed-algorithm"
        result = RECEIPT.assess(candidate, contract)
        self.assertIn("SIGNATURE_ALGORITHM_INVALID", result["issues"])
        self.assertFalse(result["receiptSchemaPass"])

    def test_contract_grants_no_execution_or_release_authority(self) -> None:
        contract = RECEIPT.verified_contract()
        boundary = contract["decisionBoundary"]
        self.assertFalse(boundary["cryptographicVerificationPermitted"])
        self.assertFalse(boundary["physicalSourceAuthenticationPermitted"])
        self.assertFalse(boundary["solverRunPermitted"])
        self.assertFalse(boundary["yodaLaunchPermitted"])
        self.assertFalse(boundary["releasePermitted"])


if __name__ == "__main__":
    unittest.main()
