"""Normalization and import orchestration for daily market prices."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from database_service import (upsert_market_price, get_pun_month_price,
                              get_psv_month_price, PunDataError)


class MarketPriceError(RuntimeError):
    pass


def previous_month(reference_date: date) -> date:
    return (reference_date.replace(day=1) - timedelta(days=1)).replace(day=1)


def get_prezzo_mercato(tipo_fornitura: str, data_str: str) -> dict[str, float]:
    comparison_date = date.fromisoformat(data_str)
    reference_date = comparison_date.replace(day=1)
    if tipo_fornitura.strip().lower() == "luce":
        try:
            row = get_pun_month_price(reference_date, completed_before=comparison_date)
            if row is None:
                row = get_pun_month_price(previous_month(reference_date), completed_before=comparison_date)
        except PunDataError as error:
            # Invalid historical counts must not silently trigger another average/fallback.
            raise MarketPriceError(str(error)) from error
        if row is None:
            raise MarketPriceError(f"PUN non disponibile per {reference_date:%Y-%m} né per {previous_month(reference_date):%Y-%m}")
        price = row["prezzo_medio"]
    elif tipo_fornitura.strip().lower() == "gas":
        row = get_psv_month_price(reference_date)
        if row is None:
            row = get_psv_month_price(previous_month(reference_date))
        if row is None:
            raise MarketPriceError(
                f"PSV non disponibile per {reference_date:%Y-%m} "
                f"né per {previous_month(reference_date):%Y-%m}"
            )
        price = row["value_eur_smc"]
    else:
        raise MarketPriceError(f"Tipo fornitura non supportato: {tipo_fornitura}")
    if price is None:
        raise MarketPriceError("Prezzo di mercato privo del valore richiesto")
    # disp is returned separately: the comparison adds it once for variable offers.
    return {"prezzo_medio": float(price), "disp": float(row["disp"] or 0)}


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
        value_eur_kwh=value_eur_kwh, source="GME", observation_count=observations,
    )
    return {
        "market": "PUN", "reference_date": target_date, "observations": observations,
        "value_eur_mwh": value_eur_mwh, "value_eur_kwh": value_eur_kwh, "action": action,
    }
