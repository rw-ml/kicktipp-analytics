from kicktipp_analytics.calculation.interfaces import PointsBreakdown
from kicktipp_analytics.calculation.scoring_resolver import TipEvaluation
from kicktipp_analytics.calculation.statistics import StatisticsCalculator
from kicktipp_analytics.domain.models import Tendency


def make_eval(player: str, match: str, points: int, tendency_correct: bool, exact: bool, goal_diff_correct: bool = False):
    breakdown = PointsBreakdown(
        points=points,
        is_tendency_correct=tendency_correct,
        is_goal_difference_correct=goal_diff_correct or exact,
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
    match_to_tendency = {"m1": Tendency.HOME_WIN, "m2": Tendency.AWAY_WIN, "m3": Tendency.DRAW}
    stats = StatisticsCalculator().calculate(evaluations, match_to_tendency)
    alice_stats = next(s for s in stats if s.player_id == "alice")

    assert alice_stats.total_tips == 3
    assert alice_stats.exact_hits == 1
    assert alice_stats.tendency_hits == 2
    assert alice_stats.misses == 1
    assert alice_stats.hit_rate == round(2 / 3, 4)


def test_tendency_hits_are_broken_down_by_win_and_draw():
    evaluations = [
        make_eval("alice", "m1", 4, True, True),  # Heimsieg -> zählt als Sieg
        make_eval("alice", "m2", 2, True, False),  # Remis
        make_eval("alice", "m3", 3, True, False),  # Auswärtssieg -> zählt ebenfalls als Sieg
        make_eval("alice", "m4", 0, False, False),  # falsche Tendenz, zählt nirgends
    ]
    match_to_tendency = {
        "m1": Tendency.HOME_WIN,
        "m2": Tendency.DRAW,
        "m3": Tendency.AWAY_WIN,
        "m4": Tendency.HOME_WIN,
    }
    stats = StatisticsCalculator().calculate(evaluations, match_to_tendency)
    alice_stats = next(s for s in stats if s.player_id == "alice")

    # Heim- und Auswärtssieg fließen beide in dieselbe "Sieg"-Kategorie ein,
    # da das bei einem Turnier auf neutralem Platz keine sinnvolle
    # Unterscheidung ist.
    assert alice_stats.win_tips_correct == 2
    assert alice_stats.draw_tips_correct == 1
    assert alice_stats.tendency_hits == 3


def test_bremsfett_ranking_sorts_by_most_misses():
    evaluations = [
        make_eval("alice", "m1", 0, False, False),
        make_eval("alice", "m2", 0, False, False),
        make_eval("bob", "m1", 4, True, True),
        make_eval("bob", "m2", 0, False, False),
    ]
    match_to_tendency = {"m1": Tendency.HOME_WIN, "m2": Tendency.AWAY_WIN}
    stats = StatisticsCalculator().calculate(evaluations, match_to_tendency)
    assert stats[0].player_id == "alice"  # mehr Fehltipps -> Spitzenreiter im Bremsfett-Ranking


def test_goal_difference_hits():
    evaluations = [
        make_eval("alice", "m1", 4, True, True, True),   # exakt → kein goal_diff_hit
        make_eval("alice", "m2", 3, True, False, True),  # tordiff, nicht exakt → goal_diff_hit
        make_eval("alice", "m3", 2, True, False, False), # tendenz nur
        make_eval("alice", "m4", 0, False, False, False),# miss
    ]
    match_to_tendency = {
        "m1": Tendency.HOME_WIN, "m2": Tendency.AWAY_WIN,
        "m3": Tendency.DRAW, "m4": Tendency.HOME_WIN,
    }
    stats = StatisticsCalculator().calculate(evaluations, match_to_tendency)
    alice = next(s for s in stats if s.player_id == "alice")
    assert alice.exact_hits == 1
    assert alice.goal_difference_hits == 1
    assert alice.tendency_hits == 3  # m1+m2+m3