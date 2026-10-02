import datetime as dt
from decimal import Decimal

import pytest

from app.db.base import async_session_factory
from app.settlement.eod import settle_day
from tests.conftest import auth_headers, login


@pytest.mark.asyncio(loop_scope="session")
async def test_full_trading_flow(client, seeded_accounts):
    bob_token = await login(client, "bob")
    alice_token = await login(client, "alice")
    mm_token = await login(client, "market_maker")

    # 1. Reject path: bob holds no BTC, a naked SELL must be rejected, not queued.
    resp = await client.post(
        "/orders",
        json={"symbol": "BTCUSD", "side": "SELL", "order_type": "LIMIT", "qty": "1", "price": "50000"},
        headers=auth_headers(bob_token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "REJECTED"
    assert body["reject_reason"] == "INSUFFICIENT_POSITION"

    # 2. market_maker (has starting BTC inventory) rests a SELL -- no counterparty yet.
    resp = await client.post(
        "/orders",
        json={"symbol": "BTCUSD", "side": "SELL", "order_type": "LIMIT", "qty": "1", "price": "50000"},
        headers=auth_headers(mm_token),
    )
    assert resp.status_code == 201
    mm_order = resp.json()
    assert mm_order["status"] == "NEW"
    assert mm_order["fills"] == []

    # 3. alice crosses it with a BUY -> a real fill/trade/position update.
    resp = await client.post(
        "/orders",
        json={"symbol": "BTCUSD", "side": "BUY", "order_type": "LIMIT", "qty": "1", "price": "50000"},
        headers=auth_headers(alice_token),
    )
    assert resp.status_code == 201
    alice_order = resp.json()
    assert alice_order["status"] == "FILLED"
    assert len(alice_order["fills"]) == 1
    trade_id = alice_order["fills"][0]["trade_id"]
    assert Decimal(alice_order["fills"][0]["price"]) == 50000

    # 4. Positions reflect the fill on both sides.
    resp = await client.get("/positions", headers=auth_headers(alice_token))
    alice_positions = {p["symbol"]: p for p in resp.json()}
    assert Decimal(alice_positions["BTCUSD"]["net_qty"]) == 1
    assert Decimal(alice_positions["BTCUSD"]["avg_cost"]) == 50000

    resp = await client.get("/positions", headers=auth_headers(mm_token))
    mm_positions = {p["symbol"]: p for p in resp.json()}
    assert Decimal(mm_positions["BTCUSD"]["net_qty"]) == 49

    # 5. Alice's blotter shows the FILL row with the matching trade id.
    resp = await client.get("/blotter", headers=auth_headers(alice_token))
    fill_rows = [r for r in resp.json() if r["status"] == "FILL"]
    assert len(fill_rows) == 1
    assert fill_rows[0]["trade_id"] == trade_id
    assert fill_rows[0]["side"] == "BUY"

    # 6. Bob's blotter shows his REJECT row.
    resp = await client.get("/blotter", headers=auth_headers(bob_token))
    reject_rows = [r for r in resp.json() if r["status"] == "REJECT"]
    assert len(reject_rows) == 1
    assert reject_rows[0]["reject_reason"] == "INSUFFICIENT_POSITION"

    # 7. Alice sells at a higher price -> realized P&L.
    resp = await client.post(
        "/orders",
        json={"symbol": "BTCUSD", "side": "SELL", "order_type": "LIMIT", "qty": "1", "price": "52000"},
        headers=auth_headers(alice_token),
    )
    assert resp.json()["status"] == "NEW"

    resp = await client.post(
        "/orders",
        json={"symbol": "BTCUSD", "side": "BUY", "order_type": "LIMIT", "qty": "1", "price": "52000"},
        headers=auth_headers(mm_token),
    )
    assert resp.json()["status"] == "FILLED"

    resp = await client.get("/positions", headers=auth_headers(alice_token))
    alice_positions = {p["symbol"]: p for p in resp.json()}
    assert Decimal(alice_positions["BTCUSD"]["net_qty"]) == 0
    assert Decimal(alice_positions["BTCUSD"]["realized_pnl_today"]) == 2000

    # 8. EOD settlement snapshots and resets today's realized P&L (but not the lifetime total).
    async with async_session_factory() as session, session.begin():
        result = await settle_day(session, dt.datetime.now(dt.UTC).date())
    assert result["skipped"] is False
    assert result["accounts_snapshotted"] > 0
    assert result["trades_settled"] == 2

    resp = await client.get("/positions", headers=auth_headers(alice_token))
    alice_positions = {p["symbol"]: p for p in resp.json()}
    assert Decimal(alice_positions["BTCUSD"]["realized_pnl_today"]) == 0
    assert Decimal(alice_positions["BTCUSD"]["realized_pnl_total"]) == 2000

    # Re-running the same day's settlement is a no-op.
    async with async_session_factory() as session, session.begin():
        result2 = await settle_day(session, dt.datetime.now(dt.UTC).date())
    assert result2["skipped"] is True
