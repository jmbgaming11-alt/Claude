"""Step 2: model-vs-market comparison and expected value math.

Kalshi cut markets trade as binary YES/NO contracts settling at $1 (100
cents) or $0. Buying a YES contract at price `p` (dollars, 0 < p < 1) pays
$1 if the player makes the cut, $0 otherwise. So for a $1 stake:

  EV = model_probability * (1 / price) - 1

which is the standard "edge over implied probability, converted through the
market price" formula. A positive EV means the model thinks the contract is
underpriced relative to its own estimate.
"""
from __future__ import annotations

from pga_cutline_bot.models import KalshiMarket, MatchedOpportunity, ModelPrediction


def match_predictions_to_markets(
    predictions: list[ModelPrediction], markets: list[KalshiMarket]
) -> list[MatchedOpportunity]:
    """Join model predictions to Kalshi markets by normalized player name."""
    by_name = {_normalize(m.player_name): m for m in markets}
    matched = []
    for pred in predictions:
        market = by_name.get(_normalize(pred.name))
        if market is not None:
            matched.append(MatchedOpportunity(prediction=pred, market=market))
    return matched


def _normalize(name: str) -> str:
    return " ".join(name.lower().replace(".", "").split())


def edge(opportunity: MatchedOpportunity) -> float:
    """Model probability minus market-implied probability."""
    return opportunity.edge


def expected_value_per_dollar(opportunity: MatchedOpportunity) -> float:
    """Expected profit per $1 staked buying YES at the ask."""
    return opportunity.ev_per_dollar


def filter_positive_ev(
    opportunities: list[MatchedOpportunity], min_edge: float
) -> list[MatchedOpportunity]:
    """Keep only opportunities with edge >= min_edge and positive EV.

    Excludes withdrawn/questionable players and anything the model considers
    a fade (edge <= 0), even if a caller passed min_edge <= 0.
    """
    filtered = []
    for opp in opportunities:
        if opp.edge >= min_edge and opp.ev_per_dollar > 0:
            filtered.append(opp)
    return filtered


def rank_by_ev(opportunities: list[MatchedOpportunity]) -> list[MatchedOpportunity]:
    return sorted(opportunities, key=lambda o: o.ev_per_dollar, reverse=True)
