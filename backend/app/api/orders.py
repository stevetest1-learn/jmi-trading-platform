from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_account, get_engine
from app.api.schemas import FillSummary, OrderCreateRequest, OrderResponse
from app.db.base import get_db
from app.db.models import Account
from app.db.models import Order as OrderRow
from app.engine.engine import MatchingEngine
from app.engine.types import OrderType, Side

router = APIRouter(prefix="/orders", tags=["orders"])

OPEN_STATUSES = ("NEW", "PARTIALLY_FILLED")


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def submit_order(
    body: OrderCreateRequest,
    account: Account = Depends(get_current_account),
    engine: MatchingEngine = Depends(get_engine),
) -> OrderResponse:
    try:
        side = Side(body.side.upper())
        order_type = OrderType(body.order_type.upper())
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid side or order_type") from exc

    result = await engine.submit_order(
        account_id=account.id,
        symbol=body.symbol.upper(),
        side=side,
        order_type=order_type,
        qty=body.qty,
        price=body.price,
        source="GUI",
    )

    order = result.order
    return OrderResponse(
        order_id=order.order_id,
        symbol=order.symbol,
        side=order.side.value,
        order_type=order.order_type.value,
        qty=order.qty,
        price=order.price,
        leaves_qty=order.leaves_qty,
        status=order.status.value,
        reject_reason=result.reject_reason,
        fills=[
            FillSummary(trade_id=trade_id, price=fill.price, qty=fill.qty)
            for fill, trade_id in zip(result.fills, result.trade_ids, strict=True)
        ],
    )


@router.delete("/{order_id}", response_model=OrderResponse)
async def cancel_order(
    order_id: int,
    account: Account = Depends(get_current_account),
    engine: MatchingEngine = Depends(get_engine),
    db: AsyncSession = Depends(get_db),
) -> OrderResponse:
    ok = await engine.cancel_order(account_id=account.id, order_id=order_id)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order cannot be canceled")
    row = await db.get(OrderRow, order_id)
    return OrderResponse(
        order_id=row.id, symbol=row.symbol, side=row.side, order_type=row.order_type,
        qty=row.qty, price=row.price, leaves_qty=row.leaves_qty, status=row.status,
        reject_reason=row.reject_reason,
    )


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    status_filter: str | None = None,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> list[OrderResponse]:
    stmt = select(OrderRow).where(OrderRow.account_id == account.id)
    if status_filter == "open":
        stmt = stmt.where(OrderRow.status.in_(OPEN_STATUSES))
    stmt = stmt.order_by(OrderRow.id.desc()).limit(200)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        OrderResponse(
            order_id=r.id, symbol=r.symbol, side=r.side, order_type=r.order_type,
            qty=r.qty, price=r.price, leaves_qty=r.leaves_qty, status=r.status,
            reject_reason=r.reject_reason,
        )
        for r in rows
    ]
