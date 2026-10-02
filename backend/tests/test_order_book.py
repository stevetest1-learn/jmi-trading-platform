import datetime as dt
from decimal import Decimal

from app.engine.order_book import OrderBook
from app.engine.types import BookOrder, OrdStatus, OrderType, Side


def make_order(order_id, account_id, side, price, qty, order_type=OrderType.LIMIT) -> BookOrder:
    return BookOrder(
        order_id=order_id, account_id=account_id, symbol="BTCUSD", side=side, order_type=order_type,
        price=price, qty=qty, leaves_qty=qty, status=OrdStatus.NEW, seq=order_id,
        ts_created=dt.datetime.now(dt.UTC),
    )


def test_resting_limit_order_with_no_cross():
    book = OrderBook("BTCUSD")
    order = make_order(1, 1, Side.BUY, Decimal("50000"), Decimal("1"))
    fills = book.submit_limit(order)
    assert fills == []
    assert order.status == OrdStatus.NEW
    assert book.best_bid() == Decimal("50000")
    assert book.best_ask() is None


def test_full_cross_fills_both_sides():
    book = OrderBook("BTCUSD")
    resting = make_order(1, 100, Side.BUY, Decimal("50000"), Decimal("1"))
    book.submit_limit(resting)

    incoming = make_order(2, 200, Side.SELL, Decimal("50000"), Decimal("1"))
    fills = book.submit_limit(incoming)

    assert len(fills) == 1
    fill = fills[0]
    assert fill.price == Decimal("50000")
    assert fill.qty == Decimal("1")
    assert fill.buy_account_id == 100
    assert fill.sell_account_id == 200
    assert incoming.status == OrdStatus.FILLED
    assert resting.status == OrdStatus.FILLED
    assert book.best_bid() is None


def test_partial_fill_leaves_remainder_resting():
    book = OrderBook("BTCUSD")
    resting = make_order(1, 100, Side.BUY, Decimal("50000"), Decimal("2"))
    book.submit_limit(resting)

    incoming = make_order(2, 200, Side.SELL, Decimal("50000"), Decimal("0.5"))
    fills = book.submit_limit(incoming)

    assert len(fills) == 1
    assert fills[0].qty == Decimal("0.5")
    assert incoming.status == OrdStatus.FILLED
    assert resting.status == OrdStatus.PARTIALLY_FILLED
    assert resting.leaves_qty == Decimal("1.5")
    assert book.best_bid() == Decimal("50000")


def test_price_time_priority_fifo_within_level():
    book = OrderBook("BTCUSD")
    first = make_order(1, 100, Side.BUY, Decimal("50000"), Decimal("1"))
    second = make_order(2, 101, Side.BUY, Decimal("50000"), Decimal("1"))
    book.submit_limit(first)
    book.submit_limit(second)

    incoming = make_order(3, 200, Side.SELL, Decimal("50000"), Decimal("1"))
    fills = book.submit_limit(incoming)

    assert fills[0].buy_order_id == first.order_id  # first-in-time is matched first
    assert first.status == OrdStatus.FILLED
    assert second.status == OrdStatus.NEW  # untouched, still resting


def test_better_price_level_matched_first():
    book = OrderBook("BTCUSD")
    low = make_order(1, 100, Side.BUY, Decimal("49000"), Decimal("1"))
    high = make_order(2, 101, Side.BUY, Decimal("50000"), Decimal("1"))
    book.submit_limit(low)
    book.submit_limit(high)

    incoming = make_order(3, 200, Side.SELL, Decimal("48000"), Decimal("1"))
    fills = book.submit_limit(incoming)

    assert fills[0].price == Decimal("50000")  # best (highest) bid trades first
    assert fills[0].buy_order_id == high.order_id


def test_market_order_sweeps_multiple_levels():
    book = OrderBook("BTCUSD")
    book.submit_limit(make_order(1, 100, Side.SELL, Decimal("50000"), Decimal("1")))
    book.submit_limit(make_order(2, 101, Side.SELL, Decimal("50100"), Decimal("1")))

    incoming = make_order(3, 200, Side.BUY, None, Decimal("1.5"), order_type=OrderType.MARKET)
    fills = book.submit_market(incoming)

    assert len(fills) == 2
    assert fills[0].price == Decimal("50000")
    assert fills[0].qty == Decimal("1")
    assert fills[1].price == Decimal("50100")
    assert fills[1].qty == Decimal("0.5")
    assert incoming.status == OrdStatus.FILLED


def test_market_order_remainder_canceled_when_book_exhausted():
    book = OrderBook("BTCUSD")
    book.submit_limit(make_order(1, 100, Side.SELL, Decimal("50000"), Decimal("1")))

    incoming = make_order(2, 200, Side.BUY, None, Decimal("5"), order_type=OrderType.MARKET)
    fills = book.submit_market(incoming)

    assert len(fills) == 1
    assert fills[0].qty == Decimal("1")
    assert incoming.status == OrdStatus.CANCELED
    assert incoming.leaves_qty == Decimal(0)


def test_cancel_removes_resting_order():
    book = OrderBook("BTCUSD")
    order = make_order(1, 100, Side.BUY, Decimal("50000"), Decimal("1"))
    book.submit_limit(order)

    cancelled = book.cancel(1)
    assert cancelled is not None
    assert cancelled.status == OrdStatus.CANCELED
    assert book.best_bid() is None
    assert book.cancel(1) is None  # already gone


def test_depth_snapshot_aggregates_qty_per_level():
    book = OrderBook("BTCUSD")
    book.submit_limit(make_order(1, 100, Side.BUY, Decimal("50000"), Decimal("1")))
    book.submit_limit(make_order(2, 101, Side.BUY, Decimal("50000"), Decimal("2")))
    book.submit_limit(make_order(3, 102, Side.SELL, Decimal("50100"), Decimal("3")))

    snapshot = book.depth_snapshot(10)
    assert snapshot["bids"] == [{"price": "50000", "qty": "3"}]
    assert snapshot["asks"] == [{"price": "50100", "qty": "3"}]
