"""Append-only JSON-lines ledger of recommendations and their outcomes.

Every pipeline run appends one entry per recommended bet with `result` set
to null. A separate `record_outcome` call (after the cut is made) fills in
whether it hit, so the model's calibration and real ROI can be tracked over
time and fed back into weight tuning.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pga_cutline_bot.models import BetRecommendation

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "ledger.jsonl"


def log_recommendations(
    recommendations: list[BetRecommendation],
    tournament_name: str,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a") as f:
        for rec in recommendations:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tournament": tournament_name,
                "bet_type": rec.bet_type,
                "players": [leg.prediction.name for leg in rec.legs],
                "tickers": [leg.market.ticker for leg in rec.legs],
                "model_probabilities": [leg.prediction.probability for leg in rec.legs],
                "market_probabilities": [leg.market.implied_prob_yes for leg in rec.legs],
                "combined_probability": rec.combined_probability,
                "combined_price": rec.combined_price,
                "stake": rec.stake,
                "potential_payout": rec.potential_payout,
                "expected_value": rec.expected_value,
                "result": None,  # filled in later via record_outcome()
                "actual_payout": None,
            }
            f.write(json.dumps(entry) + "\n")


def record_outcome(ledger_path: Path, ticker_set: list[str], won: bool) -> bool:
    """Mark the first un-settled entry matching `ticker_set` with its outcome.

    Returns True if a matching entry was found and updated.
    """
    if not ledger_path.exists():
        return False
    lines = ledger_path.read_text().splitlines()
    updated = False
    for i, line in enumerate(lines):
        entry = json.loads(line)
        if entry["result"] is None and sorted(entry["tickers"]) == sorted(ticker_set):
            entry["result"] = "win" if won else "loss"
            entry["actual_payout"] = entry["potential_payout"] if won else 0.0
            lines[i] = json.dumps(entry)
            updated = True
            break
    if updated:
        ledger_path.write_text("\n".join(lines) + "\n")
    return updated


def summarize_roi(ledger_path: Path = DEFAULT_LEDGER_PATH) -> dict:
    if not ledger_path.exists():
        return {"bets": 0, "settled": 0, "staked": 0.0, "returned": 0.0, "roi": 0.0}

    staked = returned = 0.0
    settled = total = 0
    for line in ledger_path.read_text().splitlines():
        entry = json.loads(line)
        total += 1
        staked += entry["stake"]
        if entry["result"] is not None:
            settled += 1
            returned += entry["actual_payout"] or 0.0

    roi = ((returned - staked) / staked) if staked > 0 else 0.0
    return {
        "bets": total,
        "settled": settled,
        "staked": round(staked, 2),
        "returned": round(returned, 2),
        "roi": round(roi, 4),
    }
