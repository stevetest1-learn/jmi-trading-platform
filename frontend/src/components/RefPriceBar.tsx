import { useNow } from "../hooks/useNow";
import { useTradingStore } from "../state/store";
import type { RefFeedStatus } from "../types";
import { formatNum, formatPct, formatSignedUsd, formatUsd } from "../utils/format";

// A silent feed (no pushes at all) must not keep looking live.
const STALE_AFTER_MS = 15_000;

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return <div className="ref-spark ref-spark--empty" />;
  const W = 180;
  const H = 48;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const x = (i: number) => (i / (points.length - 1)) * (W - 8) + 4;
  const y = (v: number) => H - 6 - ((v - min) / span) * (H - 12);
  const path = points.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const up = points[points.length - 1] >= points[0];
  const color = up ? "var(--buy)" : "var(--sell)";
  return (
    <svg className="ref-spark" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Recent Coinbase price">
      <path d={path} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(points.length - 1)} cy={y(points[points.length - 1])} r={2.8} fill={color} />
    </svg>
  );
}

const BADGE: Record<RefFeedStatus, { label: string; cls: string }> = {
  LIVE: { label: "LIVE", cls: "ref-badge--live" },
  STALE: { label: "STALE", cls: "ref-badge--stale" },
  DOWN: { label: "OFFLINE", cls: "ref-badge--down" },
};

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="ref-stat">
      <span className="ref-stat__label">{label}</span>
      <span className="ref-stat__value mono">{value}</span>
    </div>
  );
}

/** Real Coinbase price for the selected symbol. View only: it is not our order book. */
export function RefPriceBar({ symbol, displaySymbol }: { symbol: string; displaySymbol: string }) {
  const price = useTradingStore((s) => s.refPrices[symbol]);
  const history = useTradingStore((s) => s.refHistory[symbol]);
  const receivedAt = useTradingStore((s) => s.refReceivedAt[symbol]);
  const feedStatus = useTradingStore((s) => s.refStatus);
  const now = useNow();

  const status: RefFeedStatus =
    feedStatus === "LIVE" && receivedAt !== undefined && now - receivedAt > STALE_AFTER_MS ? "STALE" : feedStatus;
  const badge = BADGE[status];

  if (!price) {
    return (
      <section className="ref-bar ref-bar--empty">
        <span className="ref-bar__source">Coinbase · {displaySymbol}</span>
        <span className={`ref-badge ${badge.cls}`}>{badge.label}</span>
        <span className="ref-bar__hint">
          {status === "DOWN" ? "Coinbase prices unavailable. Trading is unaffected." : "Waiting for the first Coinbase price…"}
        </span>
      </section>
    );
  }

  const last = history?.at(-1);
  const prev = history?.at(-2);
  const tick = last !== undefined && prev !== undefined && last !== prev ? (last > prev ? "up" : "down") : null;
  const change = Number(price.change_24h_pct);
  const base = price.product_id.split("-")[0];
  const dim = status !== "LIVE" ? "ref-bar--dim" : "";

  return (
    <section className={`ref-bar ${dim}`} aria-label={`Coinbase ${displaySymbol} reference price`}>
      <div className="ref-bar__main">
        <div className="ref-bar__source">
          Coinbase · {displaySymbol}
          <span className={`ref-badge ${badge.cls}`}>{badge.label}</span>
        </div>
        <div className="ref-bar__price mono">
          {formatUsd(price.price, 2)}
          {tick && <span className={`ref-tick ref-tick--${tick}`}>{tick === "up" ? "▲" : "▼"}</span>}
        </div>
        <div className={`ref-bar__change mono ${change > 0 ? "pnl--pos" : change < 0 ? "pnl--neg" : ""}`}>
          {price.change_24h !== null && `${formatSignedUsd(price.change_24h)} `}
          {price.change_24h_pct !== null && `(${change > 0 ? "+" : ""}${formatPct(change, 2)}) `}
          <span className="ref-bar__window">24h</span>
        </div>
      </div>

      <div className="ref-bar__stats">
        <Stat label="Bid" value={price.bid ? formatUsd(price.bid, 2) : "-"} />
        <Stat label="Ask" value={price.ask ? formatUsd(price.ask, 2) : "-"} />
        <Stat label="Spread" value={price.spread ? formatUsd(price.spread, 2) : "-"} />
        <Stat label="24h high" value={price.high_24h ? formatUsd(price.high_24h, 2) : "-"} />
        <Stat label="24h low" value={price.low_24h ? formatUsd(price.low_24h, 2) : "-"} />
        <Stat label="24h volume" value={price.volume_24h ? `${formatNum(price.volume_24h, 0)} ${base}` : "-"} />
      </div>

      <Sparkline points={history ?? []} />
      <div className="ref-bar__note">Reference price from Coinbase. View only: orders trade on our own book.</div>
    </section>
  );
}
