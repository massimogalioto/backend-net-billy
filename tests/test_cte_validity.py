import unittest

from cte_validity import normalize_cte_validity


class CteValidityTests(unittest.TestCase):
    def test_single_offer_expiry_is_not_an_start_date(self):
        self.assertEqual(
            normalize_cte_validity({"validita": "2026-10-31"}),
            {"valid_from": None, "valid_until": "2026-10-31"},
        )

    def test_generic_validity_date_is_expiry(self):
        self.assertEqual(
            normalize_cte_validity({"validita": "2026-11-15"}),
            {"valid_from": None, "valid_until": "2026-11-15"},
        )

    def test_explicit_commercial_range_is_preserved(self):
        self.assertEqual(
            normalize_cte_validity({"valid_from": "2026-10-01", "valid_until": "2026-10-31"}),
            {"valid_from": "2026-10-01", "valid_until": "2026-10-31"},
        )

    def test_document_date_does_not_become_start_date(self):
        self.assertEqual(
            normalize_cte_validity({"document_date": "2026-10-07", "validita": "2026-10-31"}),
            {"document_date": "2026-10-07", "valid_from": None, "valid_until": "2026-10-31"},
        )


if __name__ == "__main__":
    unittest.main()
