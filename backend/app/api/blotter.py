from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_account
from app.api.schemas import BlotterRow
from app.db.base import get_db
from app.db.models import Account
from app.db.models import Order as OrderRow
from app.db.models import Trade as TradeRow

router = APIRouter(prefix="/blotter", tags=["blotter"])


@router.get("", response_model=list[BlotterRow])
async def get_blotter(
    limit: int = 100,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> list[BlotterRow]:
    """Server-side union of fills-involving-me and rejects-by-me, sorted by
    time — a dedicated endpoint so the bottom panel has one clean, sortable
    data source instead of merging two REST calls in the browser."""
    trades = (
        await db.execute(
            select(TradeRow)
            .where(or_(TradeRow.buy_account_id == account.id, TradeRow.sell_account_id == account.id))
            .order_by(TradeRow.ts.desc())
            .limit(limit)
        )
    ).scalars().all()

    rejects = (
        await db.execute(
            select(OrderRow)
            .where(OrderRow.account_id == account.id, OrderRow.status == "REJECTED")
            .order_by(OrderRow.ts_created.desc())
            .limit(limit)
        )
    ).scalars().all()

    rows: list[BlotterRow] = []
    for t in trades:
        is_buy = t.buy_account_id == account.id
        rows.append(
            BlotterRow(
                order_id=t.buy_order_id if is_buy else t.sell_order_id,
                trade_id=t.id,
                symbol=t.symbol,
                side="BUY" if is_buy else "SELL",
                qty=t.qty,
                price=t.price,
                ts=t.ts,
                status="FILL",
            )
        )
    for r in rejects:
        rows.append(
            BlotterRow(
                order_id=r.id,
                trade_id=None,
                symbol=r.symbol,
                side=r.side,
                qty=r.qty,
                price=r.price,
                ts=r.ts_created,
                status="REJECT",
                reject_reason=r.reject_reason,
            )
        )

    rows.sort(key=lambda r: r.ts, reverse=True)
    return rows[:limit]
