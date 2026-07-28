"""CLI entrypoint: python -m pga_cutline_bot.cli [--budget 50] [--csv out.csv]"""
from __future__ import annotations

import argparse
from pathlib import Path

from pga_cutline_bot import config
from pga_cutline_bot.pipeline import run_pipeline
from pga_cutline_bot.reporting.slip import render_console, write_csv
from pga_cutline_bot.tracking.ledger import summarize_roi


def main() -> None:
    parser = argparse.ArgumentParser(description="PGA Tour cut-line betting recommendation engine")
    parser.add_argument("--budget", type=float, default=config.DEFAULT_BETTING.weekly_budget)
    parser.add_argument("--min-edge", type=float, default=config.DEFAULT_BETTING.min_edge)
    parser.add_argument("--csv", type=str, default=None, help="Optional path to write a CSV betting slip")
    parser.add_argument("--no-ledger", action="store_true", help="Don't append this run to the tracking ledger")
    parser.add_argument("--show-roi", action="store_true", help="Print cumulative ROI from the ledger and exit")
    args = parser.parse_args()

    if args.show_roi:
        print(summarize_roi())
        return

    betting_config = config.BettingConfig(
        weekly_budget=args.budget,
        min_edge=args.min_edge,
        max_single_bet_fraction=config.DEFAULT_BETTING.max_single_bet_fraction,
        max_parlay_legs=config.DEFAULT_BETTING.max_parlay_legs,
        min_parlay_legs=config.DEFAULT_BETTING.min_parlay_legs,
        straight_bet_budget_fraction=config.DEFAULT_BETTING.straight_bet_budget_fraction,
        kelly_fraction=config.DEFAULT_BETTING.kelly_fraction,
        min_bet_size=config.DEFAULT_BETTING.min_bet_size,
        top_n_straight=config.DEFAULT_BETTING.top_n_straight,
        max_parlays=config.DEFAULT_BETTING.max_parlays,
    )

    recommendations = run_pipeline(
        betting_config=betting_config, write_ledger=not args.no_ledger
    )

    print(render_console(recommendations, betting_config.weekly_budget, config.DEFAULT_TOURNAMENT.name))

    if args.csv:
        write_csv(recommendations, Path(args.csv))
        print(f"\nCSV betting slip written to {args.csv}")

    if config.DEMO_MODE:
        print(
            "\n[DEMO MODE] PGA_BOT_DEMO_MODE=1 (default): using synthetic sample_data/*.json, "
            "not live PGA Tour stats or real Kalshi markets. Set KALSHI_API_KEY_ID / "
            "KALSHI_PRIVATE_KEY_PATH and PGA_BOT_DEMO_MODE=0 with outbound network access "
            "to run against live data."
        )


if __name__ == "__main__":
    main()
