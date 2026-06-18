from kicktipp_analytics.calculation.interfaces import PointsBreakdown
from kicktipp_analytics.calculation.ranking import RankingCalculator
from kicktipp_analytics.calculation.scoring_resolver import TipEvaluation


def make_eval(player: str, match: str, points: int) -> TipEvaluation:
    breakdown = PointsBreakdown(
        points=points,
        is_tendency_correct=points > 0,
        is_goal_difference_correct=points >= 3,
        is_exact_hit=points == 4,
    )
    return TipEvaluation(
        match_id=match, player_id=player, total_points=points, breakdowns={"score": breakdown}
    )


def test_tiebreak_by_matchday_wins():
    # alice und bob landen bei gleicher Gesamtpunktzahl (8), aber alice hat
    # zwei Spieltagssiege gegenüber bobs einem -> alice muss laut
    # Liga-Tiebreak-Regel vorne liegen.
    evaluations = [
        make_eval("alice", "m1", 4), make_eval("bob", "m1", 2),  # MD1: alice gewinnt
        make_eval("alice", "m2", 1), make_eval("bob", "m2", 4),  # MD2: bob gewinnt
        make_eval("alice", "m3", 3), make_eval("bob", "m3", 2),  # MD3: alice gewinnt
    ]
    match_to_matchday = {"m1": 1, "m2": 2, "m3": 3}

    calc = RankingCalculator()
    standings = calc.calculate_matchday_standings(evaluations, match_to_matchday)
    snapshots = calc.build_snapshots(standings)

    final = {s.player_id: s for s in snapshots if s.matchday_number == 3}

    assert final["alice"].cumulative_points == final["bob"].cumulative_points == 8
    assert final["alice"].cumulative_matchday_wins == 2
    assert final["bob"].cumulative_matchday_wins == 1
    assert final["alice"].rank_after_matchday == 1
    assert final["bob"].rank_after_matchday == 2


def test_matchday_winner_flag_requires_points_above_zero():
    evaluations = [make_eval("alice", "m1", 0), make_eval("bob", "m1", 0)]
    calc = RankingCalculator()
    standings = calc.calculate_matchday_standings(evaluations, {"m1": 1})
    assert all(not s.is_matchday_winner for s in standings)
