from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_account
from app.db.models import Account
from app.marketdata.coinbase import RefPriceSnapshot

router = APIRouter(prefix="/refprices", tags=["refprices"])


@router.get("", response_model=RefPriceSnapshot)
async def get_reference_prices(request: Request, _account: Account = Depends(get_current_account)) -> RefPriceSnapshot:
    """Latest Coinbase prices, so a GUI can render immediately on load or
    reconnect instead of waiting for the next push. Reference only."""
    return request.app.state.coinbase.snapshot()
