import csv
import datetime as dt
from decimal import Decimal

import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio(loop_scope="session")
async def test_fill_writes_both_sides_to_todays_csv(client, seeded_accounts, tmp_path, monkeypatch):
    monkeypatch.setenv("TRADE_LOG_DIR", str(tmp_path))

    mm_token = await login(client, "market_maker")
    alice_token = await login(client, "alice")

    resp = await client.post(
        "/orders",
        json={"symbol": "BTCUSD", "side": "SELL", "order_type": "LIMIT", "qty": "1", "price": "51000"},
        headers=auth_headers(mm_token),
    )
    assert resp.json()["status"] == "NEW"

    resp = await client.post(
        "/orders",
        json={"symbol": "BTCUSD", "side": "BUY", "order_type": "LIMIT", "qty": "1", "price": "51000"},
        headers=auth_headers(alice_token),
    )
    order = resp.json()
    assert order["status"] == "FILLED"
    trade_id = order["fills"][0]["trade_id"]

    today = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    csv_path = tmp_path / f"{today}.csv"
    assert csv_path.exists()

    with csv_path.open() as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2
    by_side = {r["side"]: r for r in rows}

    buy_row = by_side["BUY"]
    assert buy_row["trade_id"] == str(trade_id)
    assert buy_row["account"] == "alice"
    assert buy_row["symbol"] == "BTCUSD"
    assert Decimal(buy_row["order_price"]) == 51000
    assert Decimal(buy_row["order_qty"]) == 1
    assert Decimal(buy_row["fill_qty"]) == 1
    assert Decimal(buy_row["fill_price"]) == 51000
    assert Decimal(buy_row["realized_pnl_this_fill"]) == 0  # a BUY never realizes P&L

    sell_row = by_side["SELL"]
    assert sell_row["account"] == "market_maker"
    assert Decimal(sell_row["order_price"]) == 51000
    assert Decimal(sell_row["realized_pnl_this_fill"]) == 51000  # 1 * (51000 - 0 avg_cost)
    assert Decimal(sell_row["net_qty_after"]) == 49


@pytest.mark.asyncio(loop_scope="session")
async def test_rejected_order_writes_no_csv_row(client, seeded_accounts, tmp_path, monkeypatch):
    monkeypatch.setenv("TRADE_LOG_DIR", str(tmp_path))
    bob_token = await login(client, "bob")

    resp = await client.post(
        "/orders",
        json={"symbol": "BTCUSD", "side": "SELL", "order_type": "LIMIT", "qty": "1", "price": "51000"},
        headers=auth_headers(bob_token),
    )
    assert resp.json()["status"] == "REJECTED"

    today = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    assert not (tmp_path / f"{today}.csv").exists()
