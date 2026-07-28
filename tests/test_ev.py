from pga_cutline_bot.model.ev import filter_positive_ev, match_predictions_to_markets, rank_by_ev
from pga_cutline_bot.models import KalshiMarket, ModelPrediction


def make_pred(name, prob):
    return ModelPrediction(
        player_id=name, name=name, probability=prob, confidence=1.0, components={}, reasoning=""
    )


def make_market(name, yes_bid, yes_ask):
    return KalshiMarket(
        ticker=f"TICK-{name}", player_name=name, yes_bid=yes_bid, yes_ask=yes_ask, no_bid=100 - yes_ask, no_ask=100 - yes_bid
    )


def test_matching_is_case_and_punctuation_insensitive():
    preds = [make_pred("A.J. Smith", 0.7)]
    markets = [make_market("aj smith", 60, 62)]
    matched = match_predictions_to_markets(preds, markets)
    assert len(matched) == 1


def test_filter_requires_minimum_edge():
    preds = [make_pred("Big Edge", 0.70), make_pred("Small Edge", 0.55)]
    markets = [make_market("Big Edge", 58, 60), make_market("Small Edge", 53, 55)]
    matched = match_predictions_to_markets(preds, markets)
    plus_ev = filter_positive_ev(matched, min_edge=0.05)
    names = {o.prediction.name for o in plus_ev}
    assert "Big Edge" in names
    assert "Small Edge" not in names


def test_negative_edge_excluded_even_with_zero_threshold():
    preds = [make_pred("Overpriced", 0.40)]
    markets = [make_market("Overpriced", 60, 62)]
    matched = match_predictions_to_markets(preds, markets)
    assert filter_positive_ev(matched, min_edge=0.0) == []


def test_rank_by_ev_orders_descending():
    preds = [make_pred("Low", 0.55), make_pred("High", 0.80)]
    markets = [make_market("Low", 50, 52), make_market("High", 55, 57)]
    matched = match_predictions_to_markets(preds, markets)
    ranked = rank_by_ev(matched)
    assert ranked[0].prediction.name == "High"
