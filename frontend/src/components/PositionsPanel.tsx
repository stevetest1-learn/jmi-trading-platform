import { useTradingStore } from "../state/store";
import { formatNum } from "../utils/format";

function pnlClass(value: string): string {
  const n = Number(value);
  if (n > 0) return "pnl--pos";
  if (n < 0) return "pnl--neg";
  return "";
}

export function PositionsPanel() {
  const positionsMap = useTradingStore((s) => s.positions);
  const positions = Object.values(positionsMap);

  return (
    <div className="panel">
      <h2 className="panel__title">Positions</h2>
      {positions.length === 0 ? (
        <div className="panel__empty">No open positions</div>
      ) : (
        <table className="panel__table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Net Qty</th>
              <th>Avg Cost</th>
              <th>Unrealized</th>
              <th>Realized (Today)</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.symbol}>
                <td>{p.symbol}</td>
                <td>{formatNum(p.net_qty)}</td>
                <td>{formatNum(p.avg_cost)}</td>
                <td className={pnlClass(p.unrealized_pnl)}>{formatNum(p.unrealized_pnl, 2)}</td>
                <td className={pnlClass(p.realized_pnl_today)}>{formatNum(p.realized_pnl_today, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
