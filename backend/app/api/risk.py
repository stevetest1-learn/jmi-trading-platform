from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_engine, require_risk_viewer
from app.db.base import get_db
from app.db.models import Account
from app.engine.engine import MatchingEngine
from app.risk.models import RiskOverview
from app.risk.overview import load_overview

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/overview", response_model=RiskOverview)
async def risk_overview(
    _viewer: Account = Depends(require_risk_viewer),
    engine: MatchingEngine = Depends(get_engine),
    db: AsyncSession = Depends(get_db),
) -> RiskOverview:
    """Every account's positions, platform-wide exposure by symbol, P&L, and
    live limit alerts. Restricted to RISK_VIEWER_USERNAMES."""
    return await load_overview(db, engine)
