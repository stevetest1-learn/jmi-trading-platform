import os
import tempfile
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://jmi:jmi_dev_password@localhost:5432/jmi_trading_test"
)
os.environ.setdefault("JWT_SECRET", "test-secret")
# Isolate the trade-log CSV to a throwaway directory for the whole test run,
# so `pytest` never writes synthetic test trades into the real trade_logs/
# at the repo root. Individual tests (test_trade_log.py) can still override
# this per-test via monkeypatch to inspect their own isolated output.
os.environ.setdefault("TRADE_LOG_DIR", tempfile.mkdtemp(prefix="jmi-trade-logs-test-"))

from app.auth.security import hash_password  # noqa: E402
from app.db.base import Base, async_session_factory, engine  # noqa: E402
from app.db.models import Account, Position, Symbol  # noqa: E402
from app.main import app  # noqa: E402


# The DB engine (app/db/base.py) is a module-level singleton bound to
# whichever loop is running when its connections are first used, so the
# whole test session must share one event loop -- pytest-asyncio's default
# per-function loop would hand asyncpg connections across loops and crash.
# `loop_scope="session"` on these fixtures (and on the asyncio marks in
# test files) is how pytest-asyncio 0.25+ expresses that.
@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def reset_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_accounts():
    async with async_session_factory() as session, session.begin():
        session.add(Symbol(
            symbol="BTCUSD", display_symbol="BTC/USD", base_asset="BTC", quote_asset="USD",
            price_decimals=2, qty_decimals=6, tick_size=Decimal("0.01"), lot_size=Decimal("0.0001"), active=True,
        ))
        accounts = {}
        for username, usd, starting_btc in [
            ("market_maker", Decimal("5000000"), Decimal("50")),
            ("alice", Decimal("100000"), Decimal(0)),
            ("bob", Decimal("100000"), Decimal(0)),
        ]:
            acct = Account(
                username=username, password_hash=hash_password("demo1234"),
                display_name=username.title(), usd_balance=usd, reserved_usd=Decimal(0),
            )
            session.add(acct)
            await session.flush()
            accounts[username] = acct.id
            if starting_btc > 0:
                session.add(Position(account_id=acct.id, symbol="BTCUSD", net_qty=starting_btc, avg_cost=Decimal(0)))
    return accounts


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac


async def login(client: AsyncClient, username: str, password: str = "demo1234") -> str:
    resp = await client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
