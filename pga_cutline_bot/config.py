"""Central configuration for the cut-line betting pipeline.

All tunable knobs live here so the model, allocator, and CLI stay in sync.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelWeights:
    """Weights for the Step 1 baseline probability model. Must sum to 1.0."""

    strokes_gained: float = 0.40
    historical_cut_pct: float = 0.30
    recent_form: float = 0.20
    course_history: float = 0.10

    def __post_init__(self) -> None:
        total = (
            self.strokes_gained
            + self.historical_cut_pct
            + self.recent_form
            + self.course_history
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"ModelWeights must sum to 1.0, got {total}")


@dataclass(frozen=True)
class BettingConfig:
    """Budget and risk constraints for the allocator."""

    weekly_budget: float = 50.0
    min_edge: float = 0.05  # require >5% edge (model_prob - market_prob) to bet
    max_single_bet_fraction: float = 0.35  # no single straight bet > 35% of budget
    max_parlay_legs: int = 3
    min_parlay_legs: int = 2
    straight_bet_budget_fraction: float = 0.65  # remainder goes to parlays
    kelly_fraction: float = 0.25  # fractional Kelly (quarter-Kelly) for sizing
    min_bet_size: float = 1.0  # Kalshi's practical minimum contract cost
    top_n_straight: int = 4
    max_parlays: int = 2


@dataclass(frozen=True)
class Tournament:
    name: str
    pga_tour_slug: str  # e.g. "rocket-classic"
    kalshi_series_ticker: str  # e.g. "KXPGACUT" - series ticker for cut-line markets
    course_type: str = "parkland"  # tree-lined | open | links | parkland | desert
    is_recurring_venue: bool = True


DEFAULT_TOURNAMENT = Tournament(
    name="Rocket Classic",
    pga_tour_slug="rocket-classic",
    kalshi_series_ticker="KXPGACUT",
    course_type="tree-lined",
    is_recurring_venue=True,
)

DEFAULT_WEIGHTS = ModelWeights()
DEFAULT_BETTING = BettingConfig()

# --- Environment-driven credentials (never hardcode secrets) ---
KALSHI_API_KEY_ID = os.environ.get("KALSHI_API_KEY_ID", "")
KALSHI_PRIVATE_KEY_PATH = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
KALSHI_BASE_URL = os.environ.get(
    "KALSHI_BASE_URL", "https://api.elections.kalshi.com/trade-api/v2"
)
PGA_TOUR_STATS_BASE_URL = os.environ.get(
    "PGA_TOUR_STATS_BASE_URL", "https://orchestrator.pgatour.com/graphql"
)

# When true (default whenever live credentials/network aren't available), every
# data source falls back to the bundled synthetic sample_data/*.json fixtures
# instead of making a network call. This keeps the pipeline runnable end to end
# for development, testing, and demonstration.
DEMO_MODE = os.environ.get("PGA_BOT_DEMO_MODE", "1") == "1"
