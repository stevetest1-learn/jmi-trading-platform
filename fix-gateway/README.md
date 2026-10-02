# FIX Gateway (template)

A skeleton FIX 4.4 acceptor that lets an external counterparty connect over
FIX to **send in orders** and/or **receive market data**, translated into
calls against the same backend REST/WebSocket API the React GUI uses. It
shares no code with `../backend` — it's a genuine arms-length client of the
platform's public interfaces, which is the point: anyone could write an
equivalent gateway against the same API without touching the matching
engine's internals.

## What's implemented

| FIX MsgType | Tag 35 | Direction | Status |
|---|---|---|---|
| Logon | A | in/out | full session handshake |
| Heartbeat | 0 | in/out | keepalive |
| TestRequest | 1 | in/out | answered with an echoing Heartbeat |
| Logout | 5 | in/out | graceful teardown |
| NewOrderSingle | D | in | → `POST /orders`, replies with ExecutionReport |
| ExecutionReport | 8 | out | ack / fill / reject, mirrors the order's REST response |
| MarketDataRequest | V | in | → `GET /marketdata/{symbol}` snapshot |
| MarketDataSnapshotFullRefresh | W | out | full top-of-book reply to a request |
| MarketDataIncrementalRefresh | X | out | live updates, relayed from the backend's own WebSocket feed, while `SubscriptionRequestType=1` |

## What's a stub, on purpose

This is a **template**, not a certified FIX engine:

- **No ResendRequest handling.** A sequence-number gap is detected
  (`app/session.py`) but not acted on — a real implementation needs to ask
  for and honor resends.
- **`OrderCancelRequest` (F) and other message types are unimplemented.**
  `app/message_handlers.py` is the extension point.
- **`SenderCompID` → account mapping is a static dict** in `app/config.py`
  (`comp_id_to_credentials`). A real deployment needs a proper
  FIX-session-provisioning flow, not a hardcoded map.
- **MarketDataIncrementalRefresh always sends a full replace**, not true
  incremental deltas (`MDUpdateAction` is hardcoded to `0`/New).

## Running it locally

```bash
cd fix-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# needs the backend running (see ../backend/README or docker-compose.yml)
export BACKEND_BASE_URL=http://localhost:8000
export BACKEND_WS_URL=ws://localhost:8000/ws
python -m app.acceptor   # listens on :9878 by default
```

Run the tests (spins up its own acceptor instance against the real backend):

```bash
pytest tests/
```

## Extending it

To onboard a real counterparty: add their `SenderCompID` and a backend
account/credential to `comp_id_to_credentials` in `app/config.py`, point
them at this gateway's host:port, and they can send `NewOrderSingle` /
`MarketDataRequest` today. Everything else in the message-type table above
("What's a stub") is where a production integration would need real work.
