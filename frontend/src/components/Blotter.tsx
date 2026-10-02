import { useTradingStore } from "../state/store";
import { formatNum } from "../utils/format";

function formatTime(ts: string): string {
  return new Date(ts).toLocaleTimeString(undefined, { hour12: false });
}

export function Blotter() {
  const rows = useTradingStore((s) => s.blotter);

  return (
    <section className="blotter">
      <div className="blotter__header">
        <h2>Executions</h2>
        <span className="blotter__count">{rows.length}</span>
      </div>

      {rows.length === 0 ? (
        <div className="blotter__empty">No executions yet — submit an order to trade.</div>
      ) : (
        <div className="blotter__table-wrap">
          <table className="blotter__table">
            <thead>
              <tr>
                <th>Order ID</th>
                <th>Trade ID</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Time of Trade</th>
                <th>Price</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr
                  key={`${r.order_id}-${r.trade_id ?? "reject"}-${i}`}
                  className={r.status === "REJECT" ? "row--reject" : r.side === "BUY" ? "row--buy" : "row--sell"}
                >
                  <td>{r.order_id}</td>
                  <td>{r.trade_id ?? "—"}</td>
                  <td>{r.symbol}</td>
                  <td className="blotter__side">{r.side}</td>
                  <td>{formatNum(r.qty)}</td>
                  <td>{formatTime(r.ts)}</td>
                  <td>{r.price !== null ? formatNum(r.price) : "—"}</td>
                  <td title={r.reject_reason ?? undefined}>{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
