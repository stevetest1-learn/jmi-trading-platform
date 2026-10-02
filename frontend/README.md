# JMI Crypto Trading GUI — frontend

React + TypeScript (Vite). See the [repo root README](../README.md) for how
this fits together with the backend, and how to run the whole stack.

```bash
npm install
npm run dev
```

Points at `http://localhost:8000` by default; override with
`VITE_API_BASE_URL` (see `.env.example`).

## Structure

- `src/state/` — `AuthContext` (login/session) and a Zustand `store` for
  live order-book/positions/open-orders/blotter state, fed by one shared
  WebSocket connection (`src/hooks/useLiveConnection.ts`).
- `src/components/` — `SymbolSelector`, `OrderBookDepth`, `OrderEntryTicket`,
  `OpenOrdersPanel`, `PositionsPanel`, `Blotter` (the bottom execution/reject
  panel).
- `src/api/rest.ts` — typed REST client; `src/types.ts` mirrors the
  backend's response shapes.
