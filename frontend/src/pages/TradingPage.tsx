import { useEffect, useState } from "react";
import { Blotter } from "../components/Blotter";
import { OpenOrdersPanel } from "../components/OpenOrdersPanel";
import { OrderBookDepth } from "../components/OrderBookDepth";
import { OrderEntryTicket } from "../components/OrderEntryTicket";
import { PositionsPanel } from "../components/PositionsPanel";
import { RiskCockpit } from "../components/RiskCockpit";
import { SymbolSelector } from "../components/SymbolSelector";
import { useLiveConnection } from "../hooks/useLiveConnection";
import { useSymbols } from "../hooks/useSymbols";
import { useAuth } from "../state/AuthContext";
import { useTradingStore } from "../state/store";
import type { Side } from "../types";
import { formatNum } from "../utils/format";

type Tab = "trading" | "risk";

export function TradingPage() {
  const { account, token, logout } = useAuth();
  const canViewRisk = account?.can_view_risk ?? false;
  const [tab, setTab] = useState<Tab>("trading");
  // The server enforces access to /risk; this only decides what to render.
  const activeTab: Tab = tab === "risk" && canViewRisk ? "risk" : "trading";
  const symbols = useSymbols(true);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<{ price: string; side: Side } | null>(null);
  const liveUsdBalance = useTradingStore((s) => s.usdBalance);

  useEffect(() => {
    if (symbols.length > 0 && !selectedSymbol) setSelectedSymbol(symbols[0].symbol);
  }, [symbols, selectedSymbol]);

  // Seed the live balance from the login snapshot; WS position_update
  // pushes keep it current after that (see state/store.ts upsertPosition).
  useEffect(() => {
    if (account) useTradingStore.getState().setUsdBalance(account.usd_balance);
  }, [account]);

  const { connected } = useLiveConnection(
    token,
    symbols.map((s) => s.symbol),
    canViewRisk,
  );

  const displayBalance = liveUsdBalance ?? account?.usd_balance ?? null;

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__title">
          <span className="app-header__logo">JMI</span>
          <h1>JMI Crypto Trading GUI</h1>
        </div>
        {canViewRisk && (
          <nav className="main-tabs" aria-label="Sections">
            <button
              type="button"
              className={`main-tab ${activeTab === "trading" ? "main-tab--active" : ""}`}
              onClick={() => setTab("trading")}
            >
              Trading Engine
            </button>
            <button
              type="button"
              className={`main-tab ${activeTab === "risk" ? "main-tab--active" : ""}`}
              onClick={() => setTab("risk")}
            >
              Risk &amp; Exposure
            </button>
          </nav>
        )}
        <div className="app-header__controls">
          <span className={`status-dot ${connected ? "status-dot--live" : "status-dot--local"}`} title={connected ? "Live" : "Connecting…"} />
          {account && displayBalance !== null && (
            <span className="app-header__account">
              {account.display_name} · ${formatNum(displayBalance, 2)}
            </span>
          )}
          <button type="button" className="btn btn--ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <div className="tab-pane" hidden={activeTab !== "trading"}>
      <SymbolSelector symbols={symbols} selected={selectedSymbol} onSelect={setSelectedSymbol} />

      <main className="app-main">
        {selectedSymbol && (
          <>
            <OrderBookDepth
              symbol={selectedSymbol}
              onPriceClick={(price, side) => setPrefill({ price, side })}
            />
            <OrderEntryTicket symbol={selectedSymbol} prefill={prefill} />
          </>
        )}
        <div className="app-main__side">
          <OpenOrdersPanel />
          <PositionsPanel />
        </div>
      </main>

      <Blotter />
      </div>

      {activeTab === "risk" && account && (
        <main className="risk-main">
          <RiskCockpit currentUsername={account.username} />
        </main>
      )}
    </div>
  );
}
