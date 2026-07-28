"""Step 3: turn +EV opportunities into a sized betting slip.

Two bet types are produced:

  - **Straight bets**: single-player "makes the cut" YES contracts, sized
    with fractional Kelly (config.kelly_fraction) against a straight-bet
    sub-budget, then scaled to fit that sub-budget and per-bet caps.
  - **Parlays**: 2-3 leg combinations of the same +EV pool, preferring legs
    whose predictions are driven by *different* dominant factors (one
    player's edge coming from ball-striking/SG, another's from recent form,
    a third's from course history) as a simple proxy for picking
    less-correlated outcomes rather than stacking players who all live or
    die by the same underlying driver. Parlay legs assume roughly
    independent outcomes (reasonable first approximation since cut-making
    is primarily a function of individual play, not head-to-head
    interaction) and are sized proportional to expected value.

Every recommendation independently respects `max_single_bet_fraction` of
the weekly budget, and the two sub-budgets are hard caps so total spend
never exceeds `weekly_budget`.
"""
from __future__ import annotations

from itertools import combinations

from pga_cutline_bot.allocation.kelly import kelly_fraction
from pga_cutline_bot.config import BettingConfig
from pga_cutline_bot.model.ev import filter_positive_ev, rank_by_ev
from pga_cutline_bot.models import BetRecommendation, MatchedOpportunity


class BetAllocator:
    def __init__(self, betting_config: BettingConfig):
        self.cfg = betting_config

    def build_recommendations(
        self, opportunities: list[MatchedOpportunity]
    ) -> list[BetRecommendation]:
        plus_ev = rank_by_ev(filter_positive_ev(opportunities, self.cfg.min_edge))
        if not plus_ev:
            return []

        straight_budget = self.cfg.weekly_budget * self.cfg.straight_bet_budget_fraction
        parlay_budget = self.cfg.weekly_budget - straight_budget

        straights = self._build_straight_bets(plus_ev, straight_budget)
        used_players = {leg.prediction.player_id for rec in straights for leg in rec.legs}
        parlay_pool = [o for o in plus_ev if o.prediction.player_id not in used_players] or plus_ev
        parlays = self._build_parlays(parlay_pool, parlay_budget)

        return straights + parlays

    # -- Straight bets --------------------------------------------------------

    def _build_straight_bets(
        self, opportunities: list[MatchedOpportunity], budget: float
    ) -> list[BetRecommendation]:
        top = opportunities[: self.cfg.top_n_straight]
        if not top:
            return []

        raw_stakes = []
        for opp in top:
            f = kelly_fraction(opp.prediction.probability, opp.market.yes_price)
            raw_stakes.append(budget * f * self.cfg.kelly_fraction)

        total_raw = sum(raw_stakes)
        cap = self.cfg.weekly_budget * self.cfg.max_single_bet_fraction
        recs = []
        for opp, raw_stake in zip(top, raw_stakes):
            if total_raw <= 0:
                break
            # Scale proportionally so straights never exceed their sub-budget.
            stake = min((raw_stake / total_raw) * budget, cap)
            if stake < self.cfg.min_bet_size:
                continue
            price = opp.market.yes_price
            contracts = stake / price
            payout = contracts * 1.0
            ev = opp.prediction.probability * payout - stake
            recs.append(
                BetRecommendation(
                    bet_type="straight",
                    legs=[opp],
                    stake=round(stake, 2),
                    combined_probability=opp.prediction.probability,
                    combined_price=price,
                    expected_value=round(ev, 2),
                    potential_payout=round(payout, 2),
                    reasoning=(
                        f"{opp.prediction.name}: model {opp.prediction.probability:.0%} vs "
                        f"market {opp.market.implied_prob_yes:.0%} "
                        f"(edge {opp.edge:+.1%}). {opp.prediction.reasoning}"
                    ),
                )
            )
        return recs

    # -- Parlays ----------------------------------------------------------------

    def _build_parlays(
        self, pool: list[MatchedOpportunity], budget: float
    ) -> list[BetRecommendation]:
        if budget < self.cfg.min_bet_size or len(pool) < self.cfg.min_parlay_legs:
            return []

        candidates = []
        for r in range(self.cfg.min_parlay_legs, self.cfg.max_parlay_legs + 1):
            for combo in combinations(pool, r):
                candidates.append(combo)

        scored = [(self._parlay_score(combo), combo) for combo in candidates]
        scored.sort(key=lambda t: t[0], reverse=True)

        chosen: list[tuple[float, tuple[MatchedOpportunity, ...]]] = []
        used_players: set[str] = set()
        for score, combo in scored:
            player_ids = {leg.prediction.player_id for leg in combo}
            if player_ids & used_players:
                continue  # keep parlays independent of each other, no shared legs
            if score <= 0:
                continue
            chosen.append((score, combo))
            used_players |= player_ids
            if len(chosen) >= self.cfg.max_parlays:
                break

        if not chosen:
            return []

        total_score = sum(s for s, _ in chosen)
        cap = self.cfg.weekly_budget * self.cfg.max_single_bet_fraction
        recs = []
        for score, combo in chosen:
            stake = min((score / total_score) * budget, cap) if total_score > 0 else 0.0
            if stake < self.cfg.min_bet_size:
                continue
            combined_prob = 1.0
            combined_price = 1.0
            names = []
            for leg in combo:
                combined_prob *= leg.prediction.probability
                combined_price *= leg.market.yes_price
                names.append(leg.prediction.name)
            payout = (stake / combined_price) * 1.0 if combined_price > 0 else 0.0
            ev = combined_prob * payout - stake
            factors = ", ".join(
                f"{leg.prediction.name} ({self._dominant_component(leg)})" for leg in combo
            )
            recs.append(
                BetRecommendation(
                    bet_type="parlay",
                    legs=list(combo),
                    stake=round(stake, 2),
                    combined_probability=combined_prob,
                    combined_price=combined_price,
                    expected_value=round(ev, 2),
                    potential_payout=round(payout, 2),
                    reasoning=(
                        f"{len(combo)}-leg parlay: {', '.join(names)}. "
                        f"Legs chosen for diversified drivers: {factors}."
                    ),
                )
            )
        return recs

    def _parlay_score(self, combo: tuple[MatchedOpportunity, ...]) -> float:
        combined_prob = 1.0
        combined_price = 1.0
        for leg in combo:
            combined_prob *= leg.prediction.probability
            combined_price *= leg.market.yes_price
        if combined_price <= 0:
            return 0.0
        ev_per_dollar = combined_prob * (1.0 / combined_price) - 1.0
        diversification = len({self._dominant_component(leg) for leg in combo}) / len(combo)
        # Reward EV, lightly discount parlays that stack correlated (same
        # dominant driver) legs.
        return ev_per_dollar * (0.6 + 0.4 * diversification)

    @staticmethod
    def _dominant_component(opp: MatchedOpportunity) -> str:
        return max(opp.prediction.components, key=opp.prediction.components.get)
