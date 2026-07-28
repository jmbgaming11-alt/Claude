"""End-to-end orchestration: field/stats -> Kalshi markets -> model -> EV -> allocation -> slip."""
from __future__ import annotations

from pathlib import Path

from pga_cutline_bot import config
from pga_cutline_bot.allocation.allocator import BetAllocator
from pga_cutline_bot.data_sources.kalshi_client import KalshiClient
from pga_cutline_bot.data_sources.pga_stats import PGATourStatsClient
from pga_cutline_bot.model.ev import match_predictions_to_markets
from pga_cutline_bot.model.probability_model import CutProbabilityModel
from pga_cutline_bot.models import BetRecommendation, PlayingStatus
from pga_cutline_bot.tracking.ledger import log_recommendations


def run_pipeline(
    tournament: config.Tournament = config.DEFAULT_TOURNAMENT,
    weights: config.ModelWeights = config.DEFAULT_WEIGHTS,
    betting_config: config.BettingConfig = config.DEFAULT_BETTING,
    write_ledger: bool = True,
) -> list[BetRecommendation]:
    stats_client = PGATourStatsClient()
    kalshi_client = KalshiClient()

    field = stats_client.fetch_field(tournament.pga_tour_slug)
    active_field = [
        p for p in field if p.status not in (PlayingStatus.WITHDRAWN, PlayingStatus.QUESTIONABLE)
    ]

    model = CutProbabilityModel(weights=weights)
    predictions = [
        model.predict(p, tournament.course_type, tournament.is_recurring_venue)
        for p in active_field
    ]

    markets = kalshi_client.get_cut_markets(tournament.kalshi_series_ticker)
    opportunities = match_predictions_to_markets(predictions, markets)

    allocator = BetAllocator(betting_config)
    recommendations = allocator.build_recommendations(opportunities)

    if write_ledger and recommendations:
        log_recommendations(recommendations, tournament.name)

    return recommendations
