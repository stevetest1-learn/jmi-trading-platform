"""Arms-length client of the backend's own public REST/WS API.

Deliberately has zero shared imports with backend/ -- this is what makes it
a genuine demonstration of "a client of the same internal order-submission
API," not a fork of the matching logic. A real integration would swap the
username/password login below for whatever service-credential flow the
platform actually uses (see config.py's comp_id_to_credentials TODO).
"""

import httpx

from app.config import settings


class EngineClient:
    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}

    async def token_for(self, comp_id: str) -> str:
        if comp_id in self._tokens:
            return self._tokens[comp_id]
        username, password = settings.comp_id_to_credentials[comp_id]
        async with httpx.AsyncClient(base_url=settings.backend_base_url) as client:
            resp = await client.post("/auth/login", json={"username": username, "password": password})
            resp.raise_for_status()
            token = resp.json()["access_token"]
        self._tokens[comp_id] = token
        return token

    async def submit_order(
        self, comp_id: str, *, symbol: str, side: str, order_type: str, qty: str, price: str | None
    ) -> dict:
        token = await self.token_for(comp_id)
        async with httpx.AsyncClient(base_url=settings.backend_base_url) as client:
            resp = await client.post(
                "/orders",
                json={"symbol": symbol, "side": side, "order_type": order_type, "qty": qty, "price": price},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_order_book(self, symbol: str) -> dict:
        async with httpx.AsyncClient(base_url=settings.backend_base_url) as client:
            resp = await client.get(f"/marketdata/{symbol}")
            resp.raise_for_status()
            return resp.json()


engine_client = EngineClient()
