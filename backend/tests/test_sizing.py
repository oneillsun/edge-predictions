from __future__ import annotations

import pytest

from app.engine import sizing


def test_kelly_fraction_positive_edge() -> None:
    # p=0.7 win chance, contract costs 0.5 -> f* = 0.7 - 0.3*0.5/0.5 = 0.4
    f = sizing.kelly_fraction(probability=0.7, price=0.5)
    assert f == pytest.approx(0.4)


def test_kelly_fraction_no_edge_is_negative_or_zero() -> None:
    # p=0.3 win chance at price 0.5 is a bad bet -> negative Kelly fraction
    f = sizing.kelly_fraction(probability=0.3, price=0.5)
    assert f < 0


def test_kelly_fraction_degenerate_price_returns_zero() -> None:
    assert sizing.kelly_fraction(probability=0.9, price=0.0) == 0.0
    assert sizing.kelly_fraction(probability=0.9, price=1.0) == 0.0


def test_capped_position_size_applies_kelly_cap() -> None:
    # raw kelly = 0.4; half-Kelly -> 0.2; hard cap (0.5) is well above that, so
    # the Kelly-scaled value is the binding constraint here, not the hard cap.
    size = sizing.capped_position_size(probability=0.7, price=0.5, kelly_fraction_cap=0.5, max_position_pct=0.5)
    assert size == pytest.approx(0.2)


def test_capped_position_size_hard_cap_wins_over_kelly() -> None:
    # raw kelly = 0.4; half-Kelly = 0.2; hard cap of 0.03 must win
    size = sizing.capped_position_size(probability=0.7, price=0.5, kelly_fraction_cap=0.5, max_position_pct=0.03)
    assert size == 0.03


def test_capped_position_size_negative_kelly_clamped_to_zero() -> None:
    size = sizing.capped_position_size(probability=0.3, price=0.5, kelly_fraction_cap=0.5, max_position_pct=0.03)
    assert size == 0.0
