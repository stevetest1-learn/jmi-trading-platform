from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    account_id: int
    username: str


class AccountResponse(BaseModel):
    account_id: int
    username: str
    display_name: str
    usd_balance: Decimal
    reserved_usd: Decimal
    can_view_risk: bool = False


class SymbolResponse(BaseModel):
    symbol: str
    display_symbol: str
    base_asset: str
    quote_asset: str
    price_decimals: int
    qty_decimals: int
    tick_size: Decimal
    lot_size: Decimal
    active: bool


class OrderCreateRequest(BaseModel):
    symbol: str
    side: str  # BUY | SELL
    order_type: str  # LIMIT | MARKET
    qty: Decimal
    price: Decimal | None = None


class FillSummary(BaseModel):
    trade_id: int
    price: Decimal
    qty: Decimal


class OrderResponse(BaseModel):
    order_id: int
    symbol: str
    side: str
    order_type: str
    qty: Decimal
    price: Decimal | None
    leaves_qty: Decimal
    status: str
    reject_reason: str | None
    fills: list[FillSummary] = []


class PositionResponse(BaseModel):
    symbol: str
    net_qty: Decimal
    reserved_qty: Decimal
    avg_cost: Decimal
    realized_pnl_today: Decimal
    realized_pnl_total: Decimal
    unrealized_pnl: Decimal


class BlotterRow(BaseModel):
    order_id: int
    trade_id: int | None
    symbol: str
    side: str
    qty: Decimal
    price: Decimal | None
    ts: datetime
    status: str
    reject_reason: str | None = None


class DepthLevel(BaseModel):
    price: Decimal
    qty: Decimal


class OrderBookSnapshot(BaseModel):
    symbol: str
    bids: list[DepthLevel]
    asks: list[DepthLevel]
