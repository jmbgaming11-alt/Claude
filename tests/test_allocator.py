from pga_cutline_bot.allocation.allocator import BetAllocator
from pga_cutline_bot.config import BettingConfig
from pga_cutline_bot.models import KalshiMarket, MatchedOpportunity, ModelPrediction


def make_opportunity(name, prob, yes_ask, dominant="strokes_gained"):
    pred = ModelPrediction(
        player_id=name,
        name=name,
        probability=prob,
        confidence=1.0,
        components={dominant: prob, "other": 0.01},
        reasoning="",
    )
    market = KalshiMarket(
        ticker=f"TICK-{name}", player_name=name, yes_bid=yes_ask - 2, yes_ask=yes_ask, no_bid=100 - yes_ask, no_ask=102 - yes_ask
    )
    return MatchedOpportunity(prediction=pred, market=market)


def test_no_bets_when_no_positive_ev():
    cfg = BettingConfig(weekly_budget=50.0, min_edge=0.05)
    allocator = BetAllocator(cfg)
    opps = [make_opportunity("Fair", 0.6, 60)]  # market prob ~0.59, edge < 0.05
    recs = allocator.build_recommendations(opps)
    assert recs == []


def test_total_stake_never_exceeds_budget():
    cfg = BettingConfig(weekly_budget=50.0, min_edge=0.05)
    allocator = BetAllocator(cfg)
    opps = [
        make_opportunity("A", 0.80, 60),
        make_opportunity("B", 0.75, 55),
        make_opportunity("C", 0.70, 50),
        make_opportunity("D", 0.65, 48),
        make_opportunity("E", 0.72, 52),
        make_opportunity("F", 0.68, 45),
    ]
    recs = allocator.build_recommendations(opps)
    total = sum(r.stake for r in recs)
    assert total <= cfg.weekly_budget + 1e-6


def test_no_single_bet_exceeds_max_fraction():
    cfg = BettingConfig(weekly_budget=50.0, min_edge=0.05, max_single_bet_fraction=0.35)
    allocator = BetAllocator(cfg)
    opps = [make_opportunity("A", 0.85, 40)]  # huge edge, would want a big stake
    recs = allocator.build_recommendations(opps)
    for rec in recs:
        assert rec.stake <= cfg.weekly_budget * cfg.max_single_bet_fraction + 1e-6


def test_parlays_do_not_reuse_straight_bet_players():
    cfg = BettingConfig(weekly_budget=50.0, min_edge=0.05, top_n_straight=2, max_parlays=1)
    allocator = BetAllocator(cfg)
    opps = [
        make_opportunity("A", 0.85, 40, dominant="strokes_gained"),
        make_opportunity("B", 0.80, 45, dominant="recent_form"),
        make_opportunity("C", 0.75, 50, dominant="historical_cut_pct"),
        make_opportunity("D", 0.72, 52, dominant="course_history"),
    ]
    recs = allocator.build_recommendations(opps)
    straight_players = {leg.prediction.name for r in recs if r.bet_type == "straight" for leg in r.legs}
    parlay_players = {leg.prediction.name for r in recs if r.bet_type == "parlay" for leg in r.legs}
    assert straight_players.isdisjoint(parlay_players)
