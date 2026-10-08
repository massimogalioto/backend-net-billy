import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import plan_service


class PlanLimitTests(unittest.TestCase):
    def test_expired_cte_does_not_consume_an_active_slot(self):
        self.assertFalse(plan_service._offer_is_active(date(2020, 1, 1)))
        self.assertTrue(plan_service._offer_is_active(None))

    def test_active_cte_count_is_tenant_scoped_and_excludes_expired(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"count": 15}
        self.assertEqual(plan_service._count_active_cte(cursor, "tenant-a"), 15)
        sql, params = cursor.execute.call_args.args
        self.assertEqual(params, ("tenant-a",))
        self.assertIn("valid_until IS NULL OR valid_until >= CURRENT_DATE", sql)

    def test_limit_error_has_the_public_structured_payload(self):
        plan = plan_service.PlanLimits("FREE", "Free", 2, 4, "active")
        error = plan_service.UsageLimitError("cte", plan, 2, 2)
        self.assertEqual(error.payload(), {
            "code": "cte_limit_reached", "message": str(error),
            "used": 2, "limit": 2, "plan": "FREE",
        })

    def test_active_cte_limit_blocks_when_usage_reaches_plan_limit(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        plan = plan_service.PlanLimits("START", "Start", 20, 120, "active")
        with patch.object(plan_service, "_active_plan", return_value=plan), patch.object(
            plan_service, "_count_active_cte", return_value=20
        ):
            with self.assertRaises(plan_service.UsageLimitError) as raised:
                plan_service.ensure_active_cte_capacity("tenant-a", None, conn=connection)
        self.assertEqual(raised.exception.payload()["code"], "cte_limit_reached")

    def test_cte_capacity_allows_zero_and_nineteen_but_not_twenty(self):
        plan = plan_service.PlanLimits("START", "Start", 20, 120, "active")
        for used in (0, 19):
            connection = MagicMock()
            with patch.object(plan_service, "_active_plan", return_value=plan), patch.object(
                plan_service, "_count_active_cte", return_value=used
            ):
                plan_service.ensure_active_cte_capacity("tenant-a", None, conn=connection)

    def test_free_plan_blocks_the_third_active_cte(self):
        connection = MagicMock()
        plan = plan_service.PlanLimits("FREE", "Free", 2, 4, "active")
        with patch.object(plan_service, "_active_plan", return_value=plan), patch.object(
            plan_service, "_count_active_cte", return_value=2
        ), self.assertRaises(plan_service.UsageLimitError):
            plan_service.ensure_active_cte_capacity("tenant-a", None, conn=connection)

    def test_monthly_count_is_tenant_scoped(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"count": 119}
        self.assertEqual(plan_service._count_monthly_comparisons(cursor, "tenant-a"), 119)
        sql, params = cursor.execute.call_args.args
        self.assertEqual(params, ("tenant-a",))
        self.assertIn("Europe/Rome", sql)

    def test_comparison_slot_allows_119_and_records_only_on_success(self):
        connection = MagicMock()
        plan = plan_service.PlanLimits("START", "Start", 20, 120, "active")
        with patch.object(plan_service, "_connection", return_value=connection), patch.object(
            plan_service, "_active_plan", return_value=plan
        ), patch.object(plan_service, "_count_monthly_comparisons", return_value=119):
            with plan_service.comparison_slot("tenant-a", "user-a") as slot:
                slot.record_success("Luce")
        self.assertTrue(connection.cursor.return_value.__enter__.return_value.execute.called)
        self.assertTrue(connection.commit.called)

    def test_comparison_slot_blocks_at_monthly_limit(self):
        connection = MagicMock()
        plan = plan_service.PlanLimits("START", "Start", 20, 120, "active")
        with patch.object(plan_service, "_connection", return_value=connection), patch.object(
            plan_service, "_active_plan", return_value=plan
        ), patch.object(plan_service, "_count_monthly_comparisons", return_value=120), self.assertRaises(
            plan_service.UsageLimitError
        ) as raised:
            with plan_service.comparison_slot("tenant-a", "user-a"):
                pass
        self.assertEqual(raised.exception.payload()["code"], "comparison_limit_reached")


if __name__ == "__main__":
    unittest.main()
