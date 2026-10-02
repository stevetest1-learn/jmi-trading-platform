from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, auth, blotter, health, marketdata, orders, positions, risk, symbols
from app.config import settings
from app.db.base import async_session_factory
from app.engine.engine import MatchingEngine
from app.ws.manager import ConnectionManager
from app.ws.router import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    ws_manager = ConnectionManager()
    engine = MatchingEngine(async_session_factory, ws_manager)
    await engine.bootstrap()
    app.state.ws_manager = ws_manager
    app.state.engine = engine
    yield


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
app.include_router(ws_router)
