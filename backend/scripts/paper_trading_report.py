"""Milestone 5 acceptance check: paper-trade count, win rate, and P&L by signal source.

Run from backend/: python scripts/paper_trading_report.py
"""

from collections import defaultdict

from app.config import settings
from app.db.models import Trade
from app.db.session import SessionLocal


def main() -> None:
    session = SessionLocal()
    try:
        trades = session.query(Trade).all()
    finally:
        session.close()

    by_source: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        by_source[trade.source or "unknown"].append(trade)

    print(
        f"btc_15min_scalp settings: ${settings.btc_15min_position_size_usd:.2f}/trade, "
        f"{settings.btc_15min_profit_target_pct:.0%} profit target"
    )
    print(f"Total paper trades: {len(trades)}")

    if not trades:
        print("No paper trades yet.")
        return

    earliest = min(trade.opened_at for trade in trades)
    print(f"Since: {earliest.strftime('%m/%d/%Y %H:%M:%S')} UTC\n")

    header = (
        f"{'source':<20} {'count':>6} {'settled':>8} {'wins':>6} {'losses':>7} "
        f"{'win_rate':>9} {'total_pnl':>11}"
    )
    print(header)
    print("-" * len(header))

    for source, source_trades in sorted(by_source.items()):
        settled = [t for t in source_trades if t.status == "settled"]
        wins = [t for t in settled if t.result == "win"]
        losses = [t for t in settled if t.result == "loss"]
        win_rate = (len(wins) / len(settled) * 100) if settled else float("nan")
        total_pnl = sum(t.pnl or 0.0 for t in settled)
        win_rate_str = f"{win_rate:.1f}%" if settled else "n/a"
        print(
            f"{source:<20} {len(source_trades):>6} {len(settled):>8} {len(wins):>6} {len(losses):>7} "
            f"{win_rate_str:>9} {total_pnl:>11.2f}"
        )


if __name__ == "__main__":
    main()
