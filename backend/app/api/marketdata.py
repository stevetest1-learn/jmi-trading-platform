from fastapi import APIRouter, Depends

from app.api.deps import get_engine
from app.api.schemas import DepthLevel, OrderBookSnapshot
from app.config import settings
from app.engine.engine import MatchingEngine

router = APIRouter(prefix="/marketdata", tags=["marketdata"])


@router.get("/{symbol}", response_model=OrderBookSnapshot)
async def get_order_book(symbol: str, engine: MatchingEngine = Depends(get_engine)) -> OrderBookSnapshot:
    snapshot = engine.book(symbol.upper()).depth_snapshot(settings.book_depth_levels)
    return OrderBookSnapshot(
        symbol=symbol.upper(),
        bids=[DepthLevel(**lvl) for lvl in snapshot["bids"]],
        asks=[DepthLevel(**lvl) for lvl in snapshot["asks"]],
    )
