import { useRiskOverview } from "../hooks/useRiskOverview";
import type { RiskAccount, RiskAlert, RiskOverview, RiskSymbol } from "../types";
import { formatNum, formatPct, formatSignedUsd, formatUsd } from "../utils/format";

// One colour per account, assigned in exposure order so the bars, legend and
// table dots always agree.
const PALETTE = ["#4f8cff", "#f0a53c", "#a78bfa", "#2dd4bf", "#f472b6", "#94a3b8"];

const MARK_LABEL: Record<RiskSymbol["mark_source"], string> = {
  MID: "mid of best bid/ask",
  LAST_TRADE: "last trade",
  NONE: "no price",
};

function signClass(value: string | null): string {
  const n = Number(value);
  if (!value || !Number.isFinite(n) || n === 0) return "";
  return n > 0 ? "pnl--pos" : "pnl--neg";
}

function YouTag({ show }: { show: boolean }) {
  return show ? <span className="risk-you">you</span> : null;
}

function Kpis({ data }: { data: RiskOverview }) {
  const critical = data.alerts.filter((a) => a.severity === "CRITICAL").length;
  const warning = data.alerts.filter((a) => a.severity === "WARNING").length;
  const alertText = critical + warning === 0 ? "None" : [critical && `${critical} critical`, warning && `${warning} warning`].filter(Boolean).join(" · ");
  const alertClass = critical ? "pnl--neg" : warning ? "risk-warn" : "pnl--pos";

  return (
    <section className="risk-kpis">
      <div className="risk-kpi">
        <div className="risk-kpi__label">Platform net exposure</div>
        <div className="risk-kpi__value mono">{formatUsd(data.totals.net_exposure)}</div>
        <div className="risk-kpi__sub">{data.totals.symbols} symbols, at mark</div>
      </div>
      <div className="risk-kpi">
        <div className="risk-kpi__label">Unrealized P&amp;L</div>
        <div className={`risk-kpi__value mono ${signClass(data.totals.unrealized_pnl)}`}>
          {formatSignedUsd(data.totals.unrealized_pnl, 0)}
        </div>
        <div className="risk-kpi__sub">Across {data.totals.accounts} accounts</div>
      </div>
      <div className="risk-kpi">
        <div className="risk-kpi__label">Realized P&amp;L (today)</div>
        <div className={`risk-kpi__value mono ${signClass(data.totals.realized_pnl_today)}`}>
          {formatSignedUsd(data.totals.realized_pnl_today, 0)}
        </div>
        <div className="risk-kpi__sub">Resets at end-of-day settlement</div>
      </div>
      <div className="risk-kpi">
        <div className="risk-kpi__label">Active alerts</div>
        <div className={`risk-kpi__value ${alertClass}`}>{alertText}</div>
        <div className="risk-kpi__sub">Concentration, utilization, pricing</div>
      </div>
    </section>
  );
}

function ExposureBars({ data, colorOf }: { data: RiskOverview; colorOf: Map<number, string> }) {
  return (
    <div className="panel">
      <h2 className="panel__title">Exposure by symbol</h2>
      {data.symbols.map((s) => (
        <div className="risk-exposure" key={s.symbol}>
          <div className="risk-exposure__head">
            <span className="risk-exposure__sym">{s.display_symbol}</span>
            <span className="risk-exposure__amt mono">
              {formatNum(s.net_qty)} · {s.mark_price === null ? "unvalued" : formatUsd(s.notional)}
            </span>
          </div>
          <div className="risk-bar" role="img" aria-label={`${s.display_symbol} inventory by account`}>
            {s.holders.length === 0 && <div className="risk-bar__empty">No inventory</div>}
            {s.holders.map((h) => {
              const share = Number(h.share_pct);
              return (
                <div
                  key={h.account_id}
                  className="risk-bar__seg"
                  style={{ width: `${share}%`, background: colorOf.get(h.account_id) }}
                  title={`${h.display_name}: ${formatNum(h.net_qty)} (${formatPct(share)})`}
                >
                  {share >= 18 ? `${h.display_name} ${formatPct(share)}` : ""}
                </div>
              );
            })}
          </div>
          <div className="risk-exposure__mark">
            Mark {s.mark_price === null ? "—" : formatUsd(s.mark_price, 2)} · {MARK_LABEL[s.mark_source]}
          </div>
        </div>
      ))}
      <div className="risk-legend">
        {data.accounts.map((a) => (
          <span className="risk-legend__item" key={a.account_id}>
            <span className="risk-swatch" style={{ background: colorOf.get(a.account_id) }} />
            {a.display_name}
          </span>
        ))}
      </div>
    </div>
  );
}

function Alerts({ alerts }: { alerts: RiskAlert[] }) {
  return (
    <div className="panel">
      <h2 className="panel__title">
        Risk alerts <span className="risk-count">{alerts.length} open</span>
      </h2>
      {alerts.length === 0 ? (
        <div className="panel__empty">No limits breached.</div>
      ) : (
        alerts.map((al, i) => (
          <div className={`risk-alert risk-alert--${al.severity.toLowerCase()}`} key={`${al.code}-${al.account}-${al.symbol}-${i}`}>
            <span className="risk-alert__sev">{al.severity}</span>
            <span className="risk-alert__msg">{al.message}</span>
          </div>
        ))
      )}
    </div>
  );
}

function AccountsTable({
  data,
  colorOf,
  currentUsername,
}: {
  data: RiskOverview;
  colorOf: Map<number, string>;
  currentUsername: string;
}) {
  const limit = Number(data.thresholds.concentration_limit_pct);
  const warn = Number(data.thresholds.utilization_warn_pct);
  return (
    <div className="panel">
      <h2 className="panel__title">Accounts</h2>
      <div className="risk-scroll">
        <table className="panel__table risk-table">
          <thead>
            <tr>
              <th>Account</th>
              <th className="num">Cash</th>
              <th className="num">Reserved</th>
              <th className="num">Utilization</th>
              <th className="num">Exposure</th>
              <th className="num">Unrealized P&amp;L</th>
              <th className="num">Realized (today)</th>
              <th className="num">Platform share</th>
            </tr>
          </thead>
          <tbody>
            {data.accounts.map((a: RiskAccount) => {
              const share = Number(a.platform_share_pct);
              return (
                <tr key={a.account_id}>
                  <td>
                    <span className="risk-acct">
                      <span className="risk-swatch" style={{ background: colorOf.get(a.account_id) }} />
                      {a.display_name}
                      <YouTag show={a.username === currentUsername} />
                    </span>
                  </td>
                  <td className="num">{formatUsd(a.usd_balance)}</td>
                  <td className="num">{formatUsd(a.reserved_usd)}</td>
                  <td className={`num ${Number(a.utilization_pct) >= warn ? "risk-warn" : ""}`}>{formatPct(a.utilization_pct)}</td>
                  <td className="num">{formatUsd(a.total_exposure)}</td>
                  <td className={`num ${signClass(a.unrealized_pnl)}`}>{formatSignedUsd(a.unrealized_pnl)}</td>
                  <td className={`num ${signClass(a.realized_pnl_today)}`}>{formatSignedUsd(a.realized_pnl_today)}</td>
                  <td className="num">
                    <span className="risk-share">
                      <span className="risk-share__track">
                        <span
                          className={`risk-share__fill ${share > limit ? "risk-share__fill--hot" : ""}`}
                          style={{ width: `${Math.min(share, 100)}%` }}
                        />
                      </span>
                      {formatPct(share)}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PositionsTable({ data, currentUsername }: { data: RiskOverview; currentUsername: string }) {
  const rows = data.accounts.flatMap((a) => a.positions.map((p) => ({ a, p })));
  return (
    <div className="panel">
      <h2 className="panel__title">Positions by account</h2>
      {rows.length === 0 ? (
        <div className="panel__empty">No positions held.</div>
      ) : (
        <div className="risk-scroll">
          <table className="panel__table risk-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Symbol</th>
                <th className="num">Net qty</th>
                <th className="num">Avg cost</th>
                <th className="num">Mark</th>
                <th className="num">Notional</th>
                <th className="num">Unrealized P&amp;L</th>
                <th className="num">Realized (today)</th>
                <th className="num">Share of symbol</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ a, p }) => (
                <tr key={`${a.account_id}-${p.symbol}`}>
                  <td>
                    {a.display_name}
                    <YouTag show={a.username === currentUsername} />
                  </td>
                  <td>{p.display_symbol}</td>
                  <td className="num">{formatNum(p.net_qty)}</td>
                  <td className="num">{formatUsd(p.avg_cost, 2)}</td>
                  <td className="num">{p.mark_price === null ? "—" : formatUsd(p.mark_price, 2)}</td>
                  <td className="num">{p.notional === null ? "—" : formatUsd(p.notional)}</td>
                  <td className={`num ${signClass(p.unrealized_pnl)}`}>
                    {p.unrealized_pnl === null ? "—" : formatSignedUsd(p.unrealized_pnl)}
                  </td>
                  <td className={`num ${signClass(p.realized_pnl_today)}`}>{formatSignedUsd(p.realized_pnl_today)}</td>
                  <td className="num">{formatPct(p.share_of_symbol_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function RiskCockpit({ currentUsername }: { currentUsername: string }) {
  const { data, error, fetchedAt } = useRiskOverview(true);

  if (!data) {
    return (
      <div className="risk">
        <div className="panel__empty">{error ? `Could not load risk data: ${error}` : "Loading risk data…"}</div>
      </div>
    );
  }

  const colorOf = new Map(data.accounts.map((a, i) => [a.account_id, PALETTE[i % PALETTE.length]]));

  return (
    <div className="risk">
      <div className="risk-meta">
        <span className="risk-meta__live">
          <span className={`status-dot ${error ? "status-dot--local" : "status-dot--live"}`} />
          {error ? "Reconnecting…" : "Live"}
          {fetchedAt && <> · updated <span className="mono">{fetchedAt.toLocaleTimeString(undefined, { hour12: false })}</span></>}
        </span>
        <span className="risk-meta__note">
          Every account, platform-wide. Visible to risk viewers only. Exposure is valued at the mark shown per symbol.
        </span>
      </div>

      <Kpis data={data} />

      <div className="risk-split">
        <ExposureBars data={data} colorOf={colorOf} />
        <Alerts alerts={data.alerts} />
      </div>

      <AccountsTable data={data} colorOf={colorOf} currentUsername={currentUsername} />
      <PositionsTable data={data} currentUsername={currentUsername} />
    </div>
  );
}
