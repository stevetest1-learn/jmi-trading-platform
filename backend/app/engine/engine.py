import asyncio
import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Account, DailySettlement  # noqa: F401 -- DailySettlement kept for import symmetry with settlement module
from app.db.models import Order as OrderRow
from app.db.models import Position as PositionRow
from app.db.models import Symbol
from app.db.models import Trade as TradeRow
from app.engine.order_book import OrderBook
from app.engine.types import BookOrder, Fill, OrdStatus, OrderType, Side, SubmitResult
from app.positions.position_manager import FillEffect, PositionState, apply_fill, unrealized_pnl
from app.reporting.trade_log import log_trade_rows
from app.ws.manager import ConnectionManager


def _to_state(row: PositionRow) -> PositionState:
    return PositionState(
        net_qty=row.net_qty,
        reserved_qty=row.reserved_qty,
        avg_cost=row.avg_cost,
        realized_pnl_today=row.realized_pnl_today,
        realized_pnl_total=row.realized_pnl_total,
    )


def _write_state(row: PositionRow, state: PositionState) -> None:
    row.net_qty = state.net_qty
    row.avg_cost = state.avg_cost
    row.realized_pnl_today = state.realized_pnl_today
    row.realized_pnl_total = state.realized_pnl_total


class MatchingEngine:
    """Single-writer, in-memory order book(s) + durable Postgres state.

    Every mutating call (submit/cancel) is serialized through one asyncio
    lock and one DB transaction, so the in-memory book and Postgres can
    never disagree. This is why the backend service must run with a single
    replica (desired_count = 1) -- see the plan's Concurrency note.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], ws_manager: ConnectionManager) -> None:
        self._session_factory = session_factory
        self._ws = ws_manager
        self._books: dict[str, OrderBook] = {}
        self._lock = asyncio.Lock()
        self._seq_counter = 0

    def book(self, symbol: str) -> OrderBook:
        if symbol not in self._books:
            self._books[symbol] = OrderBook(symbol)
        return self._books[symbol]

    def _next_seq(self) -> int:
        self._seq_counter += 1
        return self._seq_counter

    async def bootstrap(self) -> None:
        """Rehydrate resting orders from Postgres after a process restart."""
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(OrderRow)
                    .where(OrderRow.status.in_([OrdStatus.NEW.value, OrdStatus.PARTIALLY_FILLED.value]))
                    .order_by(OrderRow.id.asc())
                )
            ).scalars().all()
            for row in rows:
                book_order = BookOrder(
                    order_id=row.id,
                    account_id=row.account_id,
                    symbol=row.symbol,
                    side=Side(row.side),
                    order_type=OrderType(row.order_type),
                    price=row.price,
                    qty=row.qty,
                    leaves_qty=row.leaves_qty,
                    status=OrdStatus(row.status),
                    seq=row.seq,
                    ts_created=row.ts_created,
                )
                self.book(row.symbol)._rest(book_order)  # noqa: SLF001 -- recovery path
                self._seq_counter = max(self._seq_counter, row.seq)

    async def submit_order(
        self,
        *,
        account_id: int,
        symbol: str,
        side: Side,
        order_type: OrderType,
        qty: Decimal,
        price: Decimal | None,
        source: str = "GUI",
    ) -> SubmitResult:
        async with self._lock:
            async with self._session_factory() as session, session.begin():
                result = await self._submit_locked(
                    session,
                    account_id=account_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    qty=qty,
                    price=price,
                    source=source,
                )
            await self._publish_submit(result)
            if result.csv_rows:
                # Only reached after the transaction above has committed, so
                # the CSV can never record a trade that got rolled back.
                # Best-effort: a logging problem here must not break trading.
                try:
                    await asyncio.to_thread(log_trade_rows, result.csv_rows)
                except OSError:
                    pass
            return result

    async def cancel_order(self, *, account_id: int, order_id: int) -> bool:
        async with self._lock:
            symbol: str | None = None
            async with self._session_factory() as session, session.begin():
                order_row = await session.get(OrderRow, order_id, with_for_update=True)
                if order_row is None or order_row.account_id != account_id:
                    return False
                if order_row.status not in (OrdStatus.NEW.value, OrdStatus.PARTIALLY_FILLED.value):
                    return False

                cancelled = self.book(order_row.symbol).cancel(order_id)
                if cancelled is None:
                    return False

                leftover = order_row.leaves_qty
                order_row.status = OrdStatus.CANCELED.value
                order_row.leaves_qty = Decimal(0)

                if order_row.side == Side.BUY.value:
                    account = await session.get(Account, account_id, with_for_update=True)
                    account.reserved_usd -= leftover * order_row.price
                else:
                    position_row = await session.get(PositionRow, (account_id, order_row.symbol), with_for_update=True)
                    position_row.reserved_qty -= leftover
                symbol = order_row.symbol

            await self._ws.send_to_account(account_id, "order_ack", {"order_id": order_id, "status": "CANCELED"})
            if symbol:
                await self._ws.broadcast_symbol(symbol, "book_snapshot", self.book(symbol).depth_snapshot(10))
                await self._ws.broadcast_risk("risk_dirty", {"symbol": symbol})
            return True

    # -- internals ---------------------------------------------------------

    async def _submit_locked(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        symbol: str,
        side: Side,
        order_type: OrderType,
        qty: Decimal,
        price: Decimal | None,
        source: str,
    ) -> SubmitResult:
        symbol_row = await session.get(Symbol, symbol)
        if symbol_row is None or not symbol_row.active:
            return await self._reject(session, account_id, symbol, side, order_type, qty, price, source, "UNKNOWN_SYMBOL")
        if qty <= 0:
            return await self._reject(session, account_id, symbol, side, order_type, qty, price, source, "INVALID_QTY")
        if order_type == OrderType.LIMIT and (price is None or price <= 0):
            return await self._reject(session, account_id, symbol, side, order_type, qty, price, source, "INVALID_PRICE")

        book = self.book(symbol)

        if order_type == OrderType.MARKET:
            opposite_book = book.asks if side == Side.BUY else book.bids
            if not opposite_book:
                return await self._reject(session, account_id, symbol, side, order_type, qty, price, source, "NO_LIQUIDITY")

        account = await session.get(Account, account_id, with_for_update=True)
        position_row = await session.get(PositionRow, (account_id, symbol), with_for_update=True)
        if position_row is None:
            position_row = PositionRow(account_id=account_id, symbol=symbol)
            session.add(position_row)
            await session.flush()

        if side == Side.SELL:
            available_qty = position_row.net_qty - position_row.reserved_qty
            if qty > available_qty:
                return await self._reject(session, account_id, symbol, side, order_type, qty, price, source, "INSUFFICIENT_POSITION")
        else:
            available_usd = account.usd_balance - account.reserved_usd
            estimated_cost = self._estimate_buy_cost(book, order_type, qty, price)
            if estimated_cost > available_usd:
                return await self._reject(session, account_id, symbol, side, order_type, qty, price, source, "INSUFFICIENT_BUYING_POWER")

        order_row = OrderRow(
            account_id=account_id,
            symbol=symbol,
            side=side.value,
            order_type=order_type.value,
            price=price,
            qty=qty,
            leaves_qty=qty,
            status=OrdStatus.NEW.value,
            seq=self._next_seq(),
            source=source,
        )
        session.add(order_row)
        await session.flush()

        book_order = BookOrder(
            order_id=order_row.id,
            account_id=account_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=price,
            qty=qty,
            leaves_qty=qty,
            status=OrdStatus.NEW,
            seq=order_row.seq,
            ts_created=order_row.ts_created or dt.datetime.now(dt.UTC),
        )

        fills = book.submit_limit(book_order) if order_type == OrderType.LIMIT else book.submit_market(book_order)

        order_row.status = book_order.status.value
        order_row.leaves_qty = book_order.leaves_qty

        if book_order.leaves_qty > 0 and book_order.status in (OrdStatus.NEW, OrdStatus.PARTIALLY_FILLED):
            if side == Side.BUY:
                account.reserved_usd += book_order.leaves_qty * price
            else:
                position_row.reserved_qty += book_order.leaves_qty

        trade_ids: list[int] = []
        csv_rows: list[dict] = []
        for fill in fills:
            trade_id, rows = await self._apply_fill(session, fill, order_row)
            trade_ids.append(trade_id)
            csv_rows.extend(rows)

        return SubmitResult(order=book_order, fills=fills, trade_ids=trade_ids, csv_rows=csv_rows)

    def _estimate_buy_cost(self, book: OrderBook, order_type: OrderType, qty: Decimal, price: Decimal | None) -> Decimal:
        if order_type == OrderType.LIMIT:
            return qty * price  # type: ignore[operator]
        remaining = qty
        cost = Decimal(0)
        last_price = Decimal(0)
        for ask_price, level in book.asks.items():
            if remaining <= 0:
                break
            level_qty = sum((o.leaves_qty for o in level), Decimal(0))
            take = min(remaining, level_qty)
            cost += take * ask_price
            remaining -= take
            last_price = ask_price
        if remaining > 0:
            cost += remaining * last_price
        return cost

    async def _apply_fill(self, session: AsyncSession, fill: Fill, incoming_order_row: OrderRow) -> tuple[int, list[dict]]:
        trade_row = TradeRow(
            symbol=fill.symbol,
            buy_order_id=fill.buy_order_id,
            sell_order_id=fill.sell_order_id,
            buy_account_id=fill.buy_account_id,
            sell_account_id=fill.sell_account_id,
            price=fill.price,
            qty=fill.qty,
            aggressor_side=fill.aggressor_side.value,
        )
        session.add(trade_row)
        await session.flush()

        resting_row = await session.get(OrderRow, fill.resting_order_id)
        if resting_row is not None:
            resting_row.leaves_qty = fill.resting_leaves_qty_after
            resting_row.status = fill.resting_status_after.value
            if Side(resting_row.side) == Side.BUY:
                resting_account = await session.get(Account, fill.buy_account_id, with_for_update=True)
                resting_account.reserved_usd -= fill.qty * fill.price
            else:
                resting_position = await session.get(PositionRow, (fill.sell_account_id, fill.symbol), with_for_update=True)
                resting_position.reserved_qty -= fill.qty

        buy_account = await session.get(Account, fill.buy_account_id, with_for_update=True)
        sell_account = await session.get(Account, fill.sell_account_id, with_for_update=True)

        buy_position = await session.get(PositionRow, (fill.buy_account_id, fill.symbol), with_for_update=True)
        if buy_position is None:
            buy_position = PositionRow(account_id=fill.buy_account_id, symbol=fill.symbol)
            session.add(buy_position)
            await session.flush()
        sell_position = await session.get(PositionRow, (fill.sell_account_id, fill.symbol), with_for_update=True)
        if sell_position is None:
            sell_position = PositionRow(account_id=fill.sell_account_id, symbol=fill.symbol)
            session.add(sell_position)
            await session.flush()

        buy_state = _to_state(buy_position)
        buy_effect = apply_fill(buy_state, Side.BUY, fill.qty, fill.price)
        _write_state(buy_position, buy_state)
        buy_account.usd_balance += buy_effect.cash_delta

        sell_state = _to_state(sell_position)
        sell_effect = apply_fill(sell_state, Side.SELL, fill.qty, fill.price)
        _write_state(sell_position, sell_state)
        sell_account.usd_balance += sell_effect.cash_delta

        # incoming_order_row is one side of this fill; resting_row is the
        # other (whichever order was already on the book). Sort them into
        # buy/sell so the CSV can show each side's own order price/type.
        is_incoming_buy = incoming_order_row.side == Side.BUY.value
        buy_order_row = incoming_order_row if is_incoming_buy else resting_row
        sell_order_row = resting_row if is_incoming_buy else incoming_order_row

        csv_rows = [
            self._trade_log_row(trade_row.id, fill, buy_account, "BUY", buy_order_row, buy_state, buy_effect),
            self._trade_log_row(trade_row.id, fill, sell_account, "SELL", sell_order_row, sell_state, sell_effect),
        ]

        return trade_row.id, csv_rows

    @staticmethod
    def _trade_log_row(
        trade_id: int,
        fill: Fill,
        account: Account,
        side: str,
        order_row: OrderRow | None,
        state: PositionState,
        effect: FillEffect,
    ) -> dict:
        return {
            "timestamp": dt.datetime.now(dt.UTC).isoformat(),
            "trade_id": trade_id,
            "symbol": fill.symbol,
            "account": account.username,
            "side": side,
            "order_id": order_row.id if order_row else "",
            "order_type": order_row.order_type if order_row else "",
            "order_price": str(order_row.price) if order_row and order_row.price is not None else "",
            "order_qty": str(order_row.qty) if order_row else "",
            "fill_qty": str(fill.qty),
            "fill_price": str(fill.price),
            "realized_pnl_this_fill": str(effect.realized_pnl),
            "realized_pnl_today_after": str(state.realized_pnl_today),
            "realized_pnl_total_after": str(state.realized_pnl_total),
            "net_qty_after": str(state.net_qty),
            "avg_cost_after": str(state.avg_cost),
        }

    async def _reject(
        self,
        session: AsyncSession,
        account_id: int,
        symbol: str,
        side: Side,
        order_type: OrderType,
        qty: Decimal,
        price: Decimal | None,
        source: str,
        reason: str,
    ) -> SubmitResult:
        order_row = OrderRow(
            account_id=account_id,
            symbol=symbol,
            side=side.value,
            order_type=order_type.value,
            price=price,
            qty=qty,
            leaves_qty=Decimal(0),
            status=OrdStatus.REJECTED.value,
            reject_reason=reason,
            seq=self._next_seq(),
            source=source,
        )
        session.add(order_row)
        await session.flush()
        book_order = BookOrder(
            order_id=order_row.id,
            account_id=account_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=price,
            qty=qty,
            leaves_qty=Decimal(0),
            status=OrdStatus.REJECTED,
            seq=order_row.seq,
            ts_created=order_row.ts_created or dt.datetime.now(dt.UTC),
        )
        return SubmitResult(order=book_order, fills=[], rejected=True, reject_reason=reason)

    async def _position_snapshot(self, account_id: int, symbol: str) -> dict:
        async with self._session_factory() as session:
            position_row = await session.get(PositionRow, (account_id, symbol))
            account = await session.get(Account, account_id)
        net_qty = position_row.net_qty if position_row else Decimal(0)
        avg_cost = position_row.avg_cost if position_row else Decimal(0)
        realized_today = position_row.realized_pnl_today if position_row else Decimal(0)
        mark = self.book(symbol).best_bid()
        state = PositionState(
            net_qty=net_qty, reserved_qty=Decimal(0), avg_cost=avg_cost,
            realized_pnl_today=Decimal(0), realized_pnl_total=Decimal(0),
        )
        unrealized = unrealized_pnl(state, mark)
        return {
            "symbol": symbol,
            "net_qty": str(net_qty),
            "avg_cost": str(avg_cost),
            "realized_pnl_today": str(realized_today),
            "unrealized_pnl": str(unrealized),
            "usd_balance": str(account.usd_balance) if account else None,
        }

    async def _publish_submit(self, result: SubmitResult) -> None:
        order = result.order

        if result.rejected:
            await self._ws.send_to_account(order.account_id, "reject", {
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "order_type": order.order_type.value,
                "qty": str(order.qty),
                "price": str(order.price) if order.price is not None else None,
                "reason": result.reject_reason,
                "status": "REJECTED",
            })
            return

        await self._ws.send_to_account(order.account_id, "order_ack", {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "qty": str(order.qty),
            "price": str(order.price) if order.price is not None else None,
            "status": order.status.value,
            "leaves_qty": str(order.leaves_qty),
        })

        accounts_touched: set[int] = set()
        for fill, trade_id in zip(result.fills, result.trade_ids, strict=True):
            for acct_id, ord_id in (
                (fill.buy_account_id, fill.buy_order_id),
                (fill.sell_account_id, fill.sell_order_id),
            ):
                accounts_touched.add(acct_id)
                await self._ws.send_to_account(acct_id, "execution", {
                    "order_id": ord_id,
                    "trade_id": trade_id,
                    "symbol": fill.symbol,
                    "side": "BUY" if acct_id == fill.buy_account_id else "SELL",
                    "qty": str(fill.qty),
                    "price": str(fill.price),
                    "status": "FILL",
                })

            # The order that was already resting on the book (as opposed to
            # the incoming order acked above) belongs to a different account
            # and would otherwise never hear that it just got (partially)
            # filled -- tell its own account so its Open Orders panel updates.
            resting_account_id = fill.sell_account_id if fill.aggressor_side.value == "BUY" else fill.buy_account_id
            await self._ws.send_to_account(resting_account_id, "order_ack", {
                "order_id": fill.resting_order_id,
                "symbol": fill.symbol,
                "status": fill.resting_status_after.value,
                "leaves_qty": str(fill.resting_leaves_qty_after),
            })

        if result.fills:
            await self._ws.broadcast_symbol(order.symbol, "book_snapshot", self.book(order.symbol).depth_snapshot(10))

        for acct_id in accounts_touched:
            await self._ws.send_to_account(acct_id, "position_update", await self._position_snapshot(acct_id, order.symbol))

        # A resting order moves reserved cash and the book mid; fills move
        # positions and P&L. Either way risk viewers should refetch.
        await self._ws.broadcast_risk("risk_dirty", {"symbol": order.symbol})
