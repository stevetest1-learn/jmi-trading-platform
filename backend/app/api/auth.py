from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import LoginRequest, LoginResponse
from app.auth.security import create_access_token, verify_password
from app.db.base import get_db
from app.db.models import Account

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> LoginResponse:
    account = (await db.execute(select(Account).where(Account.username == body.username))).scalar_one_or_none()
    if account is None or not verify_password(body.password, account.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    token = create_access_token(account.id, account.username)
    return LoginResponse(access_token=token, account_id=account.id, username=account.username)
