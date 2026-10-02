from decimal import Decimal

from app.engine.types import Side
from app.positions.position_manager import PositionState, apply_fill, unrealized_pnl


def fresh() -> PositionState:
    return PositionState(
        net_qty=Decimal(0), reserved_qty=Decimal(0), avg_cost=Decimal(0),
        realized_pnl_today=Decimal(0), realized_pnl_total=Decimal(0),
    )


def test_buy_opens_position_with_avg_cost():
    pos = fresh()
    effect = apply_fill(pos, Side.BUY, Decimal("1"), Decimal("50000"))
    assert pos.net_qty == Decimal("1")
    assert pos.avg_cost == Decimal("50000")
    assert effect.realized_pnl == Decimal(0)
    assert effect.cash_delta == Decimal("-50000")


def test_second_buy_updates_weighted_average_cost():
    pos = fresh()
    apply_fill(pos, Side.BUY, Decimal("1"), Decimal("50000"))
    apply_fill(pos, Side.BUY, Decimal("1"), Decimal("60000"))
    assert pos.net_qty == Decimal("2")
    assert pos.avg_cost == Decimal("55000")  # (1*50000 + 1*60000) / 2


def test_sell_realizes_pnl_against_avg_cost_unchanged():
    pos = fresh()
    apply_fill(pos, Side.BUY, Decimal("2"), Decimal("50000"))
    effect = apply_fill(pos, Side.SELL, Decimal("1"), Decimal("55000"))
    assert effect.realized_pnl == Decimal("5000")  # 1 * (55000 - 50000)
    assert pos.net_qty == Decimal("1")
    assert pos.avg_cost == Decimal("50000")  # unchanged by a partial sell
    assert pos.realized_pnl_today == Decimal("5000")
    assert effect.cash_delta == Decimal("55000")


def test_full_close_resets_avg_cost_to_zero():
    pos = fresh()
    apply_fill(pos, Side.BUY, Decimal("1"), Decimal("50000"))
    apply_fill(pos, Side.SELL, Decimal("1"), Decimal("45000"))
    assert pos.net_qty == Decimal(0)
    assert pos.avg_cost == Decimal(0)
    assert pos.realized_pnl_today == Decimal("-5000")


def test_realized_pnl_today_accumulates_across_fills():
    pos = fresh()
    apply_fill(pos, Side.BUY, Decimal("2"), Decimal("50000"))
    apply_fill(pos, Side.SELL, Decimal("1"), Decimal("52000"))
    apply_fill(pos, Side.SELL, Decimal("1"), Decimal("48000"))
    assert pos.realized_pnl_today == Decimal("2000") + Decimal("-2000")
    assert pos.realized_pnl_today == Decimal("0")
    assert pos.realized_pnl_total == Decimal("0")


def test_unrealized_pnl_marks_against_given_price():
    pos = fresh()
    apply_fill(pos, Side.BUY, Decimal("2"), Decimal("50000"))
    assert unrealized_pnl(pos, Decimal("51000")) == Decimal("2000")  # 2 * (51000-50000)
    assert unrealized_pnl(pos, None) == Decimal(0)


def test_unrealized_pnl_zero_when_flat():
    pos = fresh()
    assert unrealized_pnl(pos, Decimal("51000")) == Decimal(0)
