from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import accounts, auth, blotter, health, marketdata, orders, positions, refprices, risk, symbols
from app.config import settings
from app.db.base import async_session_factory
from app.db.models import Symbol
from app.engine.engine import MatchingEngine
from app.marketdata.coinbase import CoinbaseFeed
from app.ws.manager import ConnectionManager
from app.ws.router import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    ws_manager = ConnectionManager()
    engine = MatchingEngine(async_session_factory, ws_manager)
    await engine.bootstrap()
    app.state.ws_manager = ws_manager
    app.state.engine = engine

    # View-only Coinbase prices. The feed object always exists (so /refprices
    # answers with an empty snapshot when disabled); it only connects if enabled.
    coinbase = CoinbaseFeed(ws_manager)
    app.state.coinbase = coinbase
    if settings.coinbase_enabled:
        async with async_session_factory() as session:
            rows = (await session.execute(select(Symbol).where(Symbol.active.is_(True)))).scalars().all()
        coinbase.start({f"{s.base_asset}-{s.quote_asset}": s.symbol for s in rows})

    yield
    await coinbase.stop()


app = FastAPI(title="JMI Crypto Trading GUI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(symbols.router)
app.include_router(orders.router)
app.include_router(positions.router)
app.include_router(blotter.router)
app.include_router(marketdata.router)
app.include_router(risk.router)
app.include_router(refprices.router)
app.include_router(ws_router)
