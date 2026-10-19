import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import billing_endpoint
import billing_service
from auth_service import CurrentUser


USER = CurrentUser("user-a", "owner@example.com", "Owner", "tenant-a", "Tenant A", "FREE", "Free")
ORIGIN = "https://app.example.test"


class BillingEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(billing_endpoint.router)
        self.client = TestClient(self.app)
        self.env = patch.dict("os.environ", {
            "NET_BILLY_FRONTEND_URL": ORIGIN,
            "AUTH_ALLOWED_ORIGINS": ORIGIN,
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def authenticate(self):
        self.app.dependency_overrides[billing_endpoint.current_user] = lambda: USER

    def test_checkout_requires_authentication(self):
        response = self.client.post("/billing/checkout", json={"plan": "START"},
                                    headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 401)

    def test_checkout_start_and_top_use_session_tenant(self):
        self.authenticate()
        for plan in ("START", "TOP"):
            with self.subTest(plan=plan), patch.object(
                billing_endpoint, "create_checkout",
                return_value={"checkout_url": "https://checkout.stripe.test/session"},
            ) as create:
                response = self.client.post("/billing/checkout", json={"plan": plan},
                                            headers={"Origin": ORIGIN})
                self.assertEqual(response.status_code, 200)
                create.assert_called_once_with(USER.tenant_id, USER.email, USER.tenant_name, plan)

    def test_checkout_rejects_cross_site_origin(self):
        self.authenticate()
        response = self.client.post("/billing/checkout", json={"plan": "START"},
                                    headers={"Origin": "https://evil.example"})
        self.assertEqual(response.status_code, 403)

    def test_duplicate_subscription_is_conflict(self):
        self.authenticate()
        with patch.object(billing_endpoint, "create_checkout",
                          side_effect=billing_service.BillingError("duplicato", 409)):
            response = self.client.post("/billing/checkout", json={"plan": "START"},
                                        headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 409)

    def test_webhook_valid_and_duplicate(self):
        event = {"id": "evt_1", "type": "invoice.paid", "data": {"object": {}}}
        with patch.object(billing_endpoint, "construct_event", return_value=event), patch.object(
            billing_endpoint, "process_event", side_effect=[True, False]
        ):
            first = self.client.post("/billing/webhook", content=b"raw",
                                     headers={"Stripe-Signature": "valid"})
            duplicate = self.client.post("/billing/webhook", content=b"raw",
                                         headers={"Stripe-Signature": "valid"})
        self.assertEqual(first.json(), {"received": True, "duplicate": False})
        self.assertEqual(duplicate.json(), {"received": True, "duplicate": True})

    def test_webhook_invalid_signature(self):
        with patch.object(billing_endpoint, "construct_event",
                          side_effect=billing_service.BillingError("Firma webhook non valida", 400)):
            response = self.client.post("/billing/webhook", content=b"raw",
                                        headers={"Stripe-Signature": "invalid"})
        self.assertEqual(response.status_code, 400)


class BillingWebhookServiceTests(unittest.TestCase):
    def settings(self):
        return {
            "secret_key": "not-a-real-key", "webhook_secret": "whsec_mock",
            "frontend_url": ORIGIN, "prices": {"START": "price_start", "TOP": "price_top"},
            "mode": "test", "grace_days": 7,
        }

    def connection(self, fetchone_values):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = fetchone_values

        @contextmanager
        def factory():
            yield conn

        return factory, cursor

    def subscription(self, status="active"):
        now = int(datetime.now(timezone.utc).timestamp())
        return {
            "id": "sub_1", "customer": "cus_1", "status": status,
            "current_period_start": now, "current_period_end": now + 2592000,
            "cancel_at_period_end": False,
            "items": {"data": [{"price": {"id": "price_start"}}]},
        }

    def test_as_dict_uses_stripe_to_dict_without_iterating_resource(self):
        class StripeCustomerResponse:
            def to_dict(self):
                return {"id": "cus_1", "object": "customer"}

            def __iter__(self):
                raise TypeError("Customer is not iterable or a mapping; call .to_dict() for a plain dict.")

        self.assertEqual(
            billing_service._as_dict(StripeCustomerResponse()),
            {"id": "cus_1", "object": "customer"},
        )
        plain = {"id": "cus_plain"}
        self.assertIs(billing_service._as_dict(plain), plain)

    def test_upsert_tracks_classic_flexible_and_revoked_cancellations(self):
        cases = (
            ({"cancel_at_period_end": True, "cancel_at": None}, True),
            ({"cancel_at_period_end": False, "cancel_at": 1794528000}, True),
            ({"cancel_at_period_end": False, "cancel_at": None}, False),
        )
        for cancellation_fields, expected in cases:
            with self.subTest(fields=cancellation_fields):
                cursor = MagicMock()
                subscription = {**self.subscription(), **cancellation_fields}
                billing_service._upsert_subscription(cursor, "tenant-a", subscription, "START")
                params = cursor.execute.call_args.args[1]
                self.assertIs(params[6], expected)

    def test_checkout_uses_server_side_price_for_start_and_top(self):
        for plan, expected_price in (("START", "price_start"), ("TOP", "price_top")):
            with self.subTest(plan=plan):
                factory, _ = self.connection([None, None, {"stripe_customer_id": "cus_1"}])
                client = MagicMock()
                client.v1.checkout.sessions.create.return_value = {
                    "id": f"cs_{plan.lower()}", "url": "https://checkout.stripe.test/session",
                    "expires_at": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                }
                with patch.object(billing_service, "_settings", return_value=self.settings()), patch.object(
                    billing_service, "_connection", factory
                ):
                    result = billing_service.create_checkout(
                        "tenant-a", "owner@example.com", "Tenant A", plan, client=client
                    )
                params = client.v1.checkout.sessions.create.call_args.args[0]
                self.assertEqual(params["line_items"], [{"price": expected_price, "quantity": 1}])
                self.assertEqual(params["customer"], "cus_1")
                self.assertEqual(params["automatic_tax"], {"enabled": True})
                self.assertEqual(params["billing_address_collection"], "required")
                self.assertEqual(params["customer_update"], {"address": "auto"})
                self.assertEqual(params["tax_id_collection"], {"enabled": True})
                self.assertEqual(result["checkout_url"], "https://checkout.stripe.test/session")

    def test_checkout_reuses_only_sessions_created_with_tax_configuration(self):
        factory, cursor = self.connection([None, None, {"stripe_customer_id": "cus_1"}])
        client = MagicMock()
        client.v1.checkout.sessions.create.return_value = {
            "id": "cs_tax", "url": "https://checkout.stripe.test/tax-session",
            "expires_at": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        with patch.object(billing_service, "_settings", return_value=self.settings()), patch.object(
            billing_service, "_connection", factory
        ):
            billing_service.create_checkout(
                "tenant-a", "owner@example.com", "Tenant A", "START", client=client
            )

        checkout_lookup = next(
            call for call in cursor.execute.call_args_list
            if "FROM billing_checkout_sessions" in call.args[0]
        )
        self.assertEqual(
            checkout_lookup.args[1],
            ("tenant-a", "START", f"{billing_service.CHECKOUT_CONFIGURATION_PREFIX}%"),
        )
        checkout_insert = next(
            call for call in cursor.execute.call_args_list
            if "INSERT INTO billing_checkout_sessions" in call.args[0]
        )
        self.assertTrue(checkout_insert.args[1][3].startswith(billing_service.CHECKOUT_CONFIGURATION_PREFIX))

    def test_checkout_reuses_current_tax_session(self):
        factory, _ = self.connection([
            None,
            {"stripe_checkout_session_id": "cs_tax", "checkout_url": "https://checkout.stripe.test/current", "status": "open"},
        ])
        client = MagicMock()
        with patch.object(billing_service, "_settings", return_value=self.settings()), patch.object(
            billing_service, "_connection", factory
        ):
            result = billing_service.create_checkout(
                "tenant-a", "owner@example.com", "Tenant A", "START", client=client
            )

        self.assertEqual(result, {"checkout_url": "https://checkout.stripe.test/current"})
        client.v1.checkout.sessions.create.assert_not_called()

    def test_checkout_blocks_existing_stripe_subscription(self):
        factory, _ = self.connection([{"stripe_subscription_id": "sub_existing"}])
        client = MagicMock()
        with patch.object(billing_service, "_settings", return_value=self.settings()), patch.object(
            billing_service, "_connection", factory
        ), self.assertRaises(billing_service.BillingError) as raised:
            billing_service.create_checkout(
                "tenant-a", "owner@example.com", "Tenant A", "START", client=client
            )
        self.assertEqual(raised.exception.status_code, 409)
        client.v1.checkout.sessions.create.assert_not_called()

    def test_paid_invoice_activates_plan_for_mapped_tenant(self):
        factory, _ = self.connection([{"stripe_event_id": "evt_paid"}, {"tenant_id": "tenant-a"}])
        client = MagicMock()
        client.v1.subscriptions.retrieve.return_value = self.subscription()
        event = {"id": "evt_paid", "livemode": False, "type": "invoice.paid", "data": {"object": {
            "subscription": "sub_1", "customer": "cus_1",
        }}}
        with patch.object(billing_service, "_settings", return_value=self.settings()), patch.object(
            billing_service, "_connection", factory
        ), patch.object(billing_service, "_upsert_subscription") as upsert, patch.object(
            billing_service, "_set_app_plan"
        ) as set_plan:
            self.assertTrue(billing_service.process_event(event, client=client))
        self.assertEqual(upsert.call_args.args[1], "tenant-a")
        self.assertEqual(set_plan.call_args.args[1:3], ("tenant-a", "START"))

    def test_failed_payment_keeps_access_during_configured_grace(self):
        grace = datetime.now(timezone.utc) + timedelta(days=3)
        factory, _ = self.connection([
            {"stripe_event_id": "evt_failed"}, {"tenant_id": "tenant-a"},
            {"payment_grace_until": grace},
        ])
        client = MagicMock()
        client.v1.subscriptions.retrieve.return_value = self.subscription("past_due")
        event = {"id": "evt_failed", "livemode": False, "type": "invoice.payment_failed", "data": {"object": {
            "subscription": "sub_1", "customer": "cus_1",
        }}}
        with patch.object(billing_service, "_settings", return_value=self.settings()), patch.object(
            billing_service, "_connection", factory
        ), patch.object(billing_service, "_upsert_subscription") as upsert, patch.object(
            billing_service, "_set_app_plan"
        ) as set_plan:
            billing_service.process_event(event, client=client)
        self.assertEqual(upsert.call_args.args[1], "tenant-a")
        set_plan.assert_not_called()

    def test_deleted_subscription_returns_only_its_tenant_to_free(self):
        factory, _ = self.connection([{"stripe_event_id": "evt_deleted"}, {"tenant_id": "tenant-b"}])
        subscription = self.subscription("canceled")
        event = {"id": "evt_deleted", "livemode": False, "type": "customer.subscription.deleted",
                 "data": {"object": subscription}}
        with patch.object(billing_service, "_settings", return_value=self.settings()), patch.object(
            billing_service, "_connection", factory
        ), patch.object(billing_service, "_upsert_subscription"), patch.object(
            billing_service, "_set_app_plan"
        ) as set_plan:
            billing_service.process_event(event, client=MagicMock())
        set_plan.assert_called_once()
        self.assertEqual(set_plan.call_args.args[1:3], ("tenant-b", "FREE"))

    def test_delinquent_subscription_after_grace_returns_to_free(self):
        expired = datetime.now(timezone.utc) - timedelta(seconds=1)
        factory, _ = self.connection([
            {"stripe_event_id": "evt_unpaid"}, {"tenant_id": "tenant-a"},
            {"payment_grace_until": expired},
        ])
        subscription = self.subscription("unpaid")
        event = {"id": "evt_unpaid", "livemode": False,
                 "type": "customer.subscription.updated", "data": {"object": subscription}}
        with patch.object(billing_service, "_settings", return_value=self.settings()), patch.object(
            billing_service, "_connection", factory
        ), patch.object(billing_service, "_upsert_subscription"), patch.object(
            billing_service, "_set_app_plan"
        ) as set_plan:
            billing_service.process_event(event, client=MagicMock())
        self.assertEqual(set_plan.call_args.args[1:3], ("tenant-a", "FREE"))

    def test_duplicate_event_has_no_side_effects(self):
        factory, _ = self.connection([None])
        with patch.object(billing_service, "_settings", return_value=self.settings()), patch.object(
            billing_service, "_connection", factory
        ), patch.object(billing_service, "_set_app_plan") as set_plan:
            result = billing_service.process_event(
                {"id": "evt_duplicate", "livemode": False, "type": "invoice.paid", "data": {"object": {}}},
                client=MagicMock(),
            )
        self.assertFalse(result)
        set_plan.assert_not_called()

    def test_unknown_customer_cannot_cross_tenant_boundary(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        with self.assertRaises(billing_service.BillingError):
            billing_service._tenant_for_customer(cursor, "cus_unknown")


if __name__ == "__main__":
    unittest.main()
