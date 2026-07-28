"""Shared data structures passed between pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PlayingStatus(str, Enum):
    CONFIRMED = "confirmed"
    QUESTIONABLE = "questionable"
    WITHDRAWN = "withdrawn"
    UNKNOWN = "unknown"


@dataclass
class PlayerStats:
    """Raw inputs collected for a single player ahead of a tournament."""

    player_id: str
    name: str
    scoring_avg_last10: float
    scoring_avg_last4weeks: float
    scoring_avg_ytd: float
    cut_pct_career: float  # 0-1
    cut_pct_last_season: float  # 0-1
    cut_pct_last_12mo: float  # 0-1
    sg_total_recent: float  # strokes gained total, trailing window
    sg_by_course_type: dict[str, float]  # e.g. {"tree-lined": 0.8, "open": 0.3}
    recent_finishes: list[Optional[int]]  # last 3 tournaments, None = missed cut
    course_history_rounds: int = 0
    course_history_cut_pct: Optional[float] = None  # None if venue not recurring/no data
    status: PlayingStatus = PlayingStatus.CONFIRMED
    status_note: str = ""


@dataclass
class KalshiMarket:
    """A single 'Player X makes the cut' market on Kalshi."""

    ticker: str
    player_name: str
    yes_bid: float  # cents, 0-100
    yes_ask: float  # cents, 0-100
    no_bid: float
    no_ask: float
    volume: int = 0

    @property
    def implied_prob_yes(self) -> float:
        """Mid-market implied probability of 'makes the cut' as a 0-1 float."""
        mid_cents = (self.yes_bid + self.yes_ask) / 2.0
        return mid_cents / 100.0

    @property
    def yes_price(self) -> float:
        """Cost in dollars to buy one YES contract at the ask (max payout $1)."""
        return self.yes_ask / 100.0


@dataclass
class ModelPrediction:
    player_id: str
    name: str
    probability: float  # model's P(makes cut), 0-1
    confidence: float  # 0-1, based on data completeness/recency
    components: dict[str, float]  # weighted contribution of each factor
    reasoning: str


@dataclass
class MatchedOpportunity:
    """A model prediction joined to its Kalshi market."""

    prediction: ModelPrediction
    market: KalshiMarket

    @property
    def edge(self) -> float:
        return self.prediction.probability - self.market.implied_prob_yes

    @property
    def ev_per_dollar(self) -> float:
        """Expected value per $1 staked on YES at the ask price."""
        price = self.market.yes_price
        if price <= 0 or price >= 1:
            return 0.0
        payout_if_win = 1.0 / price  # contracts bought per dollar * $1 payout each
        return (self.prediction.probability * payout_if_win) - 1.0


@dataclass
class BetRecommendation:
    bet_type: str  # "straight" or "parlay"
    legs: list[MatchedOpportunity]
    stake: float
    combined_probability: float
    combined_price: float  # cost per $1 potential payout, 0-1
    expected_value: float  # expected profit in dollars on the stake
    potential_payout: float
    reasoning: str
