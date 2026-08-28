from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tools/stage20_barrage_one_way_face_flux_operator_v1.py"
SPEC = importlib.util.spec_from_file_location("stage20_barrage_one_way_face_flux_operator_v1", PATH)
assert SPEC is not None and SPEC.loader is not None
OPERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPERATOR)


class Stage20BarrageOneWayFaceFluxOperatorV1Tests(unittest.TestCase):
    def resolve(self, mass: float, multiplier: float = 1.0, upstream_is_left: bool = True):
        return OPERATOR.resolve_one_way_face_terms(
            open_left_term=[mass, 4.0, -2.0],
            open_right_term=[-mass, -3.0, 1.5],
            wall_left_term=[0.0, 6.0, -1.0],
            wall_right_term=[0.0, -5.0, 2.0],
            opening_multiplier=multiplier,
            upstream_is_left=upstream_is_left,
        )

    def test_contract_is_pure_and_not_connected(self) -> None:
        contract = OPERATOR.verified_contract()
        self.assertTrue(contract["decisionBoundary"]["pureOperatorAndSyntheticTestsPermitted"])
        self.assertFalse(contract["decisionBoundary"]["kernelConnectionPermitted"])
        self.assertFalse(contract["decisionBoundary"]["durationRunPermitted"])
        self.assertFalse(contract["decisionBoundary"]["yodaLaunchPermitted"])

    def test_outward_flux_is_blended_and_mass_conservative(self) -> None:
        result = self.resolve(2.0, multiplier=0.5)
        self.assertEqual(result["branch"], "OPEN_OUTWARD_BLEND")
        self.assertEqual(result["resolvedOutwardMassTerm"], 1.0)
        self.assertEqual(result["massResidual"], 0.0)
        self.assertEqual(result["leftTerm"], [1.0, 5.0, -1.5])
        self.assertEqual(result["rightTerm"], [-1.0, -4.0, 1.75])

    def test_adverse_flux_uses_walls_without_mass_transfer(self) -> None:
        result = self.resolve(-2.0, multiplier=1.0)
        self.assertEqual(result["branch"], "WALL_BLOCKED_REVERSE")
        self.assertEqual(result["resolvedOutwardMassTerm"], 0.0)
        self.assertEqual(result["massResidual"], 0.0)
        self.assertEqual(result["structureMomentumReactionXY"], [1.0, 1.0])

    def test_orientation_is_applied_from_upstream_side(self) -> None:
        result = self.resolve(2.0, multiplier=1.0, upstream_is_left=False)
        self.assertEqual(result["rawOutwardMassTerm"], -2.0)
        self.assertEqual(result["branch"], "WALL_BLOCKED_REVERSE")

    def test_closed_face_is_wall_even_for_outward_raw_flux(self) -> None:
        result = self.resolve(2.0, multiplier=0.0)
        self.assertEqual(result["branch"], "WALL_CLOSED")
        self.assertEqual(result["resolvedOutwardMassTerm"], 0.0)

    def test_nonconservative_open_terms_fail_closed(self) -> None:
        with self.assertRaises(OPERATOR.OneWayFaceFluxError):
            OPERATOR.resolve_one_way_face_terms(
                open_left_term=[1.0, 0.0, 0.0],
                open_right_term=[-0.9, 0.0, 0.0],
                wall_left_term=[0.0, 0.0, 0.0],
                wall_right_term=[0.0, 0.0, 0.0],
                opening_multiplier=1.0,
                upstream_is_left=True,
            )

    def test_wall_mass_leakage_fails_closed(self) -> None:
        with self.assertRaises(OPERATOR.OneWayFaceFluxError):
            OPERATOR.resolve_one_way_face_terms(
                open_left_term=[1.0, 0.0, 0.0],
                open_right_term=[-1.0, 0.0, 0.0],
                wall_left_term=[1.0e-6, 0.0, 0.0],
                wall_right_term=[0.0, 0.0, 0.0],
                opening_multiplier=1.0,
                upstream_is_left=True,
            )


if __name__ == "__main__":
    unittest.main()
