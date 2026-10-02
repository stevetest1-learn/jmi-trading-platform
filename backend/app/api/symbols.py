from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import SymbolResponse
from app.db.base import get_db
from app.db.models import Symbol

router = APIRouter(prefix="/symbols", tags=["symbols"])


@router.get("", response_model=list[SymbolResponse])
async def list_symbols(db: AsyncSession = Depends(get_db)) -> list[SymbolResponse]:
    rows = (await db.execute(select(Symbol).where(Symbol.active.is_(True)).order_by(Symbol.symbol))).scalars().all()
    return [
        SymbolResponse(
            symbol=r.symbol,
            display_symbol=r.display_symbol,
            base_asset=r.base_asset,
            quote_asset=r.quote_asset,
            price_decimals=r.price_decimals,
            qty_decimals=r.qty_decimals,
            tick_size=r.tick_size,
            lot_size=r.lot_size,
            active=r.active,
        )
        for r in rows
    ]
