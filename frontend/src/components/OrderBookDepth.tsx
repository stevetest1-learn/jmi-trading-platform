import { useTradingStore } from "../state/store";
import { formatNum } from "../utils/format";

interface Props {
  symbol: string;
  onPriceClick: (price: string, side: "BUY" | "SELL") => void;
}

export function OrderBookDepth({ symbol, onPriceClick }: Props) {
  const book = useTradingStore((s) => s.orderBooks[symbol]);

  if (!book) {
    return <div className="depth-panel depth-panel--empty">Connecting…</div>;
  }

  return (
    <div className="depth-panel">
      <div className="depth-panel__header">
        <span>Price</span>
        <span>Qty</span>
      </div>
      <div className="depth-panel__asks">
        {[...book.asks].reverse().map((lvl) => (
          <button
            key={lvl.price}
            type="button"
            className="depth-panel__row depth-panel__row--ask"
            onClick={() => onPriceClick(lvl.price, "BUY")}
          >
            <span>{formatNum(lvl.price)}</span>
            <span>{formatNum(lvl.qty)}</span>
          </button>
        ))}
        {book.asks.length === 0 && <div className="depth-panel__row depth-panel__row--empty">no asks</div>}
      </div>
      <div className="depth-panel__spread">
        {book.bids[0] && book.asks[0]
          ? `spread ${(Number(book.asks[0].price) - Number(book.bids[0].price)).toFixed(2)}`
          : "—"}
      </div>
      <div className="depth-panel__bids">
        {book.bids.map((lvl) => (
          <button
            key={lvl.price}
            type="button"
            className="depth-panel__row depth-panel__row--bid"
            onClick={() => onPriceClick(lvl.price, "SELL")}
          >
            <span>{formatNum(lvl.price)}</span>
            <span>{formatNum(lvl.qty)}</span>
          </button>
        ))}
        {book.bids.length === 0 && <div className="depth-panel__row depth-panel__row--empty">no bids</div>}
      </div>
    </div>
  );
}
