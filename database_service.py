"""PostgreSQL access for CTE offers.

This module deliberately exposes the same Airtable-shaped records consumed by
the comparison algorithm, keeping calculation code independent of persistence.
"""
import os
from decimal import Decimal
from datetime import date
from typing import Any
from urllib.parse import unquote, urlparse

import psycopg
from psycopg.rows import dict_row


class ConfigurationError(RuntimeError):
    pass


def default_tenant_id() -> str:
    # TEMPORARY: remove when authentication/tenant resolution is implemented
    tenant_id = os.getenv("DEFAULT_TENANT_ID")
    if not tenant_id:
        raise ConfigurationError("DEFAULT_TENANT_ID non configurato")
    return tenant_id


def _connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ConfigurationError("DATABASE_URL non configurato")
    return psycopg.connect(database_url, row_factory=dict_row)


def database_fingerprint() -> dict[str, str]:
    """Return only non-secret connection identifiers for temporary diagnostics."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ConfigurationError("DATABASE_URL non configurato")
    parsed = urlparse(database_url)
    return {
        "host": parsed.hostname or "unknown",
        "database": unquote(parsed.path).lstrip("/") or "unknown",
    }


def _normalize_numeric(value: Any) -> Any:
    """Keep the legacy comparison contract: database NUMERIC becomes float."""
    return float(value) if isinstance(value, Decimal) else value


def _offer_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id_offerta": str(row["id"]),
        "Fornitore": row["supplier"],
        "Nome offerta": row["offer_name"],
        "Tipologia cliente": row["customer_type"],
        "Tipo fornitura": row["supply_type"],
        "Tipo tariffa": row["tariff_type"],
        "Prezzo fisso €/kWh": _normalize_numeric(row["fixed_price_kwh"]),
        "Spread €/kWh": _normalize_numeric(row["spread_kwh"]),
        "Costo fisso mensile": _normalize_numeric(row["monthly_fixed_cost"]) or 0,
        "Data validità": row["valid_from"],
        "Fonte CTE": row["source_cte"],
        "Note": row["notes"],
        "min_power_kw": _normalize_numeric(row.get("min_power_kw")),
        "max_power_kw": _normalize_numeric(row.get("max_power_kw")),
        "pdf_filename": row["pdf_filename"],
        "pdf_content_type": row["pdf_content_type"],
        "has_pdf": bool(row["pdf_object_key"]),
    }


def is_power_eligible(customer_power_kw: float | None, min_power_kw: Any,
                      max_power_kw: Any) -> bool:
    """Keep unrestricted offers visible when a bill has no contractual power."""
    if customer_power_kw is None:
        return True
    customer_power = float(customer_power_kw)
    minimum = _normalize_numeric(min_power_kw)
    maximum = _normalize_numeric(max_power_kw)
    return ((minimum is None or customer_power >= minimum) and
            (maximum is None or customer_power <= maximum))


def get_offerte(tipo_fornitura: str, tipologia_cliente: str,
                customer_power_kw: float | None = None) -> list[dict[str, Any]]:
    tenant_id = default_tenant_id()
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT * FROM cte_offers
               WHERE tenant_id = %s AND supply_type = %s AND customer_type = %s
                 AND (valid_from IS NULL OR valid_from <= CURRENT_DATE)
                 AND (valid_until IS NULL OR valid_until >= CURRENT_DATE)
                 AND (%s::numeric IS NULL OR
                      ((min_power_kw IS NULL OR %s::numeric >= min_power_kw)
                       AND (max_power_kw IS NULL OR %s::numeric <= max_power_kw)))
               ORDER BY created_at DESC""",
            (tenant_id, tipo_fornitura, tipologia_cliente,
             customer_power_kw, customer_power_kw, customer_power_kw),
        )
        return [{"id": str(row["id"]), "fields": _offer_fields(row)} for row in cur.fetchall()]


def find_duplicate_cte_offer(dati: dict[str, Any]) -> str | None:
    # TODO: enforce duplicate protection at database level after the
    # duplicate fingerprint has been validated in production.
    tenant_id = default_tenant_id()
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM cte_offers
               WHERE tenant_id = %s
                 AND TRIM(supplier) IS NOT DISTINCT FROM %s
                 AND TRIM(customer_type) IS NOT DISTINCT FROM %s
                 AND TRIM(supply_type) IS NOT DISTINCT FROM %s
                 AND TRIM(tariff_type) IS NOT DISTINCT FROM %s
                 AND valid_until IS NOT DISTINCT FROM %s::date
                 AND fixed_price_kwh IS NOT DISTINCT FROM %s
                 AND spread_kwh IS NOT DISTINCT FROM %s
                 AND monthly_fixed_cost IS NOT DISTINCT FROM %s
                 AND min_power_kw IS NOT DISTINCT FROM %s
                 AND max_power_kw IS NOT DISTINCT FROM %s
               ORDER BY created_at, id LIMIT 1""",
            (tenant_id, *(value.strip() if isinstance(value, str) else value
                          for value in (dati.get("fornitore"), dati.get("tipologia_cliente"),
                                        dati.get("tipo_fornitura"), dati.get("tariffa"))),
             dati.get("valid_until") or None, dati.get("prezzo_kwh"),
             dati.get("spread"), dati.get("costo_fisso"), dati.get("min_power_kw"),
             dati.get("max_power_kw")),
        )
        row = cur.fetchone()
        return str(row["id"]) if row else None


def insert_offer(dati: dict[str, Any], pdf_metadata: dict[str, Any] | None = None) -> str:
    tenant_id = default_tenant_id()
    metadata = pdf_metadata or {}
    valid_from = dati.get("validita") or None
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO cte_offers
               (tenant_id, supplier, offer_name, customer_type, supply_type, tariff_type,
                fixed_price_kwh, spread_kwh, monthly_fixed_cost, valid_from, valid_until, source_cte,
                notes, min_power_kw, max_power_kw, pdf_object_key, pdf_filename, pdf_content_type, pdf_size_bytes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (tenant_id, dati.get("fornitore"), dati.get("nome_offerta"),
             dati.get("tipologia_cliente"), dati.get("tipo_fornitura"), dati.get("tariffa"),
             dati.get("prezzo_kwh"), dati.get("spread"), dati.get("costo_fisso"), valid_from,
             dati.get("valid_until") or None,
             dati.get("fonte_cte"), dati.get("vincoli"), dati.get("min_power_kw"),
             dati.get("max_power_kw"), metadata.get("object_key"),
             metadata.get("filename"), metadata.get("content_type"), metadata.get("size_bytes")),
        )
        return str(cur.fetchone()["id"])


def get_offer_pdf(offer_id: str) -> dict[str, Any] | None:
    tenant_id = default_tenant_id()
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, pdf_object_key, pdf_filename, pdf_content_type
               FROM cte_offers WHERE id = %s AND tenant_id = %s""",
            (offer_id, tenant_id),
        )
        return cur.fetchone()


def upsert_market_price(*, market: str, reference_date: date, value_eur_mwh: Decimal,
                        value_eur_kwh: Decimal, source: str, observation_count: int) -> str:
    """Create or refresh one daily market price without changing ``disp``."""
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO market_prices
                   (market, reference_date, value_eur_mwh, value_eur_kwh, source, observation_count)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (market, reference_date) DO UPDATE
               SET value_eur_mwh = EXCLUDED.value_eur_mwh,
                   value_eur_kwh = EXCLUDED.value_eur_kwh,
                   source = EXCLUDED.source,
                   observation_count = EXCLUDED.observation_count,
                   updated_at = NOW()
               RETURNING (xmax = 0) AS inserted""",
            (market, reference_date, value_eur_mwh, value_eur_kwh, source, observation_count),
        )
        return "insert" if cur.fetchone()["inserted"] else "update"


def get_pun_daily_record(reference_date: date) -> dict[str, Any] | None:
    """Read back a PUN row after an import, for temporary cron diagnostics."""
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT reference_date, value_eur_kwh, observation_count
               FROM market_prices
               WHERE market = 'PUN' AND reference_date = %s""",
            (reference_date,),
        )
        return cur.fetchone()


def get_monthly_market_prices(market: str, year: int, month: int) -> list[dict[str, Any]]:
    """Return daily prices without inferring a monthly aggregate."""
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT reference_date, value_eur_mwh, value_eur_kwh, disp
               FROM market_prices
               WHERE market = %s
                 AND reference_date >= make_date(%s, %s, 1)
                 AND reference_date < make_date(%s, %s, 1) + INTERVAL '1 month'
               ORDER BY reference_date""",
            (market, year, month, year, month),
        )
        return [{key: _normalize_numeric(value) for key, value in row.items()}
                for row in cur.fetchall()]


class PunDataError(RuntimeError):
    """PUN daily data must be reimported before calculating a monthly value."""


def get_pun_month_price(reference_date: date, *, completed_before: date | None = None) -> dict[str, Any] | None:
    """Weight completed daily PUN prices by their actual GME observation counts."""
    with _connection() as conn, conn.cursor() as cur:
        month_start = reference_date.replace(day=1)
        completed_limit = completed_before or reference_date
        cur.execute(
            """SELECT reference_date, value_eur_kwh, observation_count
               FROM market_prices
               WHERE market = 'PUN'
                 AND reference_date >= %s
                 AND reference_date < %s + INTERVAL '1 month'
                 AND reference_date < %s
               ORDER BY reference_date""",
            (month_start, month_start, completed_limit),
        )
        records = cur.fetchall()
        valid_rows = 0
        for record in records:
            observations = record["observation_count"]
            price = record["value_eur_kwh"]
            if observations is None:
                valid, reason = False, "observation_count_null"
            elif not isinstance(observations, int):
                valid, reason = False, "invalid_type"
            elif observations == 0:
                valid, reason = False, "observation_count_zero"
            elif observations not in (23, 24, 25):
                valid, reason = False, "invalid_observation_count"
            elif price is None:
                valid, reason = False, "value_eur_kwh_null"
            else:
                valid, reason = True, "ok"
                valid_rows += 1
            print("[PUN READER] "
                  f"reference_date={record['reference_date']} value_eur_kwh={price} "
                  f"observation_count={observations} valid={str(valid).lower()} reason={reason}")
        print("[PUN READER SUMMARY] "
              f"month={reference_date:%Y-%m} rows_found={len(records)} "
              f"valid_rows={valid_rows} invalid_rows={len(records) - valid_rows}")
        cur.execute(
            """SELECT SUM(value_eur_kwh * observation_count)
                          / NULLIF(SUM(observation_count), 0) AS prezzo_medio,
                      AVG(COALESCE(disp, 0)) AS disp,
                      COUNT(*) AS days,
                      COUNT(*) FILTER (WHERE observation_count IS NULL
                          OR observation_count NOT IN (23, 24, 25)
                          OR value_eur_kwh IS NULL) AS invalid_days
               FROM market_prices
               WHERE market = 'PUN'
                 AND reference_date >= %s
                 AND reference_date < %s + INTERVAL '1 month'
                 AND reference_date < %s""",
            (month_start, month_start, completed_limit),
        )
        row = cur.fetchone()
        if not row or not row["days"]:
            return None
        if row["invalid_days"]:
            raise PunDataError(
                f"PUN {reference_date:%Y-%m}: {row['invalid_days']} giorni senza "
                "observation_count valido o prezzo. Reimportare i giorni dal GME."
            )
        return {"prezzo_medio": row["prezzo_medio"], "disp": row["disp"]}


def get_psv_month_price(reference_date: date) -> dict[str, Any] | None:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT reference_date, value_eur_smc, disp
               FROM market_prices
               WHERE market = 'PSV' AND reference_date = %s""",
            (reference_date.replace(day=1),),
        )
        return cur.fetchone()


def upsert_psv_month_price(reference_date: date, value_eur_smc: Decimal, disp: Decimal) -> str:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO market_prices
                   (market, reference_date, value_eur_smc, disp, source)
               VALUES ('PSV', %s, %s, %s, 'MANUAL')
               ON CONFLICT (market, reference_date) DO UPDATE
               SET value_eur_smc = EXCLUDED.value_eur_smc,
                   disp = EXCLUDED.disp, source = EXCLUDED.source, updated_at = NOW()
               RETURNING (xmax = 0) AS inserted""",
            (reference_date.replace(day=1), value_eur_smc, disp),
        )
        return "insert" if cur.fetchone()["inserted"] else "update"
