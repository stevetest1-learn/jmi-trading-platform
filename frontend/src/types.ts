export type Side = "BUY" | "SELL";
export type OrderType = "LIMIT" | "MARKET";
export type OrderStatus = "NEW" | "PARTIALLY_FILLED" | "FILLED" | "CANCELED" | "REJECTED";

export interface SymbolInfo {
  symbol: string;
  display_symbol: string;
  base_asset: string;
  quote_asset: string;
  price_decimals: number;
  qty_decimals: number;
  tick_size: string;
  lot_size: string;
  active: boolean;
}

export interface OrderResponse {
  order_id: number;
  symbol: string;
  side: Side;
  order_type: OrderType;
  qty: string;
  price: string | null;
  leaves_qty: string;
  status: OrderStatus;
  reject_reason: string | null;
  fills: { trade_id: number; price: string; qty: string }[];
}

export interface PositionResponse {
  symbol: string;
  net_qty: string;
  reserved_qty: string;
  avg_cost: string;
  realized_pnl_today: string;
  realized_pnl_total: string;
  unrealized_pnl: string;
}

export interface BlotterRow {
  order_id: number;
  trade_id: number | null;
  symbol: string;
  side: Side;
  qty: string;
  price: string | null;
  ts: string;
  status: "FILL" | "REJECT";
  reject_reason?: string | null;
}

export interface DepthLevel {
  price: string;
  qty: string;
}

export interface OrderBookSnapshot {
  symbol: string;
  bids: DepthLevel[];
  asks: DepthLevel[];
}

export interface AccountInfo {
  account_id: number;
  username: string;
  display_name: string;
  usd_balance: string;
  reserved_usd: string;
  can_view_risk: boolean;
}

export type AlertSeverity = "CRITICAL" | "WARNING" | "INFO";

export interface RiskHolder {
  account_id: number;
  username: string;
  display_name: string;
  net_qty: string;
  notional: string | null;
  share_pct: string;
}

export interface RiskSymbol {
  symbol: string;
  display_symbol: string;
  mark_price: string | null;
  mark_source: "MID" | "LAST_TRADE" | "NONE";
  net_qty: string;
  notional: string;
  holders: RiskHolder[];
}

export interface RiskPosition {
  symbol: string;
  display_symbol: string;
  net_qty: string;
  avg_cost: string;
  mark_price: string | null;
  notional: string | null;
  unrealized_pnl: string | null;
  realized_pnl_today: string;
  realized_pnl_total: string;
  share_of_symbol_pct: string;
}

export interface RiskAccount {
  account_id: number;
  username: string;
  display_name: string;
  usd_balance: string;
  reserved_usd: string;
  utilization_pct: string;
  total_exposure: string;
  unrealized_pnl: string;
  realized_pnl_today: string;
  platform_share_pct: string;
  positions: RiskPosition[];
}

export interface RiskAlert {
  severity: AlertSeverity;
  code: string;
  message: string;
  account: string | null;
  symbol: string | null;
}

export interface RiskOverview {
  as_of: string;
  totals: {
    net_exposure: string;
    unrealized_pnl: string;
    realized_pnl_today: string;
    accounts: number;
    symbols: number;
  };
  symbols: RiskSymbol[];
  accounts: RiskAccount[];
  alerts: RiskAlert[];
  thresholds: { concentration_limit_pct: string; utilization_warn_pct: string };
}

export type RefFeedStatus = "LIVE" | "STALE" | "DOWN";

/** A Coinbase reference price. Display only; never feeds our book or marks. */
export interface RefPrice {
  symbol: string;
  product_id: string;
  price: string;
  bid: string | null;
  ask: string | null;
  spread: string | null;
  open_24h: string | null;
  high_24h: string | null;
  low_24h: string | null;
  volume_24h: string | null;
  change_24h: string | null;
  change_24h_pct: string | null;
  source_time: string | null;
  received_at: string;
}

export interface RefPriceSnapshot {
  status: RefFeedStatus;
  source: string;
  prices: RefPrice[];
}
