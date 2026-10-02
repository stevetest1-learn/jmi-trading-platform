"""Measures the latency figures quoted on the carousel's results slide.

Run against the throwaway demo backend only (it places hundreds of orders):
    python measure.py [http://localhost:8001]
Numbers are from a laptop with a local Postgres, not a production network.
"""

import asyncio
import json
import statistics as st
import sys
import time

import httpx
import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
WS = BASE.replace("http", "ws") + "/ws"


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def summarize(label, ms):
    print(f"{label:<44} n={len(ms):<4} p50={st.median(ms):6.1f} ms   p95={pct(ms, .95):6.1f} ms   max={max(ms):6.1f} ms")


def login(c, user):
    r = c.post("/auth/login", json={"username": user, "password": "demo1234"})
    return r.json()["access_token"]


def main():
    c = httpx.Client(base_url=BASE, timeout=20)
    mm, alice = login(c, "market_maker"), login(c, "alice")
    H = lambda t: {"Authorization": f"Bearer {t}"}

    def post(token, side, qty, price):
        t0 = time.perf_counter()
        r = c.post("/orders", json={"symbol": "BTCUSD", "side": side, "order_type": "LIMIT", "qty": qty, "price": price}, headers=H(token))
        return (time.perf_counter() - t0) * 1000, r.json()

    # 1. resting order, no match: far below the market
    rest = []
    for _ in range(200):
        ms, d = post(mm, "BUY", "0.001", "1000")
        rest.append(ms)
        assert d["status"] == "NEW", d
    summarize("POST /orders  resting limit order (ack)", rest)

    # 2. crossing order: persists the trade, both positions, both balances
    fill = []
    for _ in range(100):
        post(mm, "SELL", "0.0001", "70000")
        ms, d = post(alice, "BUY", "0.0001", "70000")
        fill.append(ms)
        assert d["status"] == "FILLED", d
    summarize("POST /orders  crossing order -> fill (ack)", fill)

    # 3. the risk overview read
    risk = []
    for _ in range(200):
        t0 = time.perf_counter()
        r = c.get("/risk/overview", headers=H(mm))
        risk.append((time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
    summarize("GET  /risk/overview (3 accounts, 2 symbols)", risk)

    # 4. fill -> risk push reaches the market maker's open socket
    async def push_latency():
        out = []
        async with websockets.connect(f"{WS}?token={mm}") as ws:
            await ws.send(json.dumps({"type": "subscribe_risk", "payload": {}}))
            await asyncio.sleep(0.3)
            ac = httpx.AsyncClient(base_url=BASE, timeout=20)
            for _ in range(60):
                await ac.post("/orders", json={"symbol": "BTCUSD", "side": "SELL", "order_type": "LIMIT", "qty": "0.0001", "price": "70000"}, headers=H(mm))
                await asyncio.sleep(0.15)
                while True:  # drain the resting order's own nudge
                    try:
                        await asyncio.wait_for(ws.recv(), 0.05)
                    except asyncio.TimeoutError:
                        break
                t0 = time.perf_counter()
                await ac.post("/orders", json={"symbol": "BTCUSD", "side": "BUY", "order_type": "LIMIT", "qty": "0.0001", "price": "70000"}, headers=H(alice))
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
                    if msg["type"] == "risk_dirty":
                        out.append((time.perf_counter() - t0) * 1000)
                        break
            await ac.aclose()
        return out

    summarize("fill sent -> risk_dirty received over WebSocket", asyncio.run(push_latency()))


if __name__ == "__main__":
    main()
