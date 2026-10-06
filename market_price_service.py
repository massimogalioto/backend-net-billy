"""Normalization and import orchestration for daily market prices."""
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from database_service import upsert_market_price


class MarketPriceError(RuntimeError):
    pass


def eur_mwh_to_eur_kwh(value_eur_mwh: Decimal) -> Decimal:
    return value_eur_mwh / Decimal("1000")


def calculate_daily_pun(rows: list[dict[str, Any]], target_date: date) -> tuple[Decimal, int]:
    """Return the mean of real PUN hourly observations (23, 24 or 25 only)."""
    flow_date = target_date.strftime("%Y%m%d")
    values: list[Decimal] = []
    seen_periods: set[tuple[Any, Any]] = set()
    for row in rows:
        if str(row.get("FlowDate")) != flow_date or row.get("Zone") != "PUN":
            continue
        key = (row.get("Hour"), row.get("Period"))
        if key in seen_periods:
            raise MarketPriceError("Osservazione PUN duplicata")
        seen_periods.add(key)
        try:
            value = Decimal(str(row["Price"]))
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            raise MarketPriceError("Prezzo PUN non numerico") from exc
        if not value.is_finite():
            raise MarketPriceError("Prezzo PUN non finito")
        values.append(value)

    if not values:
        raise MarketPriceError("Nessuna osservazione PUN per la data richiesta")
    if len(values) not in (23, 24, 25):
        raise MarketPriceError(f"Numero anomalo di osservazioni PUN: {len(values)}")
    return sum(values) / Decimal(len(values)), len(values)


def import_pun_date(target_date: date, client: Any,
                    persist: Callable[..., str] = upsert_market_price) -> dict[str, Any]:
    rows = client.request_pun_hourly(target_date)
    value_eur_mwh, observations = calculate_daily_pun(rows, target_date)
    value_eur_kwh = eur_mwh_to_eur_kwh(value_eur_mwh)
    action = persist(
        market="PUN", reference_date=target_date, value_eur_mwh=value_eur_mwh,
        value_eur_kwh=value_eur_kwh, source="GME",
    )
    return {
        "market": "PUN", "reference_date": target_date, "observations": observations,
        "value_eur_mwh": value_eur_mwh, "value_eur_kwh": value_eur_kwh, "action": action,
    }
