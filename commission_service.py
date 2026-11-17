"""Tenant-scoped persistence for CTE commission bands."""
from decimal import Decimal
from typing import Any

from database_service import _connection


def validate_bands(bands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for band in bands:
        minimum = band["min_contracts"]
        maximum = band.get("max_contracts")
        base = Decimal(str(band["base_amount"]))
        bonus = Decimal(str(band["sepa_bonus"]))
        if minimum < 0 or (maximum is not None and maximum < minimum):
            raise ValueError("Soglie contrattuali non valide")
        if base < 0 or bonus < 0:
            raise ValueError("Gli importi non possono essere negativi")
        normalized.append({"min_contracts": minimum, "max_contracts": maximum,
                           "base_amount": base, "sepa_bonus": bonus})
    normalized.sort(key=lambda item: item["min_contracts"])
    for index, band in enumerate(normalized):
        if index and normalized[index - 1]["max_contracts"] is None:
            raise ValueError("La fascia senza limite massimo deve essere l'ultima")
        if index and band["min_contracts"] <= normalized[index - 1]["max_contracts"]:
            raise ValueError("Le fasce non possono sovrapporsi o essere duplicate")
    return normalized


def list_commissions(offer_ids: list[str], tenant_id: str) -> list[dict[str, Any]]:
    if not offer_ids:
        return []
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT o.id AS cte_offer_id, o.supplier, o.offer_name,
                      c.min_contracts, c.max_contracts, c.base_amount, c.sepa_bonus
               FROM cte_offers o LEFT JOIN cte_commissions c
                 ON c.cte_offer_id = o.id AND c.tenant_id = o.tenant_id
               WHERE o.tenant_id = %s AND o.id = ANY(%s::uuid[])
               ORDER BY array_position(%s::uuid[], o.id), c.min_contracts""",
            (tenant_id, offer_ids, offer_ids),
        )
        grouped: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            key = str(row["cte_offer_id"])
            offer = grouped.setdefault(key, {"cte_offer_id": key, "supplier": row["supplier"],
                                             "offer_name": row["offer_name"], "bands": []})
            if row["min_contracts"] is not None:
                offer["bands"].append({"min_contracts": row["min_contracts"],
                    "max_contracts": row["max_contracts"],
                    "base_amount": str(row["base_amount"]), "sepa_bonus": str(row["sepa_bonus"])})
        return list(grouped.values())


def replace_commissions(offer_ids: list[str], bands: list[dict[str, Any]], tenant_id: str,
                        overwrite: bool) -> list[str]:
    normalized = validate_bands(bands)
    unique_ids = list(dict.fromkeys(offer_ids))
    if not unique_ids:
        raise ValueError("Seleziona almeno una CTE")
    with _connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM cte_offers WHERE tenant_id = %s AND id = ANY(%s::uuid[]) FOR UPDATE",
                    (tenant_id, unique_ids))
        found = {str(row["id"]) for row in cur.fetchall()}
        if found != set(unique_ids):
            raise LookupError("Una o più CTE non esistono o non appartengono al tenant")
        cur.execute("SELECT DISTINCT cte_offer_id FROM cte_commissions WHERE tenant_id = %s AND cte_offer_id = ANY(%s::uuid[])",
                    (tenant_id, unique_ids))
        configured = [str(row["cte_offer_id"]) for row in cur.fetchall()]
        if configured and not overwrite:
            raise FileExistsError(",".join(configured))
        cur.execute("DELETE FROM cte_commissions WHERE tenant_id = %s AND cte_offer_id = ANY(%s::uuid[])",
                    (tenant_id, unique_ids))
        for offer_id in unique_ids:
            cur.executemany(
                """INSERT INTO cte_commissions
                   (tenant_id, cte_offer_id, min_contracts, max_contracts, base_amount, sepa_bonus)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [(tenant_id, offer_id, band["min_contracts"], band["max_contracts"],
                  band["base_amount"], band["sepa_bonus"]) for band in normalized],
            )
    return unique_ids


def delete_commissions(offer_id: str, tenant_id: str) -> bool:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM cte_offers WHERE id = %s AND tenant_id = %s FOR UPDATE", (offer_id, tenant_id))
        if not cur.fetchone():
            raise LookupError("CTE non trovata")
        cur.execute("DELETE FROM cte_commissions WHERE cte_offer_id = %s AND tenant_id = %s", (offer_id, tenant_id))
        return cur.rowcount > 0
