"""Per-trade debug CSV, one file per day (YYYYMMDD.csv).

Deliberately a plain local file, not a DB table: this is a quick,
human-readable debugging aid ("anyone can open it and see what happened"),
written only after the fill's DB transaction has actually committed (see
callers in app/engine/engine.py) so it can never record a trade that got
rolled back. On AWS/ECS this directory is on the task's local (ephemeral)
disk -- fine for local debugging, but it won't survive a task restart or be
shared across replicas; swap in S3 if this needs to persist there.
"""

import csv
import datetime as dt
import os
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[3] / "trade_logs"

FIELDNAMES = [
    "timestamp",
    "trade_id",
    "symbol",
    "account",
    "side",
    "order_id",
    "order_type",
    "order_price",
    "order_qty",
    "fill_qty",
    "fill_price",
    "realized_pnl_this_fill",
    "realized_pnl_today_after",
    "realized_pnl_total_after",
    "net_qty_after",
    "avg_cost_after",
]


def _log_dir() -> Path:
    return Path(os.environ.get("TRADE_LOG_DIR", str(DEFAULT_LOG_DIR)))


def log_trade_rows(rows: list[dict]) -> None:
    """Append rows (one per counterparty per fill) to today's CSV, writing
    the header once per file. Best-effort: a logging problem here must
    never break order matching, so callers should not let an exception from
    this function propagate into the request/response path."""
    if not rows:
        return

    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    path = log_dir / f"{date_str}.csv"

    is_new = not path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
