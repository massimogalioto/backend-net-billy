import unittest
from decimal import Decimal

from commission_service import validate_bands


class CommissionBandValidationTests(unittest.TestCase):
    def test_valid_bands_are_sorted_and_exact(self):
        result = validate_bands([
            {"min_contracts": 11, "max_contracts": None, "base_amount": "65.20", "sepa_bonus": "10"},
            {"min_contracts": 0, "max_contracts": 10, "base_amount": "60", "sepa_bonus": "5.50"},
        ])
        self.assertEqual([band["min_contracts"] for band in result], [0, 11])
        self.assertEqual(result[0]["base_amount"], Decimal("60"))

    def test_overlapping_bands_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "sovrapporsi"):
            validate_bands([
                {"min_contracts": 0, "max_contracts": 10, "base_amount": 1, "sepa_bonus": 0},
                {"min_contracts": 10, "max_contracts": 20, "base_amount": 1, "sepa_bonus": 0},
            ])

    def test_duplicate_band_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_bands([
                {"min_contracts": 0, "max_contracts": 10, "base_amount": 1, "sepa_bonus": 0},
                {"min_contracts": 0, "max_contracts": 10, "base_amount": 2, "sepa_bonus": 0},
            ])

    def test_negative_amount_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "negativi"):
            validate_bands([{"min_contracts": 0, "max_contracts": None,
                             "base_amount": -1, "sepa_bonus": 0}])

    def test_unbounded_band_must_be_last(self):
        with self.assertRaisesRegex(ValueError, "ultima"):
            validate_bands([
                {"min_contracts": 0, "max_contracts": None, "base_amount": 1, "sepa_bonus": 0},
                {"min_contracts": 20, "max_contracts": 30, "base_amount": 1, "sepa_bonus": 0},
            ])


if __name__ == "__main__":
    unittest.main()
