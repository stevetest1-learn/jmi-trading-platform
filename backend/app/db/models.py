import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MONEY = Numeric(20, 8)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    usd_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    reserved_usd: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    is_service_account: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class Symbol(Base):
    __tablename__ = "symbols"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)  # e.g. "BTCUSD"
    display_symbol: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g. "BTC/USD"
    base_asset: Mapped[str] = mapped_column(String(8), nullable=False)
    quote_asset: Mapped[str] = mapped_column(String(8), nullable=False)
    price_decimals: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    qty_decimals: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    tick_size: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    lot_size: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("side IN ('BUY','SELL')", name="ck_orders_side"),
        CheckConstraint("order_type IN ('LIMIT','MARKET')", name="ck_orders_type"),
        CheckConstraint(
            "status IN ('NEW','PARTIALLY_FILLED','FILLED','CANCELED','REJECTED')",
            name="ck_orders_status",
        ),
        CheckConstraint("source IN ('GUI','FIX')", name="ck_orders_source"),
        CheckConstraint("qty > 0", name="ck_orders_qty_positive"),
        Index("idx_orders_open_book", "symbol", "status"),
        Index("idx_orders_account_status", "account_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounts.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), ForeignKey("symbols.symbol"), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    order_type: Mapped[str] = mapped_column(String(6), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    qty: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    leaves_qty: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    reject_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(4), nullable=False, default="GUI")
    ts_created: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    ts_updated: Mapped[dt.datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("aggressor_side IN ('BUY','SELL')", name="ck_trades_aggressor"),
        CheckConstraint("settlement_status IN ('PENDING','SETTLED')", name="ck_trades_settlement"),
        Index("idx_trades_symbol_ts", "symbol", "ts"),
        Index("idx_trades_buy_account", "buy_account_id", "ts"),
        Index("idx_trades_sell_account", "sell_account_id", "ts"),
        Index("idx_trades_settlement", "settlement_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), ForeignKey("symbols.symbol"), nullable=False)
    buy_order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id"), nullable=False)
    sell_order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id"), nullable=False)
    buy_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounts.id"), nullable=False)
    sell_account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounts.id"), nullable=False)
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    qty: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    aggressor_side: Mapped[str] = mapped_column(String(4), nullable=False)
    ts: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    settlement_status: Mapped[str] = mapped_column(String(8), nullable=False, default="PENDING")
    settled_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)


class Position(Base):
    __tablename__ = "positions"

    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounts.id"), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), ForeignKey("symbols.symbol"), primary_key=True)
    net_qty: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    reserved_qty: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    avg_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    realized_pnl_today: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    realized_pnl_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    updated_at: Mapped[dt.datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (CheckConstraint("net_qty >= 0", name="ck_positions_no_short"),)


class DailySettlement(Base):
    __tablename__ = "daily_settlements"
    __table_args__ = (
        UniqueConstraint("settlement_date", "account_id", "symbol", name="uq_daily_settlement"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    settlement_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    account_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("accounts.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), ForeignKey("symbols.symbol"), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    ending_net_qty: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    ending_avg_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    ending_usd_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    trades_settled_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
