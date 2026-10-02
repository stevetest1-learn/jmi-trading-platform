"""Creates tables (if needed) and seeds demo symbols + accounts.

Run with: python -m scripts.seed_demo_data (from backend/, with DATABASE_URL
pointed at a running Postgres -- e.g. `docker compose up -d postgres`).

Seeds a funded `market_maker` account with starting BTC/ETH inventory. This
is necessary, not incidental: no-short-selling means crypto can only enter
the system via a fill against an account that already holds it, so someone
has to start non-zero or the very first SELL has no legitimate counterparty.

Every starting position is booked at a cost basis equal to the reference
price below, as if bought at that price, so unrealized P&L starts near zero
instead of equalling the inventory's whole market value.
"""

import asyncio
from decimal import Decimal
from sqlalchemy import select
from app.auth.security import hash_password
from app.db.base import Base, async_session_factory, engine
from app.db.models import Account, Position, Symbol

SYMBOLS = [
    dict(
        symbol="BTCUSD", display_symbol="BTC/USD", base_asset="BTC", quote_asset="USD",
        price_decimals=2, qty_decimals=6, tick_size=Decimal("0.01"), lot_size=Decimal("0.0001"),
    ),
    dict(
        symbol="ETHUSD", display_symbol="ETH/USD", base_asset="ETH", quote_asset="USD",
        price_decimals=2, qty_decimals=6, tick_size=Decimal("0.01"), lot_size=Decimal("0.001"),
    ),
]

# Alice/Bob's starting crypto is split ~$45k BTC + ~$55k ETH (at the
# reference prices below) = ~$100k in their wallet, on top of their $100k
# cash -- so both accounts can immediately BUY or SELL either symbol, not
# just BUY. Reference prices are only a seeding convenience (to size a
# round-ish position); real prices are whatever the book actually trades at.
_BTC_REF_PRICE = Decimal("60000")
_ETH_REF_PRICE = Decimal("1000")
REFERENCE_PRICES = {"BTCUSD": _BTC_REF_PRICE, "ETHUSD": _ETH_REF_PRICE}
_ALICE_BOB_BTC_QTY = Decimal("45000") / _BTC_REF_PRICE  # 0.75 BTC
_ALICE_BOB_ETH_QTY = Decimal("55000") / _ETH_REF_PRICE  # 55 ETH

ACCOUNTS = [
    dict(
        username="market_maker", password="demo1234", display_name="Market Maker",
        usd_balance=Decimal("5000000"),
        starting_positions={"BTCUSD": Decimal("50"), "ETHUSD": Decimal("500")},
    ),
    dict(
        username="alice", password="demo1234", display_name="Alice",
        usd_balance=Decimal("100000"),
        starting_positions={"BTCUSD": _ALICE_BOB_BTC_QTY, "ETHUSD": _ALICE_BOB_ETH_QTY},
    ),
    dict(
        username="bob", password="demo1234", display_name="Bob",
        usd_balance=Decimal("100000"),
        starting_positions={"BTCUSD": _ALICE_BOB_BTC_QTY, "ETHUSD": _ALICE_BOB_ETH_QTY},
    ),
]


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session, session.begin():
        for s in SYMBOLS:
            if await session.get(Symbol, s["symbol"]) is None:
                session.add(Symbol(**s, active=True))

        for a in ACCOUNTS:
            existing = (
                await session.execute(select(Account).where(Account.username == a["username"]))
            ).scalar_one_or_none()
            if existing is not None:
                continue
            account = Account(
                username=a["username"],
                password_hash=hash_password(a["password"]),
                display_name=a["display_name"],
                usd_balance=a["usd_balance"],
                reserved_usd=Decimal(0),
            )
            session.add(account)
            await session.flush()
            for symbol, qty in a["starting_positions"].items():
                session.add(Position(account_id=account.id, symbol=symbol, net_qty=qty, avg_cost=REFERENCE_PRICES[symbol]))

    print("Seeded symbols:", [s["symbol"] for s in SYMBOLS])
    print("Seeded accounts:", [a["username"] for a in ACCOUNTS])
    print("All demo accounts use password: demo1234")


if __name__ == "__main__":
    asyncio.run(seed())
