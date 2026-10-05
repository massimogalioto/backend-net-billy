"""PostgreSQL access for CTE offers.

This module deliberately exposes the same Airtable-shaped records consumed by
the comparison algorithm, keeping calculation code independent of persistence.
"""
import os
from datetime import date
from typing import Any

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


def _offer_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id_offerta": str(row["id"]),
        "Fornitore": row["supplier"],
        "Nome offerta": row["offer_name"],
        "Tipologia cliente": row["customer_type"],
        "Tipo fornitura": row["supply_type"],
        "Tipo tariffa": row["tariff_type"],
        "Prezzo fisso €/kWh": row["fixed_price_kwh"],
        "Spread €/kWh": row["spread_kwh"],
        "Costo fisso mensile": row["monthly_fixed_cost"] or 0,
        "Data validità": row["valid_from"],
        "Fonte CTE": row["source_cte"],
        "Note": row["notes"],
        "pdf_filename": row["pdf_filename"],
        "pdf_content_type": row["pdf_content_type"],
        "has_pdf": bool(row["pdf_object_key"]),
    }


def get_offerte(tipo_fornitura: str, tipologia_cliente: str) -> list[dict[str, Any]]:
    tenant_id = default_tenant_id()
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT * FROM cte_offers
               WHERE tenant_id = %s AND supply_type = %s AND customer_type = %s
                 AND (valid_from IS NULL OR valid_from <= CURRENT_DATE)
                 AND (valid_until IS NULL OR valid_until >= CURRENT_DATE)
               ORDER BY created_at DESC""",
            (tenant_id, tipo_fornitura, tipologia_cliente),
        )
        return [{"id": str(row["id"]), "fields": _offer_fields(row)} for row in cur.fetchall()]


def insert_offer(dati: dict[str, Any], pdf_metadata: dict[str, Any] | None = None) -> str:
    tenant_id = default_tenant_id()
    metadata = pdf_metadata or {}
    valid_from = dati.get("validita") or None
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO cte_offers
               (tenant_id, supplier, offer_name, customer_type, supply_type, tariff_type,
                fixed_price_kwh, spread_kwh, monthly_fixed_cost, valid_from, source_cte,
                notes, pdf_object_key, pdf_filename, pdf_content_type, pdf_size_bytes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (tenant_id, dati.get("fornitore"), dati.get("nome_offerta"),
             dati.get("tipologia_cliente"), dati.get("tipo_fornitura"), dati.get("tariffa"),
             dati.get("prezzo_kwh"), dati.get("spread"), dati.get("costo_fisso"), valid_from,
             dati.get("fonte_cte"), dati.get("vincoli"), metadata.get("object_key"),
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
