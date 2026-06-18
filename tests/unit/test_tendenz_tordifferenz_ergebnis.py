from kicktipp_analytics.calculation.evaluators.tendenz_tordifferenz_ergebnis import (
    TendenzTordifferenzErgebnisCalculator,
)
from kicktipp_analytics.domain.models import MatchResult, ScoreResult, Tip


def make_tip(home: int, away: int) -> Tip:
    return Tip(player_id="p1", match_id="m1", score_tip=ScoreResult(home, away))


def make_result(home: int, away: int) -> MatchResult:
    return MatchResult(match_id="m1", score=ScoreResult(home, away))


def test_exact_hit_gives_four_points():
    calc = TendenzTordifferenzErgebnisCalculator()
    breakdown = calc.calculate(make_tip(2, 1), make_result(2, 1))
    assert breakdown.points == 4
    assert breakdown.is_exact_hit


def test_correct_tendency_and_goal_difference_gives_three_points():
    calc = TendenzTordifferenzErgebnisCalculator()
    # Tipp 2:1 (Tordifferenz +1), tatsächlich 3:2 (Tordifferenz +1) -> gleiche Tendenz + Tordifferenz
    breakdown = calc.calculate(make_tip(2, 1), make_result(3, 2))
    assert breakdown.points == 3
    assert breakdown.is_goal_difference_correct
    assert not breakdown.is_exact_hit


def test_correct_tendency_only_gives_two_points():
    calc = TendenzTordifferenzErgebnisCalculator()
    breakdown = calc.calculate(make_tip(2, 0), make_result(1, 0))
    assert breakdown.points == 2
    assert breakdown.is_tendency_correct
    assert not breakdown.is_goal_difference_correct


def test_wrong_tendency_gives_zero_points():
    calc = TendenzTordifferenzErgebnisCalculator()
    breakdown = calc.calculate(make_tip(2, 0), make_result(0, 1))
    assert breakdown.points == 0
    assert not breakdown.is_tendency_correct


def test_draw_tendency_correct_but_not_exact_gives_two_points():
    calc = TendenzTordifferenzErgebnisCalculator()
    breakdown = calc.calculate(make_tip(1, 1), make_result(2, 2))
    assert breakdown.points == 2
    assert breakdown.is_tendency_correct
    assert not breakdown.is_exact_hit
