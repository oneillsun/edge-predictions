from __future__ import annotations


def kelly_fraction(probability: float, price: float) -> float:
    """Fraction of bankroll for a binary contract costing `price` (pays $1 if it
    resolves in our favor, $0 otherwise), given estimated win probability.

    f* = p - (1-p) * price / (1 - price)

    Can be negative (no edge on this side) — callers should clamp to >= 0.
    """
    if price <= 0 or price >= 1:
        return 0.0
    return probability - (1 - probability) * price / (1 - price)


def capped_position_size(
    probability: float,
    price: float,
    kelly_fraction_cap: float,
    max_position_pct: float,
) -> float:
    """Kelly-fraction-capped, then hard-capped, position size as a fraction of bankroll.

    Never returns uncapped Kelly: the raw Kelly fraction is always scaled by
    kelly_fraction_cap (e.g. 0.5 for half-Kelly) and the result never exceeds
    max_position_pct regardless of what Kelly suggests.
    """
    raw_kelly = max(kelly_fraction(probability, price), 0.0)
    scaled = raw_kelly * kelly_fraction_cap
    return min(scaled, max_position_pct)
