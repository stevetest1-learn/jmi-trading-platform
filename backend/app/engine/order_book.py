from collections import deque
from decimal import Decimal

from sortedcontainers import SortedDict

from app.engine.types import BookOrder, Fill, OrdStatus, Side


class OrderBook:
    """Single-symbol price/time-priority limit order book.

    Price priority comes from the SortedDict's key ordering; time priority
    within a price level comes from FIFO deque order (append on rest,
    popleft on fill) — no separate timestamp comparison is needed at match
    time.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.bids: SortedDict[Decimal, deque[BookOrder]] = SortedDict()
        self.asks: SortedDict[Decimal, deque[BookOrder]] = SortedDict()
        self.orders_by_id: dict[int, BookOrder] = {}

    def best_bid(self) -> Decimal | None:
        return self.bids.peekitem(-1)[0] if self.bids else None

    def best_ask(self) -> Decimal | None:
        return self.asks.peekitem(0)[0] if self.asks else None

    def submit_limit(self, incoming: BookOrder) -> list[Fill]:
        fills = self._sweep(incoming, require_cross=True)
        if incoming.leaves_qty > 0:
            incoming.status = OrdStatus.PARTIALLY_FILLED if fills else OrdStatus.NEW
            self._rest(incoming)
        else:
            incoming.status = OrdStatus.FILLED
        return fills

    def submit_market(self, incoming: BookOrder) -> list[Fill]:
        fills = self._sweep(incoming, require_cross=False)
        if incoming.leaves_qty == 0:
            incoming.status = OrdStatus.FILLED
        else:
            # Book exhausted before the order could be fully filled. Market
            # orders never rest — the remainder is dropped, not queued.
            incoming.status = OrdStatus.CANCELED
            incoming.leaves_qty = Decimal(0)
        return fills

    def cancel(self, order_id: int) -> BookOrder | None:
        order = self.orders_by_id.get(order_id)
        if order is None:
            return None
        book = self.bids if order.side == Side.BUY else self.asks
        level = book.get(order.price)
        if level is not None:
            try:
                level.remove(order)
            except ValueError:
                pass
            if not level:
                del book[order.price]
        order.status = OrdStatus.CANCELED
        order.leaves_qty = Decimal(0)
        del self.orders_by_id[order_id]
        return order

    def depth_snapshot(self, levels: int) -> dict:
        """{price, qty} objects (not bare tuples) -- this shape is sent
        as-is over both the REST marketdata endpoint and the WS
        book_snapshot push, so it must match what the frontend expects."""
        bid_prices = list(self.bids.keys())[-levels:][::-1]
        ask_prices = list(self.asks.keys())[:levels]
        return {
            "bids": [
                {"price": str(p), "qty": str(sum((o.leaves_qty for o in self.bids[p]), Decimal(0)))}
                for p in bid_prices
            ],
            "asks": [
                {"price": str(p), "qty": str(sum((o.leaves_qty for o in self.asks[p]), Decimal(0)))}
                for p in ask_prices
            ],
        }

    # -- internals ---------------------------------------------------------

    def _sweep(self, incoming: BookOrder, *, require_cross: bool) -> list[Fill]:
        fills: list[Fill] = []
        opposite = self.asks if incoming.side == Side.BUY else self.bids
        while incoming.leaves_qty > 0 and opposite:
            best_price = opposite.peekitem(0 if incoming.side == Side.BUY else -1)[0]
            if require_cross and not self._crosses(incoming.side, incoming.price, best_price):
                break
            fills.append(self._trade_one(incoming, opposite, best_price))
        return fills

    @staticmethod
    def _crosses(side: Side, limit_price: Decimal | None, best_price: Decimal) -> bool:
        if limit_price is None:
            return True
        return limit_price >= best_price if side == Side.BUY else limit_price <= best_price

    def _trade_one(self, incoming: BookOrder, opposite: SortedDict, best_price: Decimal) -> Fill:
        level = opposite[best_price]
        resting = level[0]
        trade_qty = min(incoming.leaves_qty, resting.leaves_qty)

        incoming.leaves_qty -= trade_qty
        resting.leaves_qty -= trade_qty

        if resting.leaves_qty == 0:
            level.popleft()
            resting.status = OrdStatus.FILLED
            self.orders_by_id.pop(resting.order_id, None)
            if not level:
                del opposite[best_price]
        else:
            resting.status = OrdStatus.PARTIALLY_FILLED

        buy_order, sell_order = (incoming, resting) if incoming.side == Side.BUY else (resting, incoming)
        return Fill(
            buy_order_id=buy_order.order_id,
            sell_order_id=sell_order.order_id,
            buy_account_id=buy_order.account_id,
            sell_account_id=sell_order.account_id,
            symbol=self.symbol,
            price=best_price,
            qty=trade_qty,
            aggressor_side=incoming.side,
            resting_order_id=resting.order_id,
            resting_leaves_qty_after=resting.leaves_qty,
            resting_status_after=resting.status,
        )

    def _rest(self, order: BookOrder) -> None:
        book = self.bids if order.side == Side.BUY else self.asks
        level = book.setdefault(order.price, deque())
        level.append(order)
        self.orders_by_id[order.order_id] = order
