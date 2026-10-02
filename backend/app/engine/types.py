import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrdStatus(StrEnum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


@dataclass
class BookOrder:
    """In-memory representation of a resting/working order inside an OrderBook."""

    order_id: int
    account_id: int
    symbol: str
    side: Side
    order_type: OrderType
    price: Decimal | None
    qty: Decimal
    leaves_qty: Decimal
    status: OrdStatus
    seq: int
    ts_created: dt.datetime


@dataclass
class Fill:
    buy_order_id: int
    sell_order_id: int
    buy_account_id: int
    sell_account_id: int
    symbol: str
    price: Decimal
    qty: Decimal
    aggressor_side: Side
    # The resting (pre-existing) order's post-trade state, so the caller can
    # sync its DB row and release its reservation without a second lookup.
    resting_order_id: int
    resting_leaves_qty_after: Decimal
    resting_status_after: OrdStatus


@dataclass
class SubmitResult:
    order: BookOrder
    fills: list[Fill] = field(default_factory=list)
    trade_ids: list[int] = field(default_factory=list)  # parallel to `fills`
    csv_rows: list[dict] = field(default_factory=list)  # trade-log rows, 2 per fill (one per side)
    rejected: bool = False
    reject_reason: str | None = None
