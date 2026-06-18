from kicktipp_analytics.calculation.interfaces import PointsBreakdown
from kicktipp_analytics.calculation.scoring_resolver import TipEvaluation
from kicktipp_analytics.calculation.statistics import StatisticsCalculator


def make_eval(player: str, match: str, points: int, tendency_correct: bool, exact: bool):
    breakdown = PointsBreakdown(
        points=points,
        is_tendency_correct=tendency_correct,
        is_goal_difference_correct=False,
        is_exact_hit=exact,
    )
    return TipEvaluation(
        match_id=match, player_id=player, total_points=points, breakdowns={"score": breakdown}
    )


def test_hit_rate_and_misses():
    evaluations = [
        make_eval("alice", "m1", 4, True, True),
        make_eval("alice", "m2", 0, False, False),
        make_eval("alice", "m3", 2, True, False),
    ]
    stats = StatisticsCalculator().calculate(evaluations)
    alice_stats = next(s for s in stats if s.player_id == "alice")

    assert alice_stats.total_tips == 3
    assert alice_stats.exact_hits == 1
    assert alice_stats.tendency_hits == 2
    assert alice_stats.misses == 1
    assert alice_stats.hit_rate == round(2 / 3, 4)


def test_bremsfett_ranking_sorts_by_most_misses():
    evaluations = [
        make_eval("alice", "m1", 0, False, False),
        make_eval("alice", "m2", 0, False, False),
        make_eval("bob", "m1", 4, True, True),
        make_eval("bob", "m2", 0, False, False),
    ]
    stats = StatisticsCalculator().calculate(evaluations)
    assert stats[0].player_id == "alice"  # mehr Fehltipps -> Spitzenreiter im Bremsfett-Ranking
