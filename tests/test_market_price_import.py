import base64
import io
import json
import unittest
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

import database_service
from gme_service import GmeConfigurationError, GmeError, GmeMarketClient
from import_market_prices import default_target_date
from market_price_service import (MarketPriceError, calculate_daily_pun,
                                  eur_mwh_to_eur_kwh, import_pun_date)


TARGET = date(2026, 10, 5)


def pun_rows(hours: int, value: str = "150"):
    return [{"FlowDate": "20261005", "Zone": "PUN", "Hour": number,
             "Period": "1", "Price": value} for number in range(1, hours + 1)]


class MarketPriceServiceTests(unittest.TestCase):
    def test_converts_eur_mwh_to_eur_kwh(self):
        self.assertEqual(eur_mwh_to_eur_kwh(Decimal("150")), Decimal("0.15"))

    def test_calculates_24_hour_pun(self):
        value, observations = calculate_daily_pun(pun_rows(24), TARGET)
        self.assertEqual((value, observations), (Decimal("150"), 24))

    def test_accepts_dst_days_with_23_or_25_hours(self):
        for hours in (23, 25):
            with self.subTest(hours=hours):
                value, observations = calculate_daily_pun(pun_rows(hours), TARGET)
                self.assertEqual(value, Decimal("150"))
                self.assertEqual(observations, hours)

    def test_rejects_empty_or_anomalous_dataset(self):
        with self.assertRaises(MarketPriceError):
            calculate_daily_pun([], TARGET)
        with self.assertRaises(MarketPriceError):
            calculate_daily_pun(pun_rows(22), TARGET)

    def test_rejects_duplicate_hour_period(self):
        rows = pun_rows(23)
        rows.append(rows[0].copy())
        with self.assertRaises(MarketPriceError):
            calculate_daily_pun(rows, TARGET)

    def test_reimport_is_idempotently_delegated_to_upsert(self):
        client = Mock(request_pun_hourly=Mock(return_value=pun_rows(24)))
        stored = {}

        def persist(**item):
            key = (item["market"], item["reference_date"])
            action = "update" if key in stored else "insert"
            stored[key] = item
            return action

        self.assertEqual(import_pun_date(TARGET, client, persist)["action"], "insert")
        self.assertEqual(import_pun_date(TARGET, client, persist)["action"], "update")
        self.assertEqual(len(stored), 1)

    def test_upsert_uses_real_unique_key_and_never_updates_disp(self):
        class Cursor:
            def __init__(self):
                self.sql = ""

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                return False

            def execute(self, sql, parameters):
                self.sql = sql
                self.parameters = parameters

            def fetchone(self):
                return {"inserted": False}

        class Connection:
            def __init__(self):
                self.cursor_instance = Cursor()

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                return False

            def cursor(self):
                return self.cursor_instance

        connection = Connection()
        original_connection = database_service._connection
        database_service._connection = lambda: connection
        try:
            action = database_service.upsert_market_price(
                market="PUN", reference_date=TARGET, value_eur_mwh=Decimal("150"),
                value_eur_kwh=Decimal("0.15"), source="GME",
            )
        finally:
            database_service._connection = original_connection
        normalized_sql = " ".join(connection.cursor_instance.sql.split()).lower()
        self.assertEqual(action, "update")
        self.assertIn("on conflict (market, reference_date) do update", normalized_sql)
        self.assertNotIn("disp =", normalized_sql)

    def test_default_date_uses_rome_calendar_not_utc_day(self):
        # 23:30 UTC is already the following calendar day in Rome in October.
        now = datetime(2026, 10, 5, 23, 30, tzinfo=timezone.utc)
        self.assertEqual(default_target_date(now), date(2026, 10, 5))


class GmeClientTests(unittest.TestCase):
    def test_missing_credentials_fail_without_a_request(self):
        client = GmeMarketClient(username="", password="", session=Mock())
        with self.assertRaises(GmeConfigurationError):
            client.request_pun_hourly(TARGET)

    def test_decodes_gme_json_zip(self):
        raw = json.dumps(pun_rows(24)).encode()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("pun.json", raw)
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = [
            {"success": True, "token": "test-token", "reason": None},
            {
                "requestId": "123", "formatType": ".json.zip", "resultRequest": None,
                "contentResponse": base64.b64encode(archive.getvalue()).decode(),
            },
        ]
        session = Mock(post=Mock(return_value=response))
        client = GmeMarketClient(username="user", password="password", session=session)
        self.assertEqual(client.request_pun_hourly(TARGET), pun_rows(24))
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(
            session.post.call_args_list[0].kwargs["json"],
            {"Login": "user", "Password": "password"},
        )
        self.assertEqual(
            session.post.call_args_list[1].kwargs["json"],
            {
                "Platform": "PublicMarketResults", "Segment": "MGP",
                "DataName": "ME_ZonalPrices", "IntervalStart": 20261005,
                "IntervalEnd": 20261005, "Attributes": {"GranularityType": "PT60"},
            },
        )
        self.assertEqual(
            session.post.call_args_list[1].kwargs["headers"],
            {"Authorization": "Bearer test-token", "Content-Type": "application/json"},
        )

    def test_empty_response_is_rejected(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = [
            {"success": True, "token": "test-token", "reason": None},
            {"requestId": "123", "formatType": ".json.zip", "resultRequest": None,
             "contentResponse": ""},
        ]
        client = GmeMarketClient(username="user", password="password",
                                 session=Mock(post=Mock(return_value=response)))
        with self.assertRaises(GmeError):
            client.request_pun_hourly(TARGET)

    def test_authentication_failure_uses_real_lowercase_response(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": False, "token": None, "reason": "Invalid credentials",
        }
        client = GmeMarketClient(username="user", password="password",
                                 session=Mock(post=Mock(return_value=response)))
        with self.assertRaises(GmeError):
            client.request_pun_hourly(TARGET)

    def test_request_data_result_request_is_an_error(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = [
            {"success": True, "token": "test-token", "reason": None},
            {"requestId": "123", "formatType": ".json.zip",
             "resultRequest": "No data available", "contentResponse": None},
        ]
        client = GmeMarketClient(username="user", password="password",
                                 session=Mock(post=Mock(return_value=response)))
        with self.assertRaisesRegex(GmeError, "No data available"):
            client.request_pun_hourly(TARGET)

    def test_timeout_is_reported(self):
        import requests
        session = Mock(post=Mock(side_effect=requests.Timeout()))
        client = GmeMarketClient(username="user", password="password", session=session)
        with self.assertRaises(GmeError):
            client.request_pun_hourly(TARGET)
