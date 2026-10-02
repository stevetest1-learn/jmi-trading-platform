from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.db.base import get_db
from app.db.models import Account
from app.engine.engine import MatchingEngine
from app.risk.access import is_risk_viewer
from app.ws.manager import ConnectionManager

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Account:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    account = await db.get(Account, int(payload["sub"]))
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found")
    return account


async def require_risk_viewer(account: Account = Depends(get_current_account)) -> Account:
    """Cross-account data: gated by role on the server, never just hidden in the UI."""
    if not is_risk_viewer(account.username):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to view platform risk")
    return account


def get_engine(request: Request) -> MatchingEngine:
    return request.app.state.engine


def get_ws_manager(request: Request) -> ConnectionManager:
    return request.app.state.ws_manager
