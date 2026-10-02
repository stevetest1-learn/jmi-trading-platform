"""End-to-end test: a raw FIX client sends Logon + NewOrderSingle at the
acceptor and asserts a Logon ack and a FILLED ExecutionReport come back,
with the fill actually visible in the backend's blotter afterward.

Requires the real backend (see ../backend) running locally, e.g.:
    cd ../backend && docker compose up -d postgres && uvicorn app.main:app
Run with: BACKEND_BASE_URL=http://localhost:8000 pytest tests/test_fix_session.py
"""

import asyncio
import os

os.environ.setdefault("FIX_LISTEN_PORT", "19878")
os.environ.setdefault("BACKEND_BASE_URL", "http://localhost:8000")
os.environ.setdefault("BACKEND_WS_URL", "ws://localhost:8000/ws")

import httpx
import pytest
import simplefix

from app.acceptor import serve
from app.config import settings


def _client_logon(seq: int) -> bytes:
    msg = simplefix.FixMessage()
    msg.append_pair(8, settings.fix_version, header=True)
    msg.append_pair(35, "A", header=True)
    msg.append_pair(49, "CLIENT1", header=True)
    msg.append_pair(56, settings.sender_comp_id, header=True)
    msg.append_pair(34, seq, header=True)
    msg.append_utc_timestamp(52, header=True)
    msg.append_pair(98, 0)
    msg.append_pair(108, settings.heartbeat_interval)
    return msg.encode()


def _client_new_order_single(seq: int, cl_ord_id: str, symbol: str, side: str, qty: str, price: str) -> bytes:
    msg = simplefix.FixMessage()
    msg.append_pair(8, settings.fix_version, header=True)
    msg.append_pair(35, "D", header=True)
    msg.append_pair(49, "CLIENT1", header=True)
    msg.append_pair(56, settings.sender_comp_id, header=True)
    msg.append_pair(34, seq, header=True)
    msg.append_utc_timestamp(52, header=True)
    msg.append_pair(11, cl_ord_id)
    msg.append_pair(55, symbol)
    msg.append_pair(54, "1" if side == "BUY" else "2")
    msg.append_pair(40, "2")  # LIMIT
    msg.append_pair(38, qty)
    msg.append_pair(44, price)
    msg.append_utc_timestamp(60)
    return msg.encode()


async def _seed_resting_sell(symbol: str, qty: str, price: str) -> None:
    """market_maker rests a SELL via the plain REST API so the FIX client
    (logged in as bob) has real liquidity to cross."""
    async with httpx.AsyncClient(base_url=settings.backend_base_url) as client:
        resp = await client.post("/auth/login", json={"username": "market_maker", "password": "demo1234"})
        resp.raise_for_status()
        token = resp.json()["access_token"]
        resp = await client.post(
            "/orders",
            json={"symbol": symbol, "side": "SELL", "order_type": "LIMIT", "qty": qty, "price": price},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()


@pytest.mark.asyncio
async def test_new_order_single_crosses_and_returns_fill_execution_report():
    price = "12345.67"
    await _seed_resting_sell("BTCUSD", "0.1", price)

    server_task = asyncio.create_task(serve())
    await asyncio.sleep(0.2)  # let the acceptor start listening

    try:
        reader, writer = await asyncio.open_connection(settings.listen_host, settings.listen_port)
        try:
            writer.write(_client_logon(1))
            await writer.drain()

            parser = simplefix.FixParser()

            async def next_message():
                while True:
                    msg = parser.get_message()
                    if msg is not None:
                        return msg
                    data = await asyncio.wait_for(reader.read(4096), timeout=5)
                    parser.append_buffer(data)

            logon_ack = await next_message()
            assert logon_ack.get(35) == b"A"

            writer.write(_client_new_order_single(2, "CL-1", "BTCUSD", "BUY", "0.1", price))
            await writer.drain()

            exec_report = await next_message()
            assert exec_report.get(35) == b"8"
            assert exec_report.get(39) == b"2"  # OrdStatus: Filled
            assert exec_report.get(31) == price.encode()  # LastPx
            assert exec_report.get(32) == b"0.1"  # LastQty
        finally:
            writer.close()
    finally:
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass

    # Confirm the fill really landed in the backend, not just in the FIX reply.
    async with httpx.AsyncClient(base_url=settings.backend_base_url) as client:
        resp = await client.post("/auth/login", json={"username": "bob", "password": "demo1234"})
        token = resp.json()["access_token"]
        resp = await client.get("/blotter", headers={"Authorization": f"Bearer {token}"})
        rows = resp.json()
    assert any(
        r["status"] == "FILL" and r["symbol"] == "BTCUSD" and float(r["price"]) == float(price) for r in rows
    )
