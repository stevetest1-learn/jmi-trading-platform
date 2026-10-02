"""CLI entrypoint for the end-of-day settlement job.

Local:  python -m scripts.run_eod_settlement --date 2026-09-22
AWS:    same image/command, run as a scheduled one-off ECS task (see infra/eventbridge.tf).
"""

import argparse
import asyncio
import datetime as dt

from app.db.base import async_session_factory
from app.settlement.eod import settle_day


async def main(settlement_date: dt.date) -> None:
    async with async_session_factory() as session, session.begin():
        result = await settle_day(session, settlement_date)
    print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD, defaults to today (UTC)")
    args = parser.parse_args()
    target_date = dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(dt.UTC).date()
    asyncio.run(main(target_date))
