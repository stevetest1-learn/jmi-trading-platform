import { api } from "../api/rest";
import { useTradingStore } from "../state/store";
import { formatNum } from "../utils/format";

export function OpenOrdersPanel() {
  const openOrdersMap = useTradingStore((s) => s.openOrders);
  const openOrders = Object.values(openOrdersMap);

  const handleCancel = async (orderId: number) => {
    try {
      await api.cancelOrder(orderId);
    } catch {
      // WS order_ack (or a manual refresh) will reconcile state either way
    }
  };

  return (
    <div className="panel">
      <h2 className="panel__title">Open Orders</h2>
      {openOrders.length === 0 ? (
        <div className="panel__empty">No open orders</div>
      ) : (
        <table className="panel__table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Symbol</th>
              <th>Side</th>
              <th>Type</th>
              <th>Price</th>
              <th>Leaves</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {openOrders.map((o) => (
              <tr key={o.order_id} className={o.side === "BUY" ? "row--buy" : "row--sell"}>
                <td>{o.order_id}</td>
                <td>{o.symbol}</td>
                <td>{o.side}</td>
                <td>{o.order_type}</td>
                <td>{o.price ? formatNum(o.price) : "MKT"}</td>
                <td>{formatNum(o.leaves_qty)}</td>
                <td>
                  <button type="button" className="btn btn--ghost btn--small" onClick={() => handleCancel(o.order_id)}>
                    Cancel
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
