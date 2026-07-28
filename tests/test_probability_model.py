from pga_cutline_bot.model.probability_model import CutProbabilityModel
from pga_cutline_bot.models import PlayerStats, PlayingStatus


def make_player(**overrides) -> PlayerStats:
    defaults = dict(
        player_id="t1",
        name="Test Player",
        scoring_avg_last10=70.5,
        scoring_avg_last4weeks=70.5,
        scoring_avg_ytd=70.5,
        cut_pct_career=0.65,
        cut_pct_last_season=0.65,
        cut_pct_last_12mo=0.65,
        sg_total_recent=0.0,
        sg_by_course_type={},
        recent_finishes=[],
        course_history_rounds=0,
        course_history_cut_pct=None,
        status=PlayingStatus.CONFIRMED,
    )
    defaults.update(overrides)
    return PlayerStats(**defaults)


def test_probability_is_bounded():
    model = CutProbabilityModel()
    player = make_player(sg_total_recent=5.0, cut_pct_last_12mo=1.0)
    pred = model.predict(player, "tree-lined", True)
    assert 0.0 < pred.probability < 1.0


def test_better_stats_yield_higher_probability():
    model = CutProbabilityModel()
    strong = make_player(
        sg_total_recent=1.5,
        cut_pct_last_12mo=0.85,
        scoring_avg_last4weeks=69.0,
        recent_finishes=[5, 10, 8],
    )
    weak = make_player(
        sg_total_recent=-1.0,
        cut_pct_last_12mo=0.4,
        scoring_avg_last4weeks=72.0,
        recent_finishes=[None, None, 60],
    )
    strong_pred = model.predict(strong, "tree-lined", True)
    weak_pred = model.predict(weak, "tree-lined", True)
    assert strong_pred.probability > weak_pred.probability


def test_weights_must_sum_to_one():
    from pga_cutline_bot.config import ModelWeights
    import pytest

    with pytest.raises(ValueError):
        ModelWeights(strokes_gained=0.5, historical_cut_pct=0.5, recent_form=0.5, course_history=0.0)


def test_course_history_boosts_probability_when_present():
    model = CutProbabilityModel()
    no_history = make_player(course_history_rounds=0, course_history_cut_pct=None)
    with_history = make_player(course_history_rounds=20, course_history_cut_pct=0.95)
    pred_no_hist = model.predict(no_history, "tree-lined", True)
    pred_with_hist = model.predict(with_history, "tree-lined", True)
    assert pred_with_hist.probability > pred_no_hist.probability
    assert pred_with_hist.confidence > pred_no_hist.confidence
