from dataclasses import dataclass
from decimal import Decimal

from app.engine.types import Side


@dataclass
class PositionState:
    net_qty: Decimal
    reserved_qty: Decimal
    avg_cost: Decimal
    realized_pnl_today: Decimal
    realized_pnl_total: Decimal


@dataclass
class FillEffect:
    realized_pnl: Decimal
    cash_delta: Decimal  # +cash into the account, -cash out of the account


def apply_fill(position: PositionState, side: Side, fill_qty: Decimal, fill_price: Decimal) -> FillEffect:
    """Mutates `position` in place per a single fill and returns the P&L/cash effect.

    No-short-selling means net_qty is always >= 0, so a SELL can only ever
    reduce or fully close a position — it never flips to short. That keeps
    the weighted-average-cost bookkeeping to two simple cases.
    """
    if side == Side.BUY:
        new_qty = position.net_qty + fill_qty
        position.avg_cost = (
            (position.net_qty * position.avg_cost + fill_qty * fill_price) / new_qty
            if new_qty > 0
            else Decimal(0)
        )
        position.net_qty = new_qty
        return FillEffect(realized_pnl=Decimal(0), cash_delta=-(fill_qty * fill_price))

    # SELL: realize P&L against the *current* avg_cost; avg_cost of the
    # remaining position is unchanged by selling a slice of it.
    realized = fill_qty * (fill_price - position.avg_cost)
    position.net_qty -= fill_qty
    position.realized_pnl_today += realized
    position.realized_pnl_total += realized
    if position.net_qty == 0:
        position.avg_cost = Decimal(0)
    return FillEffect(realized_pnl=realized, cash_delta=fill_qty * fill_price)


def unrealized_pnl(position: PositionState, mark_price: Decimal | None) -> Decimal:
    """Mark-to-market against `mark_price` (recommended: current best bid — the
    conservative, actually-liquidatable value of a long position)."""
    if position.net_qty == 0 or mark_price is None:
        return Decimal(0)
    return position.net_qty * (mark_price - position.avg_cost)
