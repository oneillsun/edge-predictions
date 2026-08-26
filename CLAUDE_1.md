# Working conventions for this repo

This project trades real money once Milestone 8 of PLAN.md is enabled. Follow
these rules on every turn, not just when it's convenient.

## Process

- Work one milestone from `PLAN.md` at a time. Stop after each and summarize
  what changed before starting the next, even if not explicitly asked to.
- Check off `- [ ]` items in `PLAN.md` as you complete them, in the same edit
  that implements them.
- Run the acceptance check listed for a milestone before considering it done.
  If you can't run it (e.g. it needs a real API key you don't have), say so
  explicitly instead of marking it done.
- Prefer small, reviewable diffs over large multi-file rewrites in one turn.

## Secrets and money safety

- Never hardcode API keys, tokens, or the Kalshi private key path — everything
  sensitive comes from `.env` (see `.env.example`), which is gitignored.
- Never commit `.env`, `*.pem`, or any file containing a real key.
- Default every "does this place a real order" flag to `false`/off. Flipping
  one to `true` is a decision for the human, not something to change while
  implementing an unrelated milestone.
- This project deliberately does not use a demo/sandbox environment — it
  authenticates against the user's real Kalshi account and the production API
  from Milestone 1 onward, including for market data. Because of that,
  through Milestone 7 the Kalshi client must expose **only read-only (GET)
  methods** (`get_markets`, `get_orderbook`, `get_positions`, etc.). Never
  add, import, or call an order-placement/cancel/amend method
  (`POST /portfolio/orders` or equivalent) anywhere in the code path before
  Milestone 8 explicitly wires it in behind `LIVE_TRADING_ENABLED`. With no
  sandbox to fall back on, this is the only thing standing between the
  codebase and a real order — treat it as a hard boundary, not a convention.
  If a task in an earlier milestone seems to need an order-placement call,
  stop and flag it instead of adding one.
- Position sizing and daily-loss caps (Milestone 4, Milestone 8) are enforced
  in code at the point of the decision/order, not only as config defaults.

## Code

- Python: FastAPI + SQLAlchemy + APScheduler backend, pytest for tests.
- Frontend: Vite + React + TypeScript.
- Write a test alongside any new signal module or engine logic — these are the
  pieces where a silent bug costs real money later.
- Log enough context on every decision (signal inputs, computed edge, sizing)
  that a human can reconstruct why a trade did or didn't happen, without
  reading code.

## When something in PLAN.md looks wrong

Kalshi's fee schedule, API base URLs, and auth details can change — PLAN.md
was written from third-party guides plus docs.kalshi.com's homepage, not a
full read of the current API reference. If something in the primary docs
contradicts PLAN.md, follow the primary docs and flag the discrepancy instead
of silently picking one.
