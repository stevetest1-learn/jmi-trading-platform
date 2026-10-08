# JMI Crypto Trading GUI

A retail crypto trading platform: multiple accounts log in and trade
BTC/USD and ETH/USD against **each other** through a real price/time-priority
matching engine (not a simulated feed), with same-day (T+0) settlement,
live position/P&L tracking, a fills+rejects blotter, and a template for
external FIX connectivity.

> **Status:** a simulation that runs on a laptop. The FIX gateway is a template,
> and the AWS stack is written and validated with Terraform but has not been
> deployed. 45 backend tests plus a FIX end-to-end test pass.

## What it looks like

**Order book and ticket** (price/time priority, limit and market orders):

![Order book and ticket](linkedin-carousel/images/book.png)

**Risk & Exposure cockpit**, visible only to the market maker (every account's
positions, P&L and concentration, updated live):

![Risk and exposure cockpit](linkedin-carousel/images/cockpit.png)

**Alerts and the executions blotter** (fills and rejects):

![Risk alerts](linkedin-carousel/images/alerts.png)
![Executions blotter](linkedin-carousel/images/blotter.png)

A 6-slide walkthrough of the same material is in
[`linkedin-carousel/`](linkedin-carousel/), with the scripts that regenerate
it from a throwaway demo database.

## Architecture

```
backend/       Python (FastAPI) -- matching engine, REST + WebSocket API, Postgres
frontend/      React + TypeScript -- login, order book, order entry, positions, blotter
fix-gateway/   Python -- standalone FIX 4.4 acceptor template (see fix-gateway/README.md)
infra/         Terraform for AWS (written, not applied -- see below)
docker-compose.yml   local Postgres (+ optional backend container) for dev
```

The matching engine keeps its order book **in memory** and is single-writer
by design (see `backend/app/engine/engine.py`), durable state lives in
Postgres, and the frontend gets live updates over one shared WebSocket
connection per session. `fix-gateway/` talks to the backend only through its
public REST/WS API — no shared code — so it's a genuine template for how a
third party could integrate.

## Running it locally

**1. Postgres**

```bash
docker compose up -d postgres
```

**2. Backend**

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql+asyncpg://jmi:jmi_dev_password@localhost:5432/jmi_trading"
export JWT_SECRET="dev-only-secret-change-me"

python -m scripts.seed_demo_data   # creates BTCUSD/ETHUSD + 3 demo accounts
uvicorn app.main:app --reload      # http://localhost:8000
```

Demo accounts (password `demo1234` for all):
- `alice` / `bob` — $100k cash + 0.75 BTC + 55 ETH each (~$100k of crypto at
  seeding reference prices), so either can immediately BUY or SELL either
  symbol, including trading directly with each other, no `market_maker`
  required.
- `market_maker` — $5M cash + 50 BTC + 500 ETH, deep enough to keep absorbing
  demo activity. See the note on no-shorting below for why *someone* has to
  start with crypto in the first place.

Run the backend test suite (matching-engine unit tests + a full
seed→reject→cross→fill→position/P&L→blotter→EOD-settlement integration
test) against the same Postgres:

```bash
DATABASE_URL="postgresql+asyncpg://jmi:jmi_dev_password@localhost:5432/jmi_trading_test" \
  JWT_SECRET=test-secret pytest tests/
```

**3. Frontend**

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, points at http://localhost:8000 by default
```

Open it in two browser tabs/profiles logged in as two different demo
accounts to watch a real cross-account trade happen live.

**4. FIX gateway (optional)** — see [`fix-gateway/README.md`](fix-gateway/README.md).

## How trading works here

- **Order types**: LIMIT and MARKET, standard price/time priority. A LIMIT
  order rests on the book until matched; a MARKET order sweeps the book
  immediately and any unfilled remainder is canceled, not queued.
- **No short selling**: a SELL can't exceed your current position; a BUY
  can't exceed your available (unreserved) USD balance. Both are enforced
  even across multiple simultaneously-open orders (`reserved_usd` /
  `reserved_qty`), not just checked in isolation. Violations are
  **rejected**, not queued — and show up in the bottom blotter alongside
  fills.
- **Positions**: opening a BUY starts (or adds to) a weighted-average-cost
  position; a SELL realizes P&L against that average cost and reduces or
  closes the position. Unrealized P&L marks a long position against the
  current best bid.
- **Same-day settlement**: cash and positions update in real time on every
  fill (T+0). `backend/app/settlement/eod.py` is the formal end-of-day
  finalization — it snapshots the day's realized P&L per account/symbol and
  marks the day's trades `SETTLED`. Run it manually with
  `python -m scripts.run_eod_settlement`, or see `infra/eventbridge.tf` for
  the scheduled AWS version.
- **Why `market_maker` starts with BTC/ETH inventory**: since shorting is
  disallowed, crypto can only enter the system via a fill against an
  account that already holds it — someone has to start non-zero.

## Coinbase reference prices (view only)

Under the BTC/USD and ETH/USD tabs, a bar shows the **real** Coinbase price:
last, 24h change, bid/ask/spread, 24h high/low/volume and a sparkline, with a
LIVE / STALE / OFFLINE badge. It is for looking at the market only. Nothing
trades on Coinbase, and these prices never feed our order book, the marks
behind exposure and P&L, or any order.

- **One connection, many GUIs.** The backend holds a single connection to
  Coinbase's public `ticker` feed (no API key) and pushes to every GUI over the
  existing WebSocket. Ticks are coalesced to at most one push per symbol every
  500ms. `GET /refprices` returns the latest prices so a page can render
  immediately on load or reconnect.
- **Follows the symbols table.** A symbol's Coinbase product is
  `<base>-<quote>` (BTCUSD is BTC-USD), so adding a symbol Coinbase lists needs
  no code change. Restart the backend to pick up a new one.
- **Fails safe.** If Coinbase is unreachable the bar says OFFLINE and trading
  carries on untouched. The feed reconnects with exponential backoff (1s up to
  30s). A feed that connects but goes quiet turns STALE after 15s.
- **Config:** `COINBASE_ENABLED` (default true), `COINBASE_WS_URL`,
  `COINBASE_STALE_AFTER_SECONDS`, `COINBASE_PUSH_INTERVAL_MS`. The default is
  Coinbase's production public feed, which has real prices. Their sandbox feed
  (`wss://ws-feed-public.sandbox.exchange.coinbase.com`) serves made-up prices,
  so it is not the default.
- **Terms:** this is Coinbase's public market data. Check their terms before
  showing it to anyone beyond personal or internal use.
- **Note:** the demo order book is seeded around $60,000 BTC and $1,000 ETH, so
  it will not match the live Coinbase price.

## Risk & Exposure tab (market maker only)

Logging in as `market_maker` adds a second tab, **Risk & Exposure**, next to
**Trading Engine**. It shows every account's positions side by side:
platform-wide exposure per symbol (with who holds how much), per-account
cash, reserved cash and utilization, unrealized and realized P&L, and live
alerts. Other accounts never see the tab.

- **Enforced on the server, not just hidden.** `GET /risk/overview` returns
  403 for anyone not listed in `RISK_VIEWER_USERNAMES` (default
  `["market_maker"]`), and the WebSocket ignores `subscribe_risk` from them.
  `GET /accounts/me` reports `can_view_risk`, which is all the UI keys off.
- **Live.** After any accepted order, fill or cancel, the engine sends a
  `risk_dirty` nudge over the existing WebSocket and the tab refetches (about
  120ms later). A 15s poll is the fallback if the socket drops.
- **Mark price** is the mid of the best bid/ask when the book is two-sided,
  otherwise the last traded price. With neither, the symbol is shown as
  unvalued and raises a warning instead of being counted as zero. Shorting is
  disallowed, so net exposure equals gross exposure.
- **Alerts** are computed from current state (no history or acknowledgement):
  CRITICAL when one account holds more than `RISK_CONCENTRATION_LIMIT_PCT`
  (default 70) of a symbol's platform inventory; WARNING when reserved cash is
  at least `RISK_UTILIZATION_WARN_PCT` (default 80) of an account's cash, or a
  held symbol has no price.
- The aggregation maths is a pure function in `backend/app/risk/overview.py`,
  covered by `backend/tests/test_risk.py`.

Starting inventory is seeded at a cost basis equal to the seed's reference
prices ($60,000 BTC, $1,000 ETH), so unrealized P&L starts near zero and moves
with the market. Until the first trade or a two-sided book exists there is no
price, so exposure shows as unvalued and the cockpit warns about it. The seed
also leaves `market_maker` holding about 97% of each symbol, so both
concentration alerts fire from the start; that is the seed data, not a fault.

## Trade debug CSV

Every fill appends two rows (one per counterparty) to `trade_logs/YYYYMMDD.csv`
at the repo root — today's file is created automatically the first time a
trade happens that day. Columns: `timestamp, trade_id, symbol, account,
side, order_id, order_type, order_price, order_qty, fill_qty, fill_price,
realized_pnl_this_fill, realized_pnl_today_after, realized_pnl_total_after,
net_qty_after, avg_cost_after` — so for any trade you can see both sides'
own order details (price/size as originally submitted vs. what actually
executed) and the P&L impact at that moment, without cross-referencing the
DB. It's written only *after* the fill's DB transaction commits, so it can
never show a trade that got rolled back (`backend/app/reporting/trade_log.py`).

This is a plain local file — fine for local debugging, but on ECS it lives
on the task's ephemeral disk (lost on restart, not shared across replicas).
Point `TRADE_LOG_DIR` at somewhere durable (or swap in S3) if it needs to
persist there.

## Deploying to AWS (optional)

**Terraform is written but not applied** — you run it yourself so you can
review the plan and use credentials you're comfortable provisioning with.

> **Security note:** if `aws sts get-caller-identity` shows the account's
> **root** credentials, create an IAM user/role first — AWS strongly
> advises against using root for day-to-day operations like this.

> **Cost note:** unlike a pure serverless design, this is a
> **continuous-run-rate** architecture (RDS + ALB + Fargate running 24/7),
> because the matching engine needs a persistent, stateful process — a
> Lambda can't hold an in-memory order book between invocations. Rough
> ballpark: ~$50-65/month for the always-on core. `terraform destroy`
> between sessions if cost-sensitive. See `infra/main.tf`/`ecs.tf` for the
> full breakdown and the no-NAT-Gateway networking design that avoids the
> single biggest avoidable line item.

```bash
cd infra
terraform init
terraform plan    # review what will be created
terraform apply   # provisions real, billed AWS resources
```

Then build and push the backend image, and point the frontend at the ALB:

```bash
# from repo root
aws ecr get-login-password --region $(terraform -chdir=infra output -raw aws_region 2>/dev/null || echo us-east-1) \
  | docker login --username AWS --password-stdin $(terraform -chdir=infra output -raw ecr_backend_repository_url | cut -d/ -f1)
docker build -t $(terraform -chdir=infra output -raw ecr_backend_repository_url):latest backend
docker push $(terraform -chdir=infra output -raw ecr_backend_repository_url):latest

cd frontend
echo "VITE_API_BASE_URL=http://$(terraform -chdir=../infra output -raw alb_dns_name)" > .env
npm run build
aws s3 sync dist s3://$(terraform -chdir=../infra output -raw frontend_bucket_name) --delete
aws cloudfront create-invalidation \
  --distribution-id $(terraform -chdir=../infra output -raw cloudfront_distribution_id) --paths "/*"
```

Run the seed script once against the RDS instance (e.g. via `aws ecs
run-task` with the backend task definition and command overridden to
`python -m scripts.seed_demo_data`) before logging in.

### Tearing down

```bash
cd infra
terraform destroy
```
