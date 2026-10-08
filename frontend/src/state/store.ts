import { create } from "zustand";
import type {
  BlotterRow,
  OrderBookSnapshot,
  OrderResponse,
  PositionResponse,
  RefFeedStatus,
  RefPrice,
  RefPriceSnapshot,
} from "../types";

const REF_HISTORY_POINTS = 120; // about a minute of 500ms pushes, for the sparkline

interface TradingState {
  orderBooks: Record<string, OrderBookSnapshot>;
  positions: Record<string, PositionResponse>;
  openOrders: Record<number, OrderResponse>;
  blotter: BlotterRow[];
  usdBalance: string | null;
  /** Bumped when the server signals risk changed; the risk tab refetches on it. */
  riskTick: number;
  /** Coinbase reference prices (view only). */
  refPrices: Record<string, RefPrice>;
  refHistory: Record<string, number[]>;
  /** Our own clock at the moment each price arrived, to spot a silent feed. */
  refReceivedAt: Record<string, number>;
  refStatus: RefFeedStatus;

  setOrderBook: (snapshot: OrderBookSnapshot) => void;
  setPositions: (positions: PositionResponse[]) => void;
  upsertPosition: (position: PositionResponse & { usd_balance?: string | null }) => void;
  setOpenOrders: (orders: OrderResponse[]) => void;
  upsertOpenOrder: (order: Partial<OrderResponse> & { order_id: number }) => void;
  setBlotter: (rows: BlotterRow[]) => void;
  prependBlotterRow: (row: BlotterRow) => void;
  setUsdBalance: (balance: string) => void;
  bumpRiskTick: () => void;
  setRefPrice: (price: RefPrice) => void;
  setRefSnapshot: (snapshot: RefPriceSnapshot) => void;
  setRefStatus: (status: RefFeedStatus) => void;
  reset: () => void;
}

const OPEN_STATUSES = new Set(["NEW", "PARTIALLY_FILLED"]);

export const useTradingStore = create<TradingState>((set) => ({
  orderBooks: {},
  positions: {},
  openOrders: {},
  blotter: [],
  usdBalance: null,
  riskTick: 0,
  refPrices: {},
  refHistory: {},
  refReceivedAt: {},
  refStatus: "DOWN",

  setOrderBook: (snapshot) => set((s) => ({ orderBooks: { ...s.orderBooks, [snapshot.symbol]: snapshot } })),

  setPositions: (positions) => set({ positions: Object.fromEntries(positions.map((p) => [p.symbol, p])) }),

  upsertPosition: (position) =>
    set((s) => ({
      positions: { ...s.positions, [position.symbol]: position },
      usdBalance: position.usd_balance != null ? position.usd_balance : s.usdBalance,
    })),

  setOpenOrders: (orders) => set({ openOrders: Object.fromEntries(orders.map((o) => [o.order_id, o])) }),

  upsertOpenOrder: (order) =>
    set((s) => {
      const existing = s.openOrders[order.order_id];
      const merged = { ...existing, ...order } as OrderResponse;
      const next = { ...s.openOrders };
      if (OPEN_STATUSES.has(merged.status)) next[order.order_id] = merged;
      else delete next[order.order_id];
      return { openOrders: next };
    }),

  setBlotter: (rows) => set({ blotter: rows }),

  prependBlotterRow: (row) => set((s) => ({ blotter: [row, ...s.blotter].slice(0, 200) })),

  setUsdBalance: (balance) => set({ usdBalance: balance }),

  bumpRiskTick: () => set((s) => ({ riskTick: s.riskTick + 1 })),

  setRefPrice: (price) =>
    set((s) => ({
      refPrices: { ...s.refPrices, [price.symbol]: price },
      refReceivedAt: { ...s.refReceivedAt, [price.symbol]: Date.now() },
      refHistory: {
        ...s.refHistory,
        [price.symbol]: [...(s.refHistory[price.symbol] ?? []), Number(price.price)].slice(-REF_HISTORY_POINTS),
      },
    })),

  setRefSnapshot: (snapshot) => {
    snapshot.prices.forEach((p) => useTradingStore.getState().setRefPrice(p));
    set({ refStatus: snapshot.status });
  },

  setRefStatus: (status) => set({ refStatus: status }),

  reset: () =>
    set({
      orderBooks: {},
      positions: {},
      openOrders: {},
      blotter: [],
      usdBalance: null,
      refPrices: {},
      refHistory: {},
      refReceivedAt: {},
      refStatus: "DOWN",
    }),
}));
