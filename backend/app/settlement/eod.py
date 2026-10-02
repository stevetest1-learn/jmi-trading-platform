import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Account, DailySettlement, Position, Trade


async def settle_day(session: AsyncSession, settlement_date: dt.date) -> dict:
    """Snapshot each account/symbol's realized P&L for `settlement_date` into
    daily_settlements, reset the daily accumulator, and mark the day's
    trades SETTLED. Idempotent: re-running for a date that already has
    snapshots is a no-op (T+0 cash/position movement already happened in
    real time at fill; this is the formal EOD finalization/audit marker).
    """
    already = (
        await session.execute(
            select(func.count())
            .select_from(DailySettlement)
            .where(DailySettlement.settlement_date == settlement_date)
        )
    ).scalar_one()
    if already > 0:
        return {"settlement_date": str(settlement_date), "skipped": True, "reason": "already settled"}

    positions = (await session.execute(select(Position))).scalars().all()
    accounts_by_id = {a.id: a for a in (await session.execute(select(Account))).scalars().all()}

    snapshots = 0
    for position in positions:
        if position.net_qty == 0 and position.realized_pnl_today == 0 and position.realized_pnl_total == 0:
            continue

        account = accounts_by_id.get(position.account_id)
        trades_count = (
            await session.execute(
                select(func.count())
                .select_from(Trade)
                .where(
                    Trade.settlement_status == "PENDING",
                    func.date(Trade.ts) <= settlement_date,
                    Trade.symbol == position.symbol,
                    (Trade.buy_account_id == position.account_id) | (Trade.sell_account_id == position.account_id),
                )
            )
        ).scalar_one()

        session.add(
            DailySettlement(
                settlement_date=settlement_date,
                account_id=position.account_id,
                symbol=position.symbol,
                realized_pnl=position.realized_pnl_today,
                ending_net_qty=position.net_qty,
                ending_avg_cost=position.avg_cost,
                ending_usd_balance=account.usd_balance if account else Decimal(0),
                trades_settled_count=trades_count,
            )
        )
        position.realized_pnl_today = Decimal(0)
        snapshots += 1

    result = await session.execute(
        update(Trade)
        .where(Trade.settlement_status == "PENDING", func.date(Trade.ts) <= settlement_date)
        .values(settlement_status="SETTLED", settled_at=func.now())
    )

    return {
        "settlement_date": str(settlement_date),
        "skipped": False,
        "accounts_snapshotted": snapshots,
        "trades_settled": result.rowcount,
    }
