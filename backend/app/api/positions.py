from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_account, get_engine
from app.api.schemas import PositionResponse
from app.db.base import get_db
from app.db.models import Account
from app.db.models import Position as PositionRow
from app.engine.engine import MatchingEngine
from app.positions.position_manager import PositionState, unrealized_pnl

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", response_model=list[PositionResponse])
async def list_positions(
    account: Account = Depends(get_current_account),
    engine: MatchingEngine = Depends(get_engine),
    db: AsyncSession = Depends(get_db),
) -> list[PositionResponse]:
    rows = (await db.execute(select(PositionRow).where(PositionRow.account_id == account.id))).scalars().all()
    out = []
    for row in rows:
        if row.net_qty == 0 and row.realized_pnl_total == 0:
            continue
        mark = engine.book(row.symbol).best_bid()
        state = PositionState(
            net_qty=row.net_qty, reserved_qty=row.reserved_qty, avg_cost=row.avg_cost,
            realized_pnl_today=row.realized_pnl_today, realized_pnl_total=row.realized_pnl_total,
        )
        out.append(
            PositionResponse(
                symbol=row.symbol,
                net_qty=row.net_qty,
                reserved_qty=row.reserved_qty,
                avg_cost=row.avg_cost,
                realized_pnl_today=row.realized_pnl_today,
                realized_pnl_total=row.realized_pnl_total,
                unrealized_pnl=unrealized_pnl(state, mark) if mark is not None else Decimal(0),
            )
        )
    return out
