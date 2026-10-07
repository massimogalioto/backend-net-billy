"""Railway Cron entry point: import the previous Italian market day PUN."""
import argparse
import re
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from gme_service import GmeMarketClient
from market_price_service import import_pun_date


ROME_TZ = ZoneInfo("Europe/Rome")


def default_target_date(now: datetime | None = None) -> date:
    local_now = now.astimezone(ROME_TZ) if now else datetime.now(ROME_TZ)
    return local_now.date() - timedelta(days=1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import daily GME PUN into PostgreSQL")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--date", dest="target_date", type=date.fromisoformat,
                        help="reference date in YYYY-MM-DD")
    group.add_argument("--month", type=parse_month,
                       help="reimport completed days of YYYY-MM")
    return parser.parse_args(argv)


def parse_month(value: str) -> date:
    try:
        if not re.fullmatch(r"\d{4}-\d{2}", value):
            raise ValueError
        return date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise argparse.ArgumentTypeError("mese non valido: usare YYYY-MM con mese da 01 a 12") from exc


def month_days(month: date, today: date) -> list[date]:
    if month > today.replace(day=1):
        raise ValueError("Non è possibile importare un mese futuro")
    next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    end = min(next_month, today)
    return [month + timedelta(days=offset) for offset in range((end - month).days)]


def print_result(result: dict) -> None:
    print(f"[GME] market={result['market']} reference_date={result['reference_date']} "
          f"observations={result['observations']} value_eur_mwh={result['value_eur_mwh']} "
          f"value_eur_kwh={result['value_eur_kwh']}")
    print(f"[DB] action={result['action']}")


def import_month(month: date) -> int:
    # Same Europe/Rome calendar as the existing daily cron.
    try:
        days = month_days(month, default_target_date() + timedelta(days=1))
    except ValueError as exc:
        print(f"[PUN MONTH] month={month:%Y-%m} error={exc}", file=sys.stderr)
        return 1
    print(f"[PUN MONTH] month={month:%Y-%m}")
    print(f"[PUN MONTH] days_requested={len(days)}")
    failures = []
    for day in days:
        try:
            result = import_pun_date(day, GmeMarketClient())
        except Exception as exc:
            failures.append(day)
            print(f"[GME] market=PUN reference_date={day} status=error error={exc}", file=sys.stderr)
            continue
        print_result(result)
    print(f"[PUN MONTH] success={len(days) - len(failures)}")
    print(f"[PUN MONTH] failed={len(failures)}")
    if failures:
        print("[PUN MONTH] failed_dates=" + ",".join(day.isoformat() for day in failures), file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.month is not None:
        return import_month(args.month)
    target_date = args.target_date or default_target_date()
    try:
        result = import_pun_date(target_date, GmeMarketClient())
    except Exception as exc:
        print(f"[GME] market=PUN reference_date={target_date} status=error error={exc}", file=sys.stderr)
        print("[CRON] status=failed", file=sys.stderr)
        return 1
    print_result(result)
    print("[CRON] status=success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
