from fastapi import APIRouter, Depends

from app.api.deps import get_current_account
from app.api.schemas import AccountResponse
from app.db.models import Account
from app.risk.access import is_risk_viewer

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/me", response_model=AccountResponse)
async def get_me(account: Account = Depends(get_current_account)) -> AccountResponse:
    return AccountResponse(
        account_id=account.id,
        username=account.username,
        display_name=account.display_name,
        usd_balance=account.usd_balance,
        reserved_usd=account.reserved_usd,
        can_view_risk=is_risk_viewer(account.username),
    )
