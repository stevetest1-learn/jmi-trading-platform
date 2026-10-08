"""Read-only Coinbase reference prices.

One backend connection to Coinbase's public `ticker` channel (no API key,
nothing is ever sent to Coinbase except a subscribe message) is fanned out to
every GUI over our own WebSocket. This is for *viewing* real market prices
only: it never touches the matching engine, the marks used for exposure/P&L,
or any order. Product ids follow "<base>-<quote>" (BTC-USD), derived from the
symbols table, so a new symbol that Coinbase lists needs no code change.

Coinbase's market-data terms govern redistribution of this data; check them
before showing it to anyone beyond personal/internal use.
"""

import asyncio
import contextlib
import datetime as dt
import json
import logging
import time
from decimal import Decimal, InvalidOperation

import websockets
from pydantic import BaseModel

from app.config import settings
from app.ws.manager import ConnectionManager

log = logging.getLogger("coinbase")

_HUNDRED = Decimal(100)


class RefPrice(BaseModel):
    symbol: str  # our symbol, e.g. BTCUSD
    product_id: str  # Coinbase's, e.g. BTC-USD
    price: Decimal
    bid: Decimal | None
    ask: Decimal | None
    spread: Decimal | None
    open_24h: Decimal | None
    high_24h: Decimal | None
    low_24h: Decimal | None
    volume_24h: Decimal | None
    change_24h: Decimal | None
    change_24h_pct: Decimal | None
    source_time: dt.datetime | None  # Coinbase's own timestamp
    received_at: dt.datetime  # when we received it


class RefPriceSnapshot(BaseModel):
    status: str  # LIVE | STALE | DOWN
    source: str = "coinbase"
    prices: list[RefPrice]


def _dec(value: object) -> Decimal | None:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _time(value: object) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        # Coinbase sends nanoseconds ("...852203781Z"); fromisoformat wants at most 6 digits.
        head, _, frac = value.rstrip("Z").partition(".")
        return dt.datetime.fromisoformat(f"{head}.{frac[:6]}+00:00" if frac else f"{head}+00:00")
    except ValueError:
        return None


def parse_ticker(msg: dict, products: dict[str, str], now: dt.datetime | None = None) -> RefPrice | None:
    """A Coinbase `ticker` message to a RefPrice, or None if it isn't a usable
    ticker for a product we track. `products` maps Coinbase product id to our symbol."""
    if msg.get("type") != "ticker":
        return None
    product_id = msg.get("product_id")
    symbol = products.get(product_id) if isinstance(product_id, str) else None
    price = _dec(msg.get("price"))
    if symbol is None or price is None or price <= 0:
        return None

    bid, ask = _dec(msg.get("best_bid")), _dec(msg.get("best_ask"))
    open_24h = _dec(msg.get("open_24h"))
    change = price - open_24h if open_24h is not None else None
    return RefPrice(
        symbol=symbol,
        product_id=product_id,
        price=price,
        bid=bid,
        ask=ask,
        spread=ask - bid if bid is not None and ask is not None else None,
        open_24h=open_24h,
        high_24h=_dec(msg.get("high_24h")),
        low_24h=_dec(msg.get("low_24h")),
        volume_24h=_dec(msg.get("volume_24h")),
        change_24h=change,
        change_24h_pct=change / open_24h * _HUNDRED if change is not None and open_24h else None,
        source_time=_time(msg.get("time")),
        received_at=now or dt.datetime.now(dt.UTC),
    )


class CoinbaseFeed:
    def __init__(self, ws_manager: ConnectionManager) -> None:
        self._ws = ws_manager
        self._products: dict[str, str] = {}  # Coinbase product id -> our symbol
        self._latest: dict[str, RefPrice] = {}
        self._dirty: set[str] = set()
        self._connected = False
        self._last_message: float | None = None  # time.monotonic()
        self._last_status = "DOWN"
        self._tasks: list[asyncio.Task] = []

    # -- state ---------------------------------------------------------------

    def ingest(self, msg: dict) -> None:
        """Apply one decoded Coinbase message."""
        kind = msg.get("type")
        if kind == "error":
            log.warning("Coinbase rejected the subscription: %s (%s)", msg.get("message"), msg.get("reason"))
            return
        rp = parse_ticker(msg, self._products)
        if rp is None:
            return
        self._latest[rp.symbol] = rp
        self._dirty.add(rp.symbol)
        self._last_message = time.monotonic()

    def status(self) -> str:
        if not self._connected:
            return "DOWN"
        if self._last_message is None or time.monotonic() - self._last_message > settings.coinbase_stale_after_seconds:
            return "STALE"
        return "LIVE"

    def snapshot(self) -> RefPriceSnapshot:
        return RefPriceSnapshot(status=self.status(), prices=sorted(self._latest.values(), key=lambda p: p.symbol))

    # -- pushing to GUIs -----------------------------------------------------

    async def flush(self) -> None:
        """Push changed prices (coalesced: one message per symbol however many
        ticks arrived) and any change of feed status."""
        status = self.status()
        if status != self._last_status:
            self._last_status = status
            await self._ws.broadcast_all("ref_status", {"status": status})

        dirty, self._dirty = self._dirty, set()
        for symbol in sorted(dirty):
            await self._ws.broadcast_symbol(symbol, "ref_price", self._latest[symbol].model_dump(mode="json"))

    async def _flush_loop(self) -> None:
        interval = settings.coinbase_push_interval_ms / 1000
        while True:
            await asyncio.sleep(interval)
            try:
                await self.flush()
            except Exception:  # noqa: BLE001 -- a bad push must not kill the loop
                log.exception("ref price flush failed")

    # -- connection to Coinbase ---------------------------------------------

    async def _read_loop(self) -> None:
        attempt = 0
        subscribe = {"type": "subscribe", "product_ids": list(self._products), "channels": ["ticker"]}
        while True:
            try:
                async with websockets.connect(settings.coinbase_ws_url, open_timeout=10, ping_interval=20, ping_timeout=20) as ws:
                    await ws.send(json.dumps(subscribe))
                    self._connected = True
                    attempt = 0
                    log.info("connected to Coinbase for %s", ", ".join(self._products))
                    async for raw in ws:
                        self.ingest(json.loads(raw))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 -- any failure means reconnect
                log.warning("Coinbase feed dropped (%s: %s); retrying", type(exc).__name__, exc)
            finally:
                self._connected = False
            await asyncio.sleep(min(30, 2**attempt))
            attempt += 1

    # -- lifecycle -----------------------------------------------------------

    def start(self, products: dict[str, str]) -> None:
        """`products` maps Coinbase product id to our symbol. A no-op if there's nothing to track."""
        self._products = dict(products)
        if not self._products:
            return
        self._tasks = [asyncio.create_task(self._read_loop()), asyncio.create_task(self._flush_loop())]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []
