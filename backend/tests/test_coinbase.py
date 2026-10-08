import datetime as dt
import json
from decimal import Decimal

import pytest

from app.config import settings
from app.marketdata.coinbase import CoinbaseFeed, parse_ticker
from app.ws.manager import ConnectionManager
from tests.conftest import auth_headers, login

PRODUCTS = {"BTC-USD": "BTCUSD", "ETH-USD": "ETHUSD"}


def ticker(product="BTC-USD", price="82364", **over):
    # Shaped like a real message captured from Coinbase's public feed.
    msg = {
        "type": "ticker",
        "sequence": 137418961527,
        "product_id": product,
        "price": price,
        "open_24h": "83464.09",
        "volume_24h": "7084.34604864",
        "low_24h": "82155.78",
        "high_24h": "83655.03",
        "best_bid": "82363.99",
        "best_bid_size": "0.05407063",
        "best_ask": "82364.00",
        "best_ask_size": "0.63264285",
        "side": "buy",
        "time": "2026-10-08T12:27:46.852203781Z",
    }
    msg.update(over)
    return msg


# ---------- parsing ----------


def test_parse_ticker_maps_product_and_derives_spread_and_change():
    rp = parse_ticker(ticker(), PRODUCTS)
    assert rp.symbol == "BTCUSD" and rp.product_id == "BTC-USD"
    assert rp.price == Decimal("82364")
    assert rp.bid == Decimal("82363.99") and rp.ask == Decimal("82364.00")
    assert rp.spread == Decimal("0.01")
    assert rp.change_24h == Decimal("82364") - Decimal("83464.09")
    assert round(rp.change_24h_pct, 3) == Decimal("-1.318")  # (82364-83464.09)/83464.09
    assert rp.source_time == dt.datetime(2026, 10, 8, 12, 27, 46, 852203, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "subscriptions", "channels": []},  # not a ticker
        ticker(product="DOGE-USD"),  # a product we don't track
        ticker(price="not-a-number"),
        ticker(price="0"),
        ticker(price="NaN"),
        {"type": "ticker"},  # nothing in it
    ],
)
def test_parse_ticker_rejects_anything_unusable(bad):
    assert parse_ticker(bad, PRODUCTS) is None


def test_parse_ticker_survives_missing_optional_fields():
    rp = parse_ticker({"type": "ticker", "product_id": "ETH-USD", "price": "2531.88"}, PRODUCTS)
    assert rp.symbol == "ETHUSD"
    assert rp.bid is None and rp.spread is None and rp.change_24h_pct is None and rp.source_time is None


# ---------- the feed: state, coalescing, status ----------


class _Capture(ConnectionManager):
    def __init__(self):
        super().__init__()
        self.sent: list[tuple] = []

    async def broadcast_symbol(self, symbol, type_, payload):
        self.sent.append(("symbol", symbol, type_, payload))

    async def broadcast_all(self, type_, payload):
        self.sent.append(("all", type_, payload))


def _feed(connected=True):
    cap = _Capture()
    feed = CoinbaseFeed(cap)
    feed._products = dict(PRODUCTS)
    feed._connected = connected
    return feed, cap


@pytest.mark.asyncio(loop_scope="session")
async def test_many_ticks_coalesce_into_one_push_per_symbol():
    feed, cap = _feed()
    for p in ("82360", "82361", "82362"):
        feed.ingest(ticker(price=p))
    feed.ingest(ticker("ETH-USD", "2531.88"))

    await feed.flush()
    pushes = [m for m in cap.sent if m[0] == "symbol"]
    assert [(m[1], m[2]) for m in pushes] == [("BTCUSD", "ref_price"), ("ETHUSD", "ref_price")]
    assert pushes[0][3]["price"] == "82362"  # the latest of the three, not all three
    assert pushes[0][3]["symbol"] == "BTCUSD"
    json.dumps(pushes[0][3])  # must be JSON-safe (Decimals and datetimes serialized)

    cap.sent.clear()
    await feed.flush()
    assert [m for m in cap.sent if m[0] == "symbol"] == []  # nothing new, nothing sent


@pytest.mark.asyncio(loop_scope="session")
async def test_status_transitions_are_broadcast_once_each():
    feed, cap = _feed(connected=False)
    await feed.flush()
    assert cap.sent == []  # DOWN to DOWN is not news

    feed._connected = True
    feed.ingest(ticker())
    await feed.flush()
    assert ("all", "ref_status", {"status": "LIVE"}) in cap.sent

    cap.sent.clear()
    await feed.flush()
    assert [m for m in cap.sent if m[0] == "all"] == []  # unchanged

    feed._connected = False
    await feed.flush()
    assert cap.sent == [("all", "ref_status", {"status": "DOWN"})]


def test_status_goes_stale_when_ticks_stop(monkeypatch):
    feed, _ = _feed()
    feed.ingest(ticker())
    assert feed.status() == "LIVE"
    feed._last_message -= settings.coinbase_stale_after_seconds + 1
    assert feed.status() == "STALE"
    feed._connected = False
    assert feed.status() == "DOWN"


def test_connected_but_no_ticks_yet_is_stale_not_live():
    feed, _ = _feed()
    assert feed.status() == "STALE"


def test_error_message_does_not_break_the_feed():
    feed, _ = _feed()
    feed.ingest({"type": "error", "message": "Failed to subscribe", "reason": "bad product"})
    feed.ingest(ticker())
    assert feed.snapshot().prices[0].symbol == "BTCUSD"


# ---------- REST ----------


@pytest.mark.asyncio(loop_scope="session")
async def test_refprices_requires_login_and_returns_the_latest(client, seeded_accounts):
    assert (await client.get("/refprices")).status_code == 401

    headers = auth_headers(await login(client, "alice"))
    empty = (await client.get("/refprices", headers=headers)).json()
    assert empty["prices"] == [] and empty["status"] == "DOWN"  # disabled in tests: nothing, honestly reported

    feed = client._transport.app.state.coinbase
    feed._connected = True
    feed._products = dict(PRODUCTS)
    feed.ingest(ticker())
    feed.ingest(ticker("ETH-USD", "2531.88"))

    body = (await client.get("/refprices", headers=headers)).json()
    assert body["status"] == "LIVE" and body["source"] == "coinbase"
    assert [p["symbol"] for p in body["prices"]] == ["BTCUSD", "ETHUSD"]
    assert Decimal(body["prices"][0]["price"]) == 82364


@pytest.mark.asyncio(loop_scope="session")
async def test_live_prices_never_change_our_own_marks(client, seeded_accounts):
    """The reference feed is display-only: risk marks still come from our own book."""
    feed = client._transport.app.state.coinbase
    feed._connected = True
    feed._products = dict(PRODUCTS)
    feed.ingest(ticker(price="82364"))

    overview = (await client.get("/risk/overview", headers=auth_headers(await login(client, "market_maker")))).json()
    assert overview["symbols"][0]["mark_source"] == "NONE"  # empty book + no trades, whatever Coinbase says
