---
title: Kalshi + Apify Trading Bot — Execution Plan
status: draft, not yet started
last_updated: 2026-08-26
source: claude/kalshi-apify-app-ideas.md (Market & betting predictions project)
---

# How to run this plan

This file is written to be dropped at the root of a fresh repo and handed to
Claude Code (`claude` in a VS Code integrated terminal), not read passively.

1. Create the project folder, put this `PLAN.md`, `CLAUDE.md`, and `.env.example`
   at its root, `git init`, first commit.
2. Open the folder in VS Code, open the integrated terminal, run `claude`.
3. Prompt it with something like: *"Read PLAN.md and CLAUDE.md. Implement
   Milestone 0 only. Stop and show me a summary + diff before continuing to
   Milestone 1."*
4. Review the diff, run the acceptance check listed for that milestone, commit,
   then move to the next milestone the same way — one milestone per Claude Code
   turn, not the whole plan in one shot. This keeps you in the loop on the parts
   that matter most (auth, order placement, position sizing) instead of
   discovering a problem after everything is wired together.
5. Do not skip ahead to Milestone 8 (live execution). Everything before it is a
   prerequisite specifically because this trades real money once it's live.

Each milestone below lists: goal, concrete tasks, files touched, and an
acceptance check you (or Claude Code) can actually run to confirm it's done —
not just "looks right."

# Prerequisites

- Kalshi account, KYC'd, with API access enabled in account settings.
- Kalshi RSA keypair generated and public key uploaded (Milestone 1 covers the
  exact commands) — do this on kalshi.com before Milestone 1.
- Apify account + API token (console.apify.com → Settings → Integrations).
- Python 3.11+, Node 20+, git, VS Code, Claude Code CLI installed.
- Confirm current Kalshi fee schedule and whether the demo/sandbox base URL
  differs from production (`https://api.elections.kalshi.com/trade-api/v2`) —
  check docs.kalshi.com directly before Milestone 1, since this plan was written
  from third-party guides, not the primary docs, and fee/URL details move.

# Repo structure (target)

```
kalshi-apify-bot/
  PLAN.md
  CLAUDE.md
  .env.example
  README.md
  backend/
    pyproject.toml
    app/
      config.py
      kalshi_client.py
      apify_client.py
      signals/
        news_signal.py
        polymarket_arb_signal.py
      engine/
        decision.py
        sizing.py
      db/
        models.py
        session.py
      scheduler.py
      main.py
    tests/
  frontend/
    (Vite + React dashboard)
  scripts/
    seed_demo.py
  docs/
    kalshi-overview.md
    kalshi-apify-app-ideas.md
```

# Milestone 0 — Scaffolding

**Goal:** empty-but-runnable skeleton, no business logic yet.

Tasks:
- [ ] `git init`, `.gitignore` (Python, Node, `.env`, `__pycache__`, `node_modules`)
- [ ] `backend/`: FastAPI app with a `/healthz` endpoint, `pyproject.toml` with
      fastapi, uvicorn, httpx, cryptography, apify-client, sqlalchemy,
      apscheduler, pydantic-settings, pytest
- [ ] `frontend/`: Vite + React + TypeScript scaffold, one placeholder page
- [ ] `.env.example` with every variable Milestones 1–7 will need (see below)
- [ ] `README.md`: how to run backend and frontend locally

Acceptance check: `uvicorn app.main:app --reload` serves `/healthz` → 200;
`npm run dev` in `frontend/` serves the placeholder page.

# Milestone 1 — Kalshi client (read-only first)

**Goal:** authenticated read access to markets/orderbook. No order placement yet.

Tasks:
- [ ] `kalshi_private.pem` generated locally (2048-bit RSA), **never committed**
      — path referenced via `.env`, not hardcoded
- [ ] Public key uploaded on kalshi.com, key ID stored in `.env`
- [ ] `app/kalshi_client.py`: RSA-PSS request signing (timestamp + method +
      path, SHA-256, PSS padding — verify this against docs.kalshi.com, not
      just this plan) with the three `KALSHI-ACCESS-*` headers
- [ ] `get_markets()` with cursor pagination, `get_orderbook(ticker)`
- [ ] Confirm and record whether Kalshi's demo/sandbox environment is a
      separate base URL or a account-level "demo mode" — use whichever is
      genuinely isolated from real money for all testing through Milestone 7
- [ ] Unit tests mocking the signing function; one live smoke test (gated behind
      an env flag) that hits `/markets` against demo/sandbox only

Acceptance check: a script prints 10 live markets with their current yes/no
price, hitting demo/sandbox, no real funds touched.

# Milestone 2 — Persistence layer

**Goal:** every market snapshot and every signal gets stored, so later
milestones (backtest, journal) have data to work with from day one.

Tasks:
- [ ] `app/db/models.py`: `MarketSnapshot`, `Signal`, `Trade`, `Alert` tables
      (SQLite for local dev, swappable to Postgres via `DATABASE_URL`)
- [ ] `MarketSnapshot` stores ticker, timestamp, yes/no price, volume
- [ ] `Signal` stores source (which Apify actor/module), ticker, estimated
      probability, raw payload (JSON), timestamp — this is what makes the later
      trade journal ("why did we trade this") possible
- [ ] Alembic migration setup

Acceptance check: running the Milestone 1 market-fetch script also writes rows
to `market_snapshot`; inspect with a `sqlite3` query.

# Milestone 3 — First Apify signal module

**Goal:** one working signal end-to-end, not all eight from the ideas doc.
Start with the two cheapest to validate:

1. **Polymarket cross-reference** (no Apify actor needed if Polymarket has a
   public API already used by PolyEdge Bot — reuse that client directly instead
   of scraping; this is the fastest signal to stand up and ties directly to the
   arbitrage strategy).
2. **News/event scraping** via an Apify actor (`website-content-crawler` or
   similar) pointed at 2–3 sources relevant to whatever market category you
   start with.

Tasks:
- [ ] `app/apify_client.py`: thin wrapper over `apify-client` (token from
      `.env`, `run_actor(actor_id, run_input)` → waits for completion → returns
      dataset items)
- [ ] `app/signals/polymarket_arb_signal.py`: fetch same-event odds from
      Polymarket, diff against Kalshi price, store as a `Signal` row
- [ ] `app/signals/news_signal.py`: run the news actor on a schedule, do a
      first-pass relevance/sentiment pass (an LLM call is fine here), store as
      a `Signal` row
- [ ] `app/scheduler.py`: APScheduler job running both on an interval (start
      slow — every 15–30 min — tighten later if it proves useful)

Acceptance check: after running for ~1 hour against demo/sandbox, the `signal`
table has rows from both sources for at least one real market.

# Milestone 4 — Decision engine (no execution yet)

**Goal:** turn signals into a fee-aware "would this be a trade" decision,
logged but not acted on.

Tasks:
- [ ] `app/engine/decision.py`: for each ticker with a recent signal, compare
      estimated probability vs. current Kalshi price; subtract Kalshi's fee
      (confirm the current fee formula on kalshi.com — historically fee scales
      with `price * (1 - price)`, peaking near $0.50, per kalshi-overview.md);
      flag as an "edge" only if it clears fees by a configurable margin
- [ ] `app/engine/sizing.py`: position sizing capped at 2–5% of paper bankroll
      per trade (configurable), Kelly-fraction-capped like PolyEdge Bot's
      approach — do not implement uncapped Kelly
- [ ] Every decision (trade or no-trade) gets logged with its inputs — this is
      the backtest data

Acceptance check: decision log shows entries with signal inputs, computed
edge, fee-adjusted edge, and sizing recommendation, for both "would trade" and
"edge too small" cases.

# Milestone 5 — Paper trading loop

**Goal:** the full loop runs unattended against demo/sandbox and produces a
track record before anything touches real money.

Tasks:
- [ ] Decisions from Milestone 4 that clear the edge threshold get logged as
      simulated `Trade` rows (entry price, size, timestamp) — no real order
      placed yet, demo/sandbox only if you want a live-odds paper mode
- [ ] A settlement checker: when a market resolves, mark paper trades
      win/loss and compute simulated P&L
- [ ] Run for at least 1–2 weeks of wall-clock time before Milestone 8

Acceptance check: a report script prints paper-trade count, win rate, and P&L
by signal source — this is what tells you whether news signals or arb signals
are actually worth anything, per-source, not just in aggregate.

# Milestone 6 — Dashboard

**Goal:** see what the bot sees, without reading the database directly.

Tasks:
- [ ] Backend: `GET /api/markets` (with latest signal + computed edge per
      market), `GET /api/trades` (paper trade history), `GET /api/alerts`
- [ ] Frontend: market list sorted by edge size, trade/paper-trade history
      table, basic P&L-by-source chart
- [ ] State-eligibility indicator per market (flag sports contracts in
      restricted states — see kalshi-overview.md Legal Status section)

Acceptance check: dashboard loads, shows live demo/sandbox markets sorted by
edge, and paper-trade history from Milestone 5 renders correctly.

# Milestone 7 — Alerting + approval queue

**Goal:** semi-auto workflow — the bot proposes, you decide.

Tasks:
- [ ] Threshold-based alert (edge above X, or a tracked signal source fires) →
      push/Slack/email (pick one to start)
- [ ] Approval queue in the dashboard: pending "would-trade" decisions with
      rationale, one-click approve/reject
- [ ] Approved decisions still only place **paper** trades until Milestone 8 is
      explicitly turned on

Acceptance check: triggering a decision that clears the edge threshold produces
an alert and a queue entry within the target latency (define one, e.g. under 2
minutes from signal to alert).

# Milestone 8 — Live execution (explicit opt-in, gated)

**Goal:** real order placement, behind a hard kill switch, only after
Milestone 5's paper track record is good enough that you've decided to trust
it.

Tasks:
- [ ] `POST /portfolio/orders` wired into `kalshi_client.py`, limit orders only
      to start (no market orders)
- [ ] A single `LIVE_TRADING_ENABLED` env flag, default `false`, checked at the
      point of order submission — not just at startup
- [ ] Hard position-size and daily-loss caps enforced in code, not just as
      config values someone could forget to set
- [ ] State-eligibility check blocks order submission for restricted
      categories/states rather than just flagging them in the UI
- [ ] Manual approval required per trade initially (reuse Milestone 7's queue);
      revisit full-auto only after live results validate the paper results

Acceptance check: with `LIVE_TRADING_ENABLED=false`, an approved decision does
**not** place a real order (verify against your Kalshi account balance/
positions directly, not just app logs). Only flip the flag once you've verified
that.

# Not in this plan (deliberately deferred)

- The other six Apify signal modules from the ideas doc (sentiment, SERP
  trends, sportsbook lines, econ calendar, weather, resolution-source
  monitoring) — add them one at a time after Milestone 5 shows the first two
  are worth the infrastructure, following the same pattern as Milestone 3.
- Sharing dashboard components with PolyEdge Bot — worth doing once both are
  independently working, not before.
- Full-auto execution — Milestone 8 stays manual-approval by design until you
  have live (not paper) results to justify removing the human step.

Sources:
- [Kalshi API Documentation](https://docs.kalshi.com/welcome)
- [Kalshi API Python Guide: RSA-PSS Signing](https://predictandprofit.io/blog/kalshi-api-python-guide)
- [Apify Python Client — Getting Started](https://docs.apify.com/api/client/python/docs/overview/getting-started)
- [apify-client-python (GitHub)](https://github.com/apify/apify-client-python)
