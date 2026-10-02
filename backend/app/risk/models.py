from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class Holder(BaseModel):
    account_id: int
    username: str
    display_name: str
    net_qty: Decimal
    notional: Decimal | None
    share_pct: Decimal


class SymbolExposure(BaseModel):
    symbol: str
    display_symbol: str
    mark_price: Decimal | None
    mark_source: str  # MID | LAST_TRADE | NONE
    net_qty: Decimal
    notional: Decimal  # 0 when there is no mark price
    holders: list[Holder]


class AccountPosition(BaseModel):
    symbol: str
    display_symbol: str
    net_qty: Decimal
    avg_cost: Decimal
    mark_price: Decimal | None
    notional: Decimal | None
    unrealized_pnl: Decimal | None
    realized_pnl_today: Decimal
    realized_pnl_total: Decimal
    share_of_symbol_pct: Decimal


class AccountRisk(BaseModel):
    account_id: int
    username: str
    display_name: str
    usd_balance: Decimal
    reserved_usd: Decimal
    utilization_pct: Decimal
    total_exposure: Decimal
    unrealized_pnl: Decimal
    realized_pnl_today: Decimal
    platform_share_pct: Decimal
    positions: list[AccountPosition]


class RiskAlert(BaseModel):
    severity: str  # CRITICAL | WARNING | INFO
    code: str  # CONCENTRATION | UTILIZATION | NO_MARK
    message: str
    account: str | None = None
    symbol: str | None = None


class RiskTotals(BaseModel):
    net_exposure: Decimal
    unrealized_pnl: Decimal
    realized_pnl_today: Decimal
    accounts: int
    symbols: int


class RiskThresholds(BaseModel):
    concentration_limit_pct: Decimal
    utilization_warn_pct: Decimal


class RiskOverview(BaseModel):
    as_of: datetime
    totals: RiskTotals
    symbols: list[SymbolExposure]
    accounts: list[AccountRisk]
    alerts: list[RiskAlert]
    thresholds: RiskThresholds
