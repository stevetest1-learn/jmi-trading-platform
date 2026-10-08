import { useEffect, useRef, useState } from "react";
import { api, wsUrl } from "../api/rest";
import { useTradingStore } from "../state/store";

/**
 * One shared WebSocket connection per session. On (re)connect it subscribes
 * to the given symbols and re-syncs positions/open-orders/blotter over REST
 * -- WS deltas alone aren't assumed reliable across a reconnect gap.
 */
export function useLiveConnection(
  token: string | null,
  symbols: string[],
  canViewRisk: boolean,
): { connected: boolean } {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const symbolsKey = symbols.join(",");

  useEffect(() => {
    if (!token || symbols.length === 0) return;
    let cancelled = false;
    let attempt = 0;
    let retryHandle: ReturnType<typeof setTimeout> | undefined;

    const resync = async () => {
      try {
        const [positions, openOrders, blotter] = await Promise.all([
          api.positions(),
          api.openOrders(),
          api.blotter(),
        ]);
        if (cancelled) return;
        useTradingStore.getState().setPositions(positions);
        useTradingStore.getState().setOpenOrders(openOrders);
        useTradingStore.getState().setBlotter(blotter);
      } catch {
        // best effort; WS deltas keep arriving regardless
      }
      // Separate on purpose: Coinbase being unreachable must never block our own data.
      try {
        const snapshot = await api.refPrices();
        if (!cancelled) useTradingStore.getState().setRefSnapshot(snapshot);
      } catch {
        // the bar just shows "unavailable"
      }
    };

    const connect = () => {
      if (cancelled) return;
      const socket = new WebSocket(wsUrl(token));
      wsRef.current = socket;

      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
        socket.send(JSON.stringify({ type: "subscribe", payload: { symbols: symbolsKey.split(",") } }));
        if (canViewRisk) socket.send(JSON.stringify({ type: "subscribe_risk", payload: {} }));
        resync();
      };

      socket.onmessage = (event) => {
        const { type, payload } = JSON.parse(event.data);
        const store = useTradingStore.getState();
        switch (type) {
          case "book_snapshot":
            store.setOrderBook(payload);
            break;
          case "execution":
            store.prependBlotterRow({
              order_id: payload.order_id,
              trade_id: payload.trade_id,
              symbol: payload.symbol,
              side: payload.side,
              qty: payload.qty,
              price: payload.price,
              ts: new Date().toISOString(),
              status: "FILL",
            });
            break;
          case "reject":
            store.prependBlotterRow({
              order_id: payload.order_id,
              trade_id: null,
              symbol: payload.symbol,
              side: payload.side,
              qty: payload.qty,
              price: payload.price,
              ts: new Date().toISOString(),
              status: "REJECT",
              reject_reason: payload.reason,
            });
            break;
          case "order_ack":
            store.upsertOpenOrder(payload);
            break;
          case "position_update":
            store.upsertPosition(payload);
            break;
          case "risk_dirty":
            store.bumpRiskTick();
            break;
          case "ref_price":
            store.setRefPrice(payload);
            break;
          case "ref_status":
            store.setRefStatus(payload.status);
            break;
        }
      };

      socket.onclose = () => {
        setConnected(false);
        if (cancelled) return;
        attempt += 1;
        const delay = Math.min(1000 * 2 ** attempt, 10000);
        retryHandle = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (retryHandle) clearTimeout(retryHandle);
      wsRef.current?.close();
    };
  }, [token, symbolsKey, canViewRisk]);

  return { connected };
}
