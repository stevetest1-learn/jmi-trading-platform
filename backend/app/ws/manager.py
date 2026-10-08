import datetime as dt
import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """Fan-out registry for WS pushes: account-scoped (own orders/fills/
    rejects/positions) and symbol-scoped (market data) channels."""

    def __init__(self) -> None:
        self._by_account: dict[int, set[WebSocket]] = defaultdict(set)
        self._by_symbol: dict[str, set[WebSocket]] = defaultdict(set)
        self._risk_subscribers: set[WebSocket] = set()
        self._account_of: dict[WebSocket, int] = {}

    def connect(self, ws: WebSocket, account_id: int) -> None:
        self._by_account[account_id].add(ws)
        self._account_of[ws] = account_id

    def disconnect(self, ws: WebSocket) -> None:
        account_id = self._account_of.pop(ws, None)
        if account_id is not None:
            self._by_account[account_id].discard(ws)
        for subscribers in self._by_symbol.values():
            subscribers.discard(ws)
        self._risk_subscribers.discard(ws)

    def subscribe_risk(self, ws: WebSocket) -> None:
        """Callers must have already checked the account is a risk viewer."""
        self._risk_subscribers.add(ws)

    def subscribe_symbol(self, ws: WebSocket, symbol: str) -> None:
        self._by_symbol[symbol].add(ws)

    def unsubscribe_symbol(self, ws: WebSocket, symbol: str) -> None:
        self._by_symbol[symbol].discard(ws)

    @staticmethod
    def _envelope(type_: str, payload: dict) -> str:
        return json.dumps({"type": type_, "payload": payload, "ts": dt.datetime.now(dt.UTC).isoformat()})

    async def send_to_account(self, account_id: int, type_: str, payload: dict) -> None:
        message = self._envelope(type_, payload)
        dead: list[WebSocket] = []
        for ws in list(self._by_account.get(account_id, ())):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001 -- best-effort push, drop dead sockets
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_all(self, type_: str, payload: dict) -> None:
        """Every connected socket, regardless of account or subscriptions."""
        message = self._envelope(type_, payload)
        dead: list[WebSocket] = []
        for ws in list(self._account_of):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_risk(self, type_: str, payload: dict) -> None:
        message = self._envelope(type_, payload)
        dead: list[WebSocket] = []
        for ws in list(self._risk_subscribers):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_symbol(self, symbol: str, type_: str, payload: dict) -> None:
        message = self._envelope(type_, {"symbol": symbol, **payload})
        dead: list[WebSocket] = []
        for ws in list(self._by_symbol.get(symbol, ())):
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
