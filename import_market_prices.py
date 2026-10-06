"""Railway Cron entry point: import the previous Italian market day PUN."""
import argparse
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
    parser.add_argument("--date", dest="target_date", type=date.fromisoformat,
                        help="reference date in YYYY-MM-DD")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_date = args.target_date or default_target_date()
    try:
        result = import_pun_date(target_date, GmeMarketClient())
    except Exception as exc:
        print(f"[GME] market=PUN reference_date={target_date} status=error error={exc}", file=sys.stderr)
        return 1
    print(f"[GME] market={result['market']} reference_date={result['reference_date']} "
          f"observations={result['observations']} value_eur_mwh={result['value_eur_mwh']} "
          f"value_eur_kwh={result['value_eur_kwh']}")
    print(f"[DB] action={result['action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
