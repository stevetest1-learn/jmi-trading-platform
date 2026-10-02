import { useEffect, useState } from "react";
import { api } from "../api/rest";
import type { OrderType, Side } from "../types";

interface Props {
  symbol: string;
  prefill: { price: string; side: Side } | null;
}

export function OrderEntryTicket({ symbol, prefill }: Props) {
  const [side, setSide] = useState<Side>("BUY");
  const [orderType, setOrderType] = useState<OrderType>("LIMIT");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ text: string; kind: "ok" | "error" } | null>(null);

  useEffect(() => {
    if (!prefill) return;
    setSide(prefill.side);
    setPrice(prefill.price);
    setOrderType("LIMIT");
  }, [prefill]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);
    try {
      const result = await api.submitOrder({
        symbol,
        side,
        order_type: orderType,
        qty,
        price: orderType === "LIMIT" ? price : null,
      });
      if (result.status === "REJECTED") {
        setMessage({ text: `Rejected: ${result.reject_reason}`, kind: "error" });
      } else {
        setMessage({ text: `${result.status} — order #${result.order_id}`, kind: "ok" });
        setQty("");
      }
    } catch (err) {
      setMessage({ text: String(err), kind: "error" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="order-ticket" onSubmit={handleSubmit}>
      <div className="order-ticket__side-toggle">
        <button
          type="button"
          className={`side-btn side-btn--buy ${side === "BUY" ? "side-btn--active" : ""}`}
          onClick={() => setSide("BUY")}
        >
          BUY
        </button>
        <button
          type="button"
          className={`side-btn side-btn--sell ${side === "SELL" ? "side-btn--active" : ""}`}
          onClick={() => setSide("SELL")}
        >
          SELL
        </button>
      </div>

      <label className="order-ticket__field">
        Type
        <select value={orderType} onChange={(e) => setOrderType(e.target.value as OrderType)}>
          <option value="LIMIT">LIMIT</option>
          <option value="MARKET">MARKET</option>
        </select>
      </label>

      <label className="order-ticket__field">
        Qty
        <input type="number" step="any" min="0" value={qty} onChange={(e) => setQty(e.target.value)} required />
      </label>

      <label className="order-ticket__field">
        Price
        <input
          type="number"
          step="any"
          min="0"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          disabled={orderType === "MARKET"}
          required={orderType === "LIMIT"}
        />
      </label>

      <button type="submit" className={`btn btn--submit btn--${side.toLowerCase()}`} disabled={submitting}>
        {submitting ? "Submitting…" : `${side} ${symbol}`}
      </button>

      {message && <div className={`order-ticket__message order-ticket__message--${message.kind}`}>{message.text}</div>}
    </form>
  );
}
