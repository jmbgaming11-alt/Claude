"""Step 1: baseline cut-probability model.

Combines four weighted signals into a single P(makes the cut) per player:

  - Strokes Gained fit (40%): recent SG-total blended with SG at this
    course's terrain type (tree-lined / open / links / desert / parkland).
  - Historical cut-making percentage (30%): blend of last-12-months,
    last-season, and career cut rates, weighted toward recent form.
  - Last-4-weeks trajectory (20%): scoring average trend (last 4 weeks vs.
    last 10 rounds) plus cut results in the last 3 starts.
  - Course-specific history (10%): cut rate at this exact venue, when the
    player has a meaningful sample (>=4 rounds) at a recurring venue.

Each raw stat is squashed into a 0-1 "sub-probability" with a logistic
function before weighting, so the final blend stays a valid probability
without needing a fitted regression. A confidence score (based on how much
data underlies the estimate) is reported alongside so downstream filtering
can discount thin samples.
"""
from __future__ import annotations

import math

from pga_cutline_bot.config import ModelWeights
from pga_cutline_bot.models import ModelPrediction, PlayerStats, PlayingStatus


def _logistic(x: float, midpoint: float = 0.0, scale: float = 1.0) -> float:
    """Map a real-valued stat to (0, 1), centered at `midpoint`."""
    return 1.0 / (1.0 + math.exp(-(x - midpoint) / scale))


class CutProbabilityModel:
    def __init__(self, weights: ModelWeights = ModelWeights()):
        self.weights = weights

    def predict(self, player: PlayerStats, course_type: str, is_recurring_venue: bool) -> ModelPrediction:
        sg_component, sg_conf = self._sg_score(player, course_type)
        hist_component, hist_conf = self._historical_cut_score(player)
        form_component, form_conf = self._recent_form_score(player)
        course_component, course_conf = self._course_history_score(
            player, is_recurring_venue
        )

        w = self.weights
        probability = (
            w.strokes_gained * sg_component
            + w.historical_cut_pct * hist_component
            + w.recent_form * form_component
            + w.course_history * course_component
        )
        probability = min(max(probability, 0.01), 0.99)

        confidence = (
            w.strokes_gained * sg_conf
            + w.historical_cut_pct * hist_conf
            + w.recent_form * form_conf
            + w.course_history * course_conf
        )

        components = {
            "strokes_gained": w.strokes_gained * sg_component,
            "historical_cut_pct": w.historical_cut_pct * hist_component,
            "recent_form": w.recent_form * form_component,
            "course_history": w.course_history * course_component,
        }

        reasoning = self._build_reasoning(player, course_type, components, course_conf)

        return ModelPrediction(
            player_id=player.player_id,
            name=player.name,
            probability=probability,
            confidence=confidence,
            components=components,
            reasoning=reasoning,
        )

    # -- Sub-scores, each returns (score in [0,1], confidence in [0,1]) -----

    @staticmethod
    def _sg_score(player: PlayerStats, course_type: str) -> tuple[float, float]:
        course_sg = player.sg_by_course_type.get(course_type)
        if course_sg is not None:
            blended_sg = 0.6 * player.sg_total_recent + 0.4 * course_sg
            confidence = 1.0
        else:
            blended_sg = player.sg_total_recent
            confidence = 0.6  # no course-type SG breakdown available
        # SG-total is roughly normal with std ~1.0 stroke/round on tour;
        # a scale of 1.5 keeps the logistic from saturating too fast.
        score = _logistic(blended_sg, midpoint=0.0, scale=1.5)
        return score, confidence

    @staticmethod
    def _historical_cut_score(player: PlayerStats) -> tuple[float, float]:
        # Weight recent history more heavily than career.
        blended = (
            0.5 * player.cut_pct_last_12mo
            + 0.3 * player.cut_pct_last_season
            + 0.2 * player.cut_pct_career
        )
        confidence = 1.0
        return blended, confidence

    @staticmethod
    def _recent_form_score(player: PlayerStats) -> tuple[float, float]:
        # Trend: negative delta (scoring lower / better) is good.
        delta = player.scoring_avg_last4weeks - player.scoring_avg_last10
        trend_score = _logistic(-delta, midpoint=0.0, scale=0.75)

        if player.recent_finishes:
            made = sum(1 for f in player.recent_finishes if f is not None)
            cut_rate_recent = made / len(player.recent_finishes)
            confidence = min(1.0, len(player.recent_finishes) / 3.0)
        else:
            cut_rate_recent = trend_score
            confidence = 0.3

        score = 0.5 * trend_score + 0.5 * cut_rate_recent
        return score, confidence

    @staticmethod
    def _course_history_score(player: PlayerStats, is_recurring_venue: bool) -> tuple[float, float]:
        if (
            is_recurring_venue
            and player.course_history_cut_pct is not None
            and player.course_history_rounds >= 4
        ):
            confidence = min(1.0, player.course_history_rounds / 12.0)
            return player.course_history_cut_pct, confidence
        # No meaningful course-specific sample: fall back to the player's
        # blended historical cut rate so the component doesn't drag the
        # probability toward an arbitrary prior, but flag low confidence.
        fallback = (
            0.5 * player.cut_pct_last_12mo
            + 0.3 * player.cut_pct_last_season
            + 0.2 * player.cut_pct_career
        )
        return fallback, 0.15

    @staticmethod
    def _build_reasoning(
        player: PlayerStats,
        course_type: str,
        components: dict[str, float],
        course_conf: float,
    ) -> str:
        top_factor = max(components, key=components.get)
        parts = [
            f"SG(recent+{course_type} fit)={player.sg_total_recent:+.2f}",
            f"cut%(12mo)={player.cut_pct_last_12mo:.0%}",
            f"form trend last4wk avg={player.scoring_avg_last4weeks:.2f} vs last10={player.scoring_avg_last10:.2f}",
        ]
        if course_conf >= 0.3:
            parts.append(f"course history cut%={player.course_history_cut_pct:.0%} ({player.course_history_rounds} rds)")
        else:
            parts.append("no meaningful course-specific history")
        return f"Driven mainly by {top_factor.replace('_', ' ')}. " + "; ".join(parts)
