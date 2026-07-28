"""Step 4: render the betting recommendation sheet and allocation summary."""
from __future__ import annotations

import csv
from pathlib import Path

from pga_cutline_bot.models import BetRecommendation


def render_console(recommendations: list[BetRecommendation], budget: float, tournament_name: str) -> str:
    lines = [f"=== Cut-Line Betting Slip: {tournament_name} ===", ""]
    if not recommendations:
        lines.append("No +EV opportunities met the minimum edge threshold this week. No bets recommended.")
        return "\n".join(lines)

    straight_total = sum(r.stake for r in recommendations if r.bet_type == "straight")
    parlay_total = sum(r.stake for r in recommendations if r.bet_type == "parlay")

    for i, rec in enumerate(recommendations, 1):
        names = ", ".join(leg.prediction.name for leg in rec.legs)
        lines.append(f"[{i}] {rec.bet_type.upper()}: {names}")
        for leg in rec.legs:
            lines.append(
                f"      model {leg.prediction.probability:.0%} vs market {leg.market.implied_prob_yes:.0%}"
                f"  (edge {leg.edge:+.1%})  price ${leg.market.yes_price:.2f}"
                f"  ticker={leg.market.ticker}"
            )
        lines.append(
            f"      combined prob {rec.combined_probability:.1%} @ price ${rec.combined_price:.2f}"
            f" | stake ${rec.stake:.2f} -> payout ${rec.potential_payout:.2f}"
            f" | EV ${rec.expected_value:+.2f}"
        )
        lines.append(f"      why: {rec.reasoning}")
        lines.append("")

    lines.append("--- Budget Allocation Summary ---")
    lines.append(f"  Straight bets: ${straight_total:.2f}")
    lines.append(f"  Parlays:       ${parlay_total:.2f}")
    lines.append(f"  Total staked:  ${straight_total + parlay_total:.2f} of ${budget:.2f} weekly budget")
    unallocated = budget - (straight_total + parlay_total)
    if unallocated > 0.01:
        lines.append(f"  Unallocated:   ${unallocated:.2f} (no additional bets cleared the +EV/edge threshold)")
    return "\n".join(lines)


def write_csv(recommendations: list[BetRecommendation], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "bet_type",
                "players",
                "tickers",
                "model_prob",
                "market_prob",
                "edge",
                "price",
                "stake",
                "potential_payout",
                "expected_value",
                "reasoning",
            ]
        )
        for rec in recommendations:
            players = "; ".join(leg.prediction.name for leg in rec.legs)
            tickers = "; ".join(leg.market.ticker for leg in rec.legs)
            model_prob = "; ".join(f"{leg.prediction.probability:.3f}" for leg in rec.legs)
            market_prob = "; ".join(f"{leg.market.implied_prob_yes:.3f}" for leg in rec.legs)
            edge = "; ".join(f"{leg.edge:+.3f}" for leg in rec.legs)
            writer.writerow(
                [
                    rec.bet_type,
                    players,
                    tickers,
                    model_prob,
                    market_prob,
                    edge,
                    f"{rec.combined_price:.3f}",
                    f"{rec.stake:.2f}",
                    f"{rec.potential_payout:.2f}",
                    f"{rec.expected_value:.2f}",
                    rec.reasoning,
                ]
            )
