---
title: Kalshi + Apify Trading Bot — Execution Plan
status: Milestone 5 implemented; paper-trading track record period not yet started
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
- Confirm current Kalshi fee schedule on docs.kalshi.com directly before
  Milestone 1, since this plan was written from third-party guides, not the
  primary docs, and fee details move.
- **Decision: no demo/sandbox.** This project authenticates against your real
  Kalshi account and production API
  (`https://external-api.kalshi.com/trade-api/v2` — confirmed against
  docs.kalshi.com on 2026-08-26; PLAN.md previously had the now-superseded
  `api.elections.kalshi.com` host) from Milestone 1 onward,
  including for market data. Through Milestone 7, the codebase must only ever
  call **read-only (GET) endpoints** — no order-placement, cancel, or amend
  calls exist anywhere in the code path until Milestone 8 explicitly wires
  them in behind `LIVE_TRADING_ENABLED`. Since there's no sandbox to fall back
  on, this read-only constraint is the sole thing preventing a real order
  before M8 — treat it as a hard boundary, not a convention (see CLAUDE_1.md).

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
- [x] `git init`, `.gitignore` (Python, Node, `.env`, `__pycache__`, `node_modules`)
- [x] `backend/`: FastAPI app with a `/healthz` endpoint, `pyproject.toml` with
      fastapi, uvicorn, httpx, cryptography, apify-client, sqlalchemy,
      apscheduler, pydantic-settings, pytest
- [x] `frontend/`: Vite + React + TypeScript scaffold, one placeholder page
- [x] `.env.example` with every variable Milestones 1–7 will need (see below)
- [x] `README.md`: how to run backend and frontend locally

Acceptance check: `uvicorn app.main:app --reload` serves `/healthz` → 200;
`npm run dev` in `frontend/` serves the placeholder page.

# Milestone 1 — Kalshi client (read-only first)

**Goal:** authenticated read access to markets/orderbook. No order placement yet.

Tasks:
- [x] `kalshi_private.pem` generated locally (2048-bit RSA), **never committed**
      — path referenced via `.env`, not hardcoded
- [x] Public key uploaded on kalshi.com, key ID stored in `.env`
- [x] `app/kalshi_client.py`: RSA-PSS request signing (timestamp + method +
      path, SHA-256, PSS padding — verify this against docs.kalshi.com, not
      just this plan) with the three `KALSHI-ACCESS-*` headers
- [x] `get_markets()` with cursor pagination, `get_orderbook(ticker)` — GET
      endpoints only; `kalshi_client.py` must not define or import any
      order-placement/cancel/amend method until Milestone 8
- [x] Unit tests mocking the signing function; one live smoke test (gated
      behind an env flag) that hits `/markets` against the live account —
      this touches your real account but only via GET, so no funds are ever
      at risk

Acceptance check: a script prints 10 live markets with their current yes/no
price, using your live Kalshi account credentials, no order ever submitted
(nothing changes in your Kalshi balance/positions).

# Milestone 2 — Persistence layer

**Goal:** every market snapshot and every signal gets stored, so later
milestones (backtest, journal) have data to work with from day one.

Tasks:
- [x] `app/db/models.py`: `MarketSnapshot`, `Signal`, `Trade`, `Alert` tables
      (SQLite for local dev, swappable to Postgres via `DATABASE_URL`)
- [x] `MarketSnapshot` stores ticker, timestamp, yes/no price, volume
- [x] `Signal` stores source (which Apify actor/module), ticker, estimated
      probability, raw payload (JSON), timestamp — this is what makes the later
      trade journal ("why did we trade this") possible
- [x] Alembic migration setup

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
- [x] `app/apify_client.py`: thin wrapper over `apify-client` (token from
      `.env`, `run_actor(actor_id, run_input)` → waits for completion → returns
      dataset items)
- [x] `app/signals/polymarket_arb_signal.py`: fetch same-event odds from
      Polymarket, diff against Kalshi price, store as a `Signal` row
- [x] `app/signals/news_signal.py`: run the news actor on a schedule, do a
      first-pass relevance/sentiment pass (an LLM call is fine here), store as
      a `Signal` row — implemented as a keyword-based heuristic instead of an
      LLM call, to avoid needing another API credential; swap-in point is
      `score_sentiment()` in `app/signals/news_signal.py`
- [x] `app/scheduler.py`: APScheduler job running both on an interval (start
      slow — every 15–30 min — tighten later if it proves useful)

Acceptance check: after running for ~1 hour against your live Kalshi account
(read-only), the `signal` table has rows from both sources for at least one
real market.

Verified 2026-08-27: `news_eth` reliably produces rows (3/3 sources scraped
successfully). `polymarket_arb` is correct and tested, but stored 0 live rows
at the time of testing — Polymarket's ETH strike ladder for the current event
tops out at $2,900 while ETH trades above $3,200, so no strike is close
enough to be an honest match (a `MAX_STRIKE_DIFF` sanity check intentionally
skips storing a "signal" from a mismatched strike rather than fabricating
one). This should self-resolve as Polymarket adds higher strikes or price
moves back into range — it's a live data-alignment gap between the two
platforms, not a code defect.

# Milestone 4 — Decision engine (no execution yet)

**Goal:** turn signals into a fee-aware "would this be a trade" decision,
logged but not acted on.

Tasks:
- [x] `app/engine/decision.py`: for each ticker with a recent signal, compare
      estimated probability vs. current Kalshi price; subtract Kalshi's fee
      (confirm the current fee formula on kalshi.com — historically fee scales
      with `price * (1 - price)`, peaking near $0.50, per kalshi-overview.md);
      flag as an "edge" only if it clears fees by a configurable margin —
      confirmed live via `GET /series/{ticker}`: fee = `ceil_to_cent(fee_multiplier
      * 0.07 * price * (1-price))`, fee_multiplier queried per-series (not
      assumed constant) since Kalshi can set it per series
- [x] `app/engine/sizing.py`: position sizing capped at 2–5% of paper bankroll
      per trade (configurable), Kelly-fraction-capped like PolyEdge Bot's
      approach — do not implement uncapped Kelly — `KELLY_FRACTION_CAP` (0.5,
      half-Kelly) scales raw Kelly before `MAX_POSITION_PCT_OF_BANKROLL` hard-caps it
- [x] Every decision (trade or no-trade) gets logged with its inputs — this is
      the backtest data — new `Decision` table (Milestone 4 migration)

Only `polymarket_arb` signals feed the engine — they carry a specific Kalshi
ticker plus a price snapshot; `news_eth` signals are category-level (ticker =
series) and aren't directly actionable by this first-pass engine.

Acceptance check: decision log shows entries with signal inputs, computed
edge, fee-adjusted edge, and sizing recommendation, for both "would trade" and
"edge too small" cases.

Verified 2026-08-27: ran `decision.run()` live (real `get_series` fee lookup,
fee_multiplier=1.0 for KXETH). Since Milestone 3's `polymarket_arb` signal
currently produces 0 live rows (Polymarket's strike ladder doesn't reach
ETH's current price — see Milestone 3 note), the two required cases were
demonstrated with two manually-inserted signals using **real live Kalshi
prices** but a fabricated `estimated_probability`, clearly labeled
`"demo": true` in the stored payload and removed after verification. Both
produced correct `Decision` rows (one `would_trade=true` sized to the 3%
hard cap, one `would_trade=false` with `size_pct_of_bankroll=null`). Full
unit test coverage in `tests/test_decision.py` exercises both branches
deterministically without relying on demo data.

# Milestone 5 — Paper trading loop

**Goal:** the full loop runs unattended against live Kalshi market data and
produces a track record before anything touches real money.

Tasks:
- [x] Decisions from Milestone 4 that clear the edge threshold get logged as
      simulated `Trade` rows (entry price, size, timestamp) against real-time
      live prices — no order is ever submitted to Kalshi; the simulation
      lives entirely in the `trade` table — `app/engine/paper_trading.py`,
      `open_paper_trades()`; skips a ticker that already has an open trade so
      a signal firing every cycle doesn't keep stacking positions
- [x] A settlement checker: when a market resolves, mark paper trades
      win/loss and compute simulated P&L — `settle_paper_trades()`, checks
      `GET /markets/{ticker}` (read-only) and settles once `status` is
      `determined`/`finalized` with a non-empty `result`
- [ ] Run for at least 1–2 weeks of wall-clock time before Milestone 8 — **not
      done yet, and can't be done inside a single coding session.** The
      scheduler (`app/scheduler.py`) now runs the full pipeline —
      signals → decisions → paper trades → settlement — every 20 minutes via
      `uvicorn app.main:app`. Leave it running (or deploy it somewhere it can
      run continuously) for 1–2 weeks before treating Milestone 8 as unblocked.

Acceptance check: a report script prints paper-trade count, win rate, and P&L
by signal source — this is what tells you whether news signals or arb signals
are actually worth anything, per-source, not just in aggregate.

Verified 2026-08-27: ran the full live pipeline once (real Kalshi, Polymarket,
and Apify calls) — 0 decisions/trades, consistent with Milestone 3/4's
finding that `polymarket_arb` currently has no close Polymarket match.
Demonstrated `open_paper_trades`/`settle_paper_trades` against **two real
already-finalized KXETH markets** (fetched live via `status=settled`) with
manually-inserted entry prices — clearly a demo, not the live pipeline's own
output, and removed after verification. `scripts/paper_trading_report.py`
correctly showed 2 trades, 50% win rate, -$0.60 total P&L for
`polymarket_arb`, matching hand-computed P&L exactly. Deterministic coverage
of both open and settle logic (including the skip-if-already-open and
unresolved-market cases) lives in `tests/test_paper_trading.py`.

# Milestone 6 — Dashboard

**Goal:** see what the bot sees, without reading the database directly.

Tasks:
- [ ] Backend: `GET /api/markets` (with latest signal + computed edge per
      market), `GET /api/trades` (paper trade history), `GET /api/alerts`
- [ ] Frontend: market list sorted by edge size, trade/paper-trade history
      table, basic P&L-by-source chart
- [ ] State-eligibility indicator per market (flag sports contracts in
      restricted states — see kalshi-overview.md Legal Status section)

Acceptance check: dashboard loads, shows live Kalshi markets sorted by edge,
and paper-trade history from Milestone 5 renders correctly.

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

# Addendum — BTC 15-min scalp strategy (paper-simulated, 2026-08-29)

**Goal:** user requested a module that buys "Yes" the instant each Kalshi
`KXBTC15M` (BTC up/down, 15-minute window) contract opens, polling every 5
seconds, with an automatic exit at +15% gain.

**This was explicitly scoped down before building.** As requested, it would
have meant adding real order-placement to `kalshi_client.py` — a hard
boundary CLAUDE_1.md says not to cross before Milestone 8, enforced by a
test asserting no such method exists. It also has no signal/edge check at
all (unconditional timed entry, not the Milestone 4 decision engine) and no
paper track record. Per user's decision, implemented as **paper-simulated
only** — same pattern as Milestone 5, no real order ever sent.

Tasks:
- [x] `app/strategies/btc_15min_scalp.py`: `poll()` — one tick does one of:
      open a paper "Yes" position on a not-yet-traded window (skips
      degenerate prices and 0-contract sizes), monitor an open position,
      close it early once `yes_bid` implies `BTC_15MIN_PROFIT_TARGET_PCT`
      gain over entry (paying both entry and exit taker fees via the same
      quadratic formula from `app/engine/decision.py`), or settle against
      Kalshi's real result if the window rolls over before the target hits.
- [x] Scheduled via `app/scheduler.py`'s `run_btc_15min_scalp_tick`, interval
      `BTC_15MIN_POLL_SECONDS` (default 5s — confirmed against
      docs.kalshi.com that Basic-tier accounts get ~20 req/s on GET
      endpoints, so 1-2 GET calls every 5s is not a rate-limit concern),
      `max_instances=1` + `coalesce=True` so a slow tick can't stack up
      overlapping runs.
- [x] Console visibility: `logging.basicConfig` added to `app/main.py` (this
      was previously missing entirely — no scheduler job's log lines, in any
      milestone, were actually visible before this) — every 5-second tick
      now prints its outcome to console.
- [ ] Frontend visibility — not built. User asked for "front end or console";
      console is done, a live dashboard view is still Milestone 6's job.

Uses a separate paper-money pool (`BTC_15MIN_POSITION_SIZE_USD`, default $20
per window) from `PAPER_BANKROLL_USD`, so this experimental strategy's
results don't mix with the Milestone 5 `polymarket_arb`/`news_eth` track
record — `paper_trading_report.py`'s per-source breakdown already separates
them (`source="btc_15min_scalp"`).

Verified live: ran the app for ~18s, watched it open a real paper position on
the actual open window (`KXBTC15M-26AUG292245-45`, entry $0.42, 47 contracts)
and correctly monitor it on the next tick (bid moved to $0.41, still below
target). That position was left running — it's genuine output of the system,
not demo data. Full deterministic test coverage of all branches (open,
monitor, profit-target exit, settlement-based exit, idempotency, degenerate
price) lives in `tests/test_btc_15min_scalp.py`.

**Still fully gated from real money** by the same rule as everything else:
no order-placement method exists in `kalshi_client.py`, and none should
until Milestone 8 is explicitly and deliberately turned on.

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
