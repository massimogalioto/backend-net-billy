"""Power eligibility rules are independent from comparison cost formulas."""
import unittest

from database_service import is_power_eligible


class PowerEligibilityTests(unittest.TestCase):
    def test_minimum_power_excludes_lower_customer(self):
        self.assertFalse(is_power_eligible(8, 25, None))

    def test_minimum_power_includes_boundary(self):
        self.assertTrue(is_power_eligible(25, 25, None))

    def test_maximum_power_includes_boundary(self):
        self.assertTrue(is_power_eligible(15, None, 15))

    def test_maximum_power_excludes_higher_customer(self):
        self.assertFalse(is_power_eligible(16, None, 15))

    def test_range_includes_customer_inside(self):
        self.assertTrue(is_power_eligible(20, 10, 30))

    def test_range_excludes_customer_outside(self):
        self.assertFalse(is_power_eligible(35, 10, 30))

    def test_unrestricted_offer_is_always_eligible(self):
        self.assertTrue(is_power_eligible(8, None, None))

    def test_missing_customer_power_skips_filter(self):
        self.assertTrue(is_power_eligible(None, 25, 30))


if __name__ == "__main__":
    unittest.main()
