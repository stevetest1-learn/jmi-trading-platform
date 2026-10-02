import datetime as dt
from decimal import Decimal

import pytest

from app.risk.access import is_risk_viewer
from app.risk.overview import (
    AccountInfo,
    Mark,
    PositionInfo,
    SymbolInfo,
    Thresholds,
    compute_overview,
)
from app.ws.manager import ConnectionManager
from tests.conftest import auth_headers, login

D = Decimal
NOW = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.UTC)
THRESHOLDS = Thresholds(concentration_limit_pct=D("70"), utilization_warn_pct=D("80"))
SYMBOLS = [SymbolInfo("BTCUSD", "BTC/USD"), SymbolInfo("ETHUSD", "ETH/USD")]


def _accounts(alice_reserved="0"):
    return [
        AccountInfo(1, "market_maker", "Market Maker", D("5000000"), D("0")),
        AccountInfo(2, "alice", "Alice", D("100000"), D(alice_reserved)),
        AccountInfo(3, "bob", "Bob", D("100000"), D("0")),
    ]


def _pos(account_id, symbol, qty, avg="0", today="0", total="0"):
    return PositionInfo(account_id, symbol, D(qty), D(avg), D(today), D(total))


# ---------- compute_overview: maths ----------


def test_totals_shares_and_unrealized_pnl():
    result = compute_overview(
        symbols=SYMBOLS,
        accounts=_accounts(),
        positions=[
            _pos(1, "BTCUSD", "30", avg="50000"),
            _pos(2, "BTCUSD", "10", avg="55000", today="100", total="100"),
        ],
        marks={"BTCUSD": Mark(D("60000"), "MID"), "ETHUSD": Mark(None, "NONE")},
        thresholds=THRESHOLDS,
        as_of=NOW,
    )

    btc = next(s for s in result.symbols if s.symbol == "BTCUSD")
    assert btc.net_qty == 40
    assert btc.notional == 40 * 60000
    assert [h.username for h in btc.holders] == ["market_maker", "alice"]  # largest first
    assert btc.holders[0].share_pct == 75

    mm, alice = result.accounts[0], result.accounts[1]
    assert mm.username == "market_maker"  # accounts sorted by exposure
    assert mm.unrealized_pnl == 30 * (60000 - 50000)
    assert alice.unrealized_pnl == 10 * (60000 - 55000)
    assert alice.realized_pnl_today == 100
    assert mm.platform_share_pct == 75

    assert result.totals.net_exposure == 2_400_000
    assert result.totals.unrealized_pnl == 300_000 + 50_000
    assert result.totals.realized_pnl_today == 100


def test_flat_account_without_realized_pnl_has_no_position_rows():
    result = compute_overview(
        symbols=SYMBOLS,
        accounts=_accounts(),
        positions=[_pos(1, "BTCUSD", "5"), _pos(3, "BTCUSD", "0")],
        marks={"BTCUSD": Mark(D("60000"), "LAST_TRADE")},
        thresholds=THRESHOLDS,
        as_of=NOW,
    )
    bob = next(a for a in result.accounts if a.username == "bob")
    assert bob.positions == []
    assert bob.total_exposure == 0


def test_no_mark_leaves_values_unset_and_raises_warning():
    result = compute_overview(
        symbols=SYMBOLS,
        accounts=_accounts(),
        positions=[_pos(1, "ETHUSD", "100"), _pos(2, "ETHUSD", "100")],
        marks={},
        thresholds=THRESHOLDS,
        as_of=NOW,
    )
    eth = next(s for s in result.symbols if s.symbol == "ETHUSD")
    assert eth.mark_price is None and eth.mark_source == "NONE"
    assert result.accounts[0].positions[0].notional is None
    assert result.accounts[0].positions[0].unrealized_pnl is None
    assert result.totals.net_exposure == 0
    assert any(a.code == "NO_MARK" and a.symbol == "ETHUSD" for a in result.alerts)


# ---------- compute_overview: alert rules ----------


def test_concentration_over_limit_is_critical_and_sorted_first():
    result = compute_overview(
        symbols=SYMBOLS,
        accounts=_accounts(alice_reserved="90000"),
        positions=[_pos(1, "BTCUSD", "80"), _pos(2, "BTCUSD", "10"), _pos(3, "BTCUSD", "10")],
        marks={"BTCUSD": Mark(D("60000"), "MID")},
        thresholds=THRESHOLDS,
        as_of=NOW,
    )
    assert result.alerts[0].severity == "CRITICAL"
    assert result.alerts[0].code == "CONCENTRATION"
    assert result.alerts[0].account == "market_maker"
    assert "80.0%" in result.alerts[0].message
    assert [a.severity for a in result.alerts] == sorted(
        (a.severity for a in result.alerts), key=["CRITICAL", "WARNING", "INFO"].index
    )


def test_balanced_book_raises_no_concentration_alert():
    result = compute_overview(
        symbols=SYMBOLS,
        accounts=_accounts(),
        positions=[_pos(1, "BTCUSD", "10"), _pos(2, "BTCUSD", "10"), _pos(3, "BTCUSD", "10")],
        marks={"BTCUSD": Mark(D("60000"), "MID")},
        thresholds=THRESHOLDS,
        as_of=NOW,
    )
    assert [a for a in result.alerts if a.code == "CONCENTRATION"] == []


def test_utilization_alert_triggers_at_threshold_not_below():
    below = compute_overview(
        symbols=SYMBOLS, accounts=_accounts(alice_reserved="79999"), positions=[], marks={},
        thresholds=THRESHOLDS, as_of=NOW,
    )
    at = compute_overview(
        symbols=SYMBOLS, accounts=_accounts(alice_reserved="80000"), positions=[], marks={},
        thresholds=THRESHOLDS, as_of=NOW,
    )
    assert not [a for a in below.alerts if a.code == "UTILIZATION"]
    alert = next(a for a in at.alerts if a.code == "UTILIZATION")
    assert alert.severity == "WARNING" and alert.account == "alice"


# ---------- access control ----------


def test_only_configured_usernames_are_risk_viewers():
    assert is_risk_viewer("market_maker")
    assert not is_risk_viewer("alice")
    assert not is_risk_viewer(None)


@pytest.mark.asyncio(loop_scope="session")
async def test_overview_requires_authentication_and_the_viewer_role(client, seeded_accounts):
    assert (await client.get("/risk/overview")).status_code == 401

    alice_token = await login(client, "alice")
    assert (await client.get("/risk/overview", headers=auth_headers(alice_token))).status_code == 403

    mm_token = await login(client, "market_maker")
    assert (await client.get("/risk/overview", headers=auth_headers(mm_token))).status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_accounts_me_reports_can_view_risk(client, seeded_accounts):
    mm = await client.get("/accounts/me", headers=auth_headers(await login(client, "market_maker")))
    alice = await client.get("/accounts/me", headers=auth_headers(await login(client, "alice")))
    assert mm.json()["can_view_risk"] is True
    assert alice.json()["can_view_risk"] is False


# ---------- end to end through the real engine ----------


@pytest.mark.asyncio(loop_scope="session")
async def test_overview_reflects_real_trades_and_marks(client, seeded_accounts):
    mm = auth_headers(await login(client, "market_maker"))
    alice = auth_headers(await login(client, "alice"))

    # No trades, empty book: nothing to value, and the viewer is told so.
    first = (await client.get("/risk/overview", headers=mm)).json()
    assert first["symbols"][0]["mark_source"] == "NONE"
    assert any(a["code"] == "NO_MARK" for a in first["alerts"])

    # A two-sided book gives a MID mark: ask 51000, bid 49000 -> 50000.
    await client.post("/orders", headers=mm, json={"symbol": "BTCUSD", "side": "SELL", "order_type": "LIMIT", "qty": "1", "price": "51000"})
    await client.post("/orders", headers=alice, json={"symbol": "BTCUSD", "side": "BUY", "order_type": "LIMIT", "qty": "1", "price": "49000"})
    mid = (await client.get("/risk/overview", headers=mm)).json()
    assert mid["symbols"][0]["mark_source"] == "MID"
    assert Decimal(mid["symbols"][0]["mark_price"]) == 50000
    alice_row = next(a for a in mid["accounts"] if a["username"] == "alice")
    assert Decimal(alice_row["reserved_usd"]) == 49000  # open bid ties up cash

    # Cross the ask: only Alice's old bid is left, so the book is one-sided
    # and the mark falls back to the last trade.
    await client.post("/orders", headers=alice, json={"symbol": "BTCUSD", "side": "BUY", "order_type": "LIMIT", "qty": "1", "price": "51000"})
    after = (await client.get("/risk/overview", headers=mm)).json()
    btc = after["symbols"][0]
    assert btc["mark_source"] == "LAST_TRADE" and Decimal(btc["mark_price"]) == 51000

    by_user = {a["username"]: a for a in after["accounts"]}
    assert Decimal(by_user["alice"]["positions"][0]["net_qty"]) == 1
    assert Decimal(by_user["market_maker"]["positions"][0]["net_qty"]) == 49
    assert Decimal(after["totals"]["net_exposure"]) == 50 * 51000
    # market_maker was seeded at $0 cost basis, so all of its value is unrealized.
    assert Decimal(by_user["market_maker"]["unrealized_pnl"]) == 49 * 51000
    assert after["accounts"][0]["username"] == "market_maker"
    assert any(a["code"] == "CONCENTRATION" and a["account"] == "market_maker" for a in after["alerts"])


# ---------- live channel ----------


class _FakeSocket:
    def __init__(self):
        self.sent: list[str] = []

    async def send_text(self, message: str) -> None:
        self.sent.append(message)


@pytest.mark.asyncio(loop_scope="session")
async def test_risk_broadcast_reaches_only_risk_subscribers():
    manager = ConnectionManager()
    viewer, trader = _FakeSocket(), _FakeSocket()
    manager.connect(viewer, 1)
    manager.connect(trader, 2)
    manager.subscribe_risk(viewer)

    await manager.broadcast_risk("risk_dirty", {"symbol": "BTCUSD"})
    assert len(viewer.sent) == 1 and '"risk_dirty"' in viewer.sent[0]
    assert trader.sent == []

    manager.disconnect(viewer)
    await manager.broadcast_risk("risk_dirty", {})
    assert len(viewer.sent) == 1  # disconnected sockets stop receiving
