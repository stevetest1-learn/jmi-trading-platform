"""Builds a realistic trading session against a *throwaway* demo backend so the
carousel screenshots show a populated book, fills, rejects, P&L and alerts.

Never point this at the real dev database: it places and cancels many orders.
Usage: python scenario.py [http://localhost:8001]
"""

import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
client = httpx.Client(base_url=BASE, timeout=20)


def login(user: str) -> dict:
    r = client.post("/auth/login", json={"username": user, "password": "demo1234"})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


H = {u: login(u) for u in ("market_maker", "alice", "bob")}


def order(user: str, symbol: str, side: str, qty: str, price: str | None, otype: str = "LIMIT") -> dict:
    body = {"symbol": symbol, "side": side, "order_type": otype, "qty": qty, "price": price}
    r = client.post("/orders", json=body, headers=H[user])
    r.raise_for_status()
    d = r.json()
    extra = d["reject_reason"] or ", ".join(f"{f['qty']}@{f['price']}" for f in d["fills"])
    print(f"  {user:<12} {side:<4} {qty:>7} {symbol} @ {str(price):>6} -> {d['status']:<16} {extra}")
    return d


def cancel_all(user: str) -> None:
    r = client.get("/orders", params={"status_filter": "open"}, headers=H[user])
    for o in r.json():
        client.delete(f"/orders/{o['order_id']}", headers=H[user]).raise_for_status()


def quote(mid_btc: int, mid_eth: int) -> None:
    for i, (qty, off) in enumerate([("5", 50), ("8", 100), ("12", 200), ("15", 350)]):
        order("market_maker", "BTCUSD", "SELL", qty, str(mid_btc + off))
        order("market_maker", "BTCUSD", "BUY", qty, str(mid_btc - off))
    for qty, off in [("50", 1), ("80", 3), ("120", 6)]:
        order("market_maker", "ETHUSD", "SELL", qty, str(mid_eth + off))
        order("market_maker", "ETHUSD", "BUY", qty, str(mid_eth - off))


print("1. market maker quotes a layered book around 60,000 / 1,000")
quote(60000, 1000)

print("2. clients trade against it")
order("alice", "BTCUSD", "BUY", "0.3", "60050")  # lifts the ask
order("bob", "BTCUSD", "SELL", "0.2", "59950")  # hits the bid
order("alice", "ETHUSD", "BUY", "10", "1001")
order("bob", "ETHUSD", "BUY", "6", "1003")  # fills at the better resting price

print("3. peer-to-peer: Alice improves the ask, Bob lifts it. No market maker involved")
order("alice", "BTCUSD", "SELL", "0.1", "60040")
order("bob", "BTCUSD", "BUY", "0.1", "60040")

print("4. pre-trade checks reject (not queue) invalid orders")
order("alice", "BTCUSD", "SELL", "5", "60000")  # more BTC than she holds
order("bob", "BTCUSD", "BUY", "100", "60100")  # far more cash than he has

print("5. the market moves up 1,000 / 20: market maker re-quotes")
cancel_all("market_maker")
quote(61000, 1020)

print("6. clients leave resting orders; Bob reserves most of his cash")
order("alice", "BTCUSD", "BUY", "0.2", "60900")
order("alice", "ETHUSD", "SELL", "5", "1030")
order("bob", "BTCUSD", "BUY", "1.35", "60000")

print("done")
