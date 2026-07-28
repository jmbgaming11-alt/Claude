"""Kelly criterion sizing for binary Kalshi contracts.

For a YES contract bought at price `p` (dollars) that pays $1 on a win:
  - decimal odds b = (1/p) - 1  (net return per $1 staked if it wins)
  - Kelly fraction f* = (P*b - (1-P)) / b, where P is the model's win prob

f* is the fraction of bankroll to stake for log-growth-optimal sizing under
the *model's* probability. Full Kelly is aggressive and highly sensitive to
model error, so this project uses fractional Kelly (config.kelly_fraction,
default 0.25 = quarter-Kelly) to stay conservative against model
mis-calibration.
"""
from __future__ import annotations


def kelly_fraction(model_prob: float, price: float) -> float:
    """Return the full-Kelly fraction of bankroll to stake. Clipped to [0, 1]."""
    if price <= 0 or price >= 1:
        return 0.0
    b = (1.0 / price) - 1.0
    if b <= 0:
        return 0.0
    f_star = (model_prob * b - (1.0 - model_prob)) / b
    return max(0.0, min(1.0, f_star))


def fractional_kelly_stake(
    model_prob: float, price: float, bankroll: float, fraction: float
) -> float:
    """Stake in dollars using `fraction`-Kelly (e.g. 0.25 for quarter-Kelly)."""
    f_star = kelly_fraction(model_prob, price)
    return bankroll * f_star * fraction
