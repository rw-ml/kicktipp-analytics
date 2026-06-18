from kicktipp_analytics.calculation.evaluators.penalty_winner import PenaltyWinnerCalculator
from kicktipp_analytics.domain.models import MatchResult, PenaltyWinner, ScoreResult, Tip


def test_correct_penalty_winner_gives_four_points():
    calc = PenaltyWinnerCalculator()
    tip = Tip(
        player_id="p1",
        match_id="m1",
        score_tip=ScoreResult(1, 1),
        penalty_winner_tip=PenaltyWinner("team_a"),
    )
    result = MatchResult(
        match_id="m1", score=ScoreResult(1, 1), penalty_winner=PenaltyWinner("team_a")
    )
    breakdown = calc.calculate(tip, result)
    assert breakdown.points == 4


def test_wrong_penalty_winner_gives_zero_points():
    calc = PenaltyWinnerCalculator()
    tip = Tip(
        player_id="p1",
        match_id="m1",
        score_tip=ScoreResult(1, 1),
        penalty_winner_tip=PenaltyWinner("team_a"),
    )
    result = MatchResult(
        match_id="m1", score=ScoreResult(1, 1), penalty_winner=PenaltyWinner("team_b")
    )
    breakdown = calc.calculate(tip, result)
    assert breakdown.points == 0


def test_missing_penalty_tip_gives_zero_points():
    calc = PenaltyWinnerCalculator()
    tip = Tip(player_id="p1", match_id="m1", score_tip=ScoreResult(1, 1))
    result = MatchResult(
        match_id="m1", score=ScoreResult(1, 1), penalty_winner=PenaltyWinner("team_a")
    )
    breakdown = calc.calculate(tip, result)
    assert breakdown.points == 0
