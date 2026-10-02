"""Platform-wide risk & exposure aggregation.

`compute_overview` is a pure function over plain inputs so the maths and the
alert rules can be tested without a database; `load_overview` gathers the
inputs from Postgres and the in-memory order books.

Mark price: the mid of the best bid/ask when the book is two-sided,
otherwise the last traded price, otherwise none (and the symbol is then
flagged, not silently valued at zero). Shorting is disallowed, so every
position is long and net exposure equals gross exposure.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Account, Position, Symbol, Trade
from app.engine.engine import MatchingEngine
from app.risk.models import (
    AccountPosition,
    AccountRisk,
    Holder,
    RiskAlert,
    RiskOverview,
    RiskThresholds,
    RiskTotals,
    SymbolExposure,
)

_HUNDRED = Decimal(100)
_SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    display_symbol: str


@dataclass(frozen=True)
class AccountInfo:
    id: int
    username: str
    display_name: str
    usd_balance: Decimal
    reserved_usd: Decimal


@dataclass(frozen=True)
class PositionInfo:
    account_id: int
    symbol: str
    net_qty: Decimal
    avg_cost: Decimal
    realized_pnl_today: Decimal
    realized_pnl_total: Decimal


@dataclass(frozen=True)
class Mark:
    price: Decimal | None
    source: str  # MID | LAST_TRADE | NONE


@dataclass(frozen=True)
class Thresholds:
    concentration_limit_pct: Decimal
    utilization_warn_pct: Decimal


NO_MARK = Mark(price=None, source="NONE")


def compute_overview(
    *,
    symbols: list[SymbolInfo],
    accounts: list[AccountInfo],
    positions: list[PositionInfo],
    marks: dict[str, Mark],
    thresholds: Thresholds,
    as_of: dt.datetime,
) -> RiskOverview:
    acct_by_id = {a.id: a for a in accounts}
    display = {s.symbol: s.display_symbol for s in symbols}

    # Drop fully-flat positions that never realized anything, as GET /positions does.
    live = [
        p
        for p in positions
        if p.account_id in acct_by_id and p.symbol in display and (p.net_qty != 0 or p.realized_pnl_total != 0)
    ]

    platform_qty: dict[str, Decimal] = defaultdict(Decimal)
    for p in live:
        platform_qty[p.symbol] += p.net_qty

    def share_pct(qty: Decimal, symbol: str) -> Decimal:
        total = platform_qty[symbol]
        return qty / total * _HUNDRED if total > 0 else Decimal(0)

    alerts: list[RiskAlert] = []
    symbol_rows: list[SymbolExposure] = []

    for s in symbols:
        mark = marks.get(s.symbol, NO_MARK)
        total_qty = platform_qty[s.symbol]

        holders: list[Holder] = []
        holding = sorted(
            (p for p in live if p.symbol == s.symbol and p.net_qty > 0),
            key=lambda p: p.net_qty,
            reverse=True,
        )
        for p in holding:
            a = acct_by_id[p.account_id]
            pct = share_pct(p.net_qty, s.symbol)
            holders.append(
                Holder(
                    account_id=a.id,
                    username=a.username,
                    display_name=a.display_name,
                    net_qty=p.net_qty,
                    notional=p.net_qty * mark.price if mark.price is not None else None,
                    share_pct=pct,
                )
            )
            if pct > thresholds.concentration_limit_pct:
                alerts.append(
                    RiskAlert(
                        severity="CRITICAL",
                        code="CONCENTRATION",
                        message=(
                            f"{a.display_name} holds {pct:.1f}% of platform {s.display_symbol} inventory "
                            f"(limit {thresholds.concentration_limit_pct:g}%)."
                        ),
                        account=a.username,
                        symbol=s.symbol,
                    )
                )

        if total_qty > 0 and mark.price is None:
            alerts.append(
                RiskAlert(
                    severity="WARNING",
                    code="NO_MARK",
                    message=(
                        f"No market price for {s.display_symbol} (empty book, no trades yet): "
                        "exposure and unrealized P&L are not valued."
                    ),
                    symbol=s.symbol,
                )
            )

        symbol_rows.append(
            SymbolExposure(
                symbol=s.symbol,
                display_symbol=s.display_symbol,
                mark_price=mark.price,
                mark_source=mark.source,
                net_qty=total_qty,
                notional=total_qty * mark.price if mark.price is not None else Decimal(0),
                holders=holders,
            )
        )

    positions_by_account: dict[int, list[PositionInfo]] = defaultdict(list)
    for p in live:
        positions_by_account[p.account_id].append(p)

    account_rows: list[AccountRisk] = []
    for a in accounts:
        rows: list[AccountPosition] = []
        exposure = Decimal(0)
        unrealized = Decimal(0)
        realized_today = Decimal(0)

        for p in sorted(positions_by_account[a.id], key=lambda p: p.symbol):
            mark = marks.get(p.symbol, NO_MARK)
            notional = p.net_qty * mark.price if mark.price is not None else None
            upnl = p.net_qty * (mark.price - p.avg_cost) if mark.price is not None else None
            exposure += notional or Decimal(0)
            unrealized += upnl or Decimal(0)
            realized_today += p.realized_pnl_today
            rows.append(
                AccountPosition(
                    symbol=p.symbol,
                    display_symbol=display[p.symbol],
                    net_qty=p.net_qty,
                    avg_cost=p.avg_cost,
                    mark_price=mark.price,
                    notional=notional,
                    unrealized_pnl=upnl,
                    realized_pnl_today=p.realized_pnl_today,
                    realized_pnl_total=p.realized_pnl_total,
                    share_of_symbol_pct=share_pct(p.net_qty, p.symbol),
                )
            )

        utilization = a.reserved_usd / a.usd_balance * _HUNDRED if a.usd_balance > 0 else Decimal(0)
        if utilization >= thresholds.utilization_warn_pct:
            alerts.append(
                RiskAlert(
                    severity="WARNING",
                    code="UTILIZATION",
                    message=(
                        f"{a.display_name} has {utilization:.1f}% of cash reserved for open orders "
                        f"(warn at {thresholds.utilization_warn_pct:g}%)."
                    ),
                    account=a.username,
                )
            )

        account_rows.append(
            AccountRisk(
                account_id=a.id,
                username=a.username,
                display_name=a.display_name,
                usd_balance=a.usd_balance,
                reserved_usd=a.reserved_usd,
                utilization_pct=utilization,
                total_exposure=exposure,
                unrealized_pnl=unrealized,
                realized_pnl_today=realized_today,
                platform_share_pct=Decimal(0),  # filled in once the platform total is known
                positions=rows,
            )
        )

    platform_exposure = sum((r.total_exposure for r in account_rows), Decimal(0))
    for r in account_rows:
        r.platform_share_pct = r.total_exposure / platform_exposure * _HUNDRED if platform_exposure > 0 else Decimal(0)
    account_rows.sort(key=lambda r: r.total_exposure, reverse=True)

    alerts.sort(key=lambda al: _SEVERITY_ORDER[al.severity])

    return RiskOverview(
        as_of=as_of,
        totals=RiskTotals(
            net_exposure=platform_exposure,
            unrealized_pnl=sum((r.unrealized_pnl for r in account_rows), Decimal(0)),
            realized_pnl_today=sum((r.realized_pnl_today for r in account_rows), Decimal(0)),
            accounts=len(account_rows),
            symbols=len(symbol_rows),
        ),
        symbols=symbol_rows,
        accounts=account_rows,
        alerts=alerts,
        thresholds=RiskThresholds(
            concentration_limit_pct=thresholds.concentration_limit_pct,
            utilization_warn_pct=thresholds.utilization_warn_pct,
        ),
    )


async def _mark_for(session: AsyncSession, engine: MatchingEngine, symbol: str) -> Mark:
    book = engine.book(symbol)
    bid, ask = book.best_bid(), book.best_ask()
    if bid is not None and ask is not None:
        return Mark(price=(bid + ask) / 2, source="MID")
    last = (
        await session.execute(select(Trade.price).where(Trade.symbol == symbol).order_by(Trade.id.desc()).limit(1))
    ).scalar_one_or_none()
    if last is not None:
        return Mark(price=last, source="LAST_TRADE")
    return NO_MARK


async def load_overview(session: AsyncSession, engine: MatchingEngine) -> RiskOverview:
    symbol_rows = (await session.execute(select(Symbol).where(Symbol.active.is_(True)).order_by(Symbol.symbol))).scalars().all()
    account_rows = (await session.execute(select(Account).order_by(Account.id))).scalars().all()
    position_rows = (await session.execute(select(Position))).scalars().all()

    marks = {s.symbol: await _mark_for(session, engine, s.symbol) for s in symbol_rows}

    return compute_overview(
        symbols=[SymbolInfo(s.symbol, s.display_symbol) for s in symbol_rows],
        accounts=[
            AccountInfo(a.id, a.username, a.display_name, a.usd_balance, a.reserved_usd) for a in account_rows
        ],
        positions=[
            PositionInfo(p.account_id, p.symbol, p.net_qty, p.avg_cost, p.realized_pnl_today, p.realized_pnl_total)
            for p in position_rows
        ],
        marks=marks,
        thresholds=Thresholds(settings.risk_concentration_limit_pct, settings.risk_utilization_warn_pct),
        as_of=dt.datetime.now(dt.UTC),
    )
