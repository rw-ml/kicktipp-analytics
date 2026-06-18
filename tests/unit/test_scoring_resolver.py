from datetime import datetime

from kicktipp_analytics.calculation.evaluators.penalty_winner import PenaltyWinnerCalculator
from kicktipp_analytics.calculation.evaluators.tendenz_tordifferenz_ergebnis import (
    TendenzTordifferenzErgebnisCalculator,
)
from kicktipp_analytics.calculation.scoring_resolver import ScoringResolver
from kicktipp_analytics.domain.models import (
    Match,
    MatchResult,
    MatchType,
    Matchday,
    PenaltyWinner,
    ScoreResult,
    Team,
    Tip,
)


def make_resolver() -> ScoringResolver:
    return ScoringResolver([TendenzTordifferenzErgebnisCalculator(), PenaltyWinnerCalculator()])


def test_knockout_match_combines_score_and_penalty_points():
    match = Match(
        id="m1",
        matchday=Matchday(number=5, season="wm2026"),
        home_team=Team(id="A", name="Team A"),
        away_team=Team(id="B", name="Team B"),
        kickoff=datetime(2026, 7, 1, 18, 0),
        match_type=MatchType.KNOCKOUT,
    )
    tip = Tip(
        player_id="p1",
        match_id="m1",
        score_tip=ScoreResult(1, 1),
        penalty_winner_tip=PenaltyWinner("A"),
    )
    result = MatchResult(
        match_id="m1", score=ScoreResult(1, 1), penalty_winner=PenaltyWinner("A")
    )

    evaluation = make_resolver().evaluate(tip, match, result)

    assert evaluation.total_points == 4 + 4  # exaktes 1:1 (4) + richtiger Elfersieger (4)
    assert evaluation.breakdowns["score"].is_exact_hit
    assert evaluation.breakdowns["penalty_shootout"].points == 4


def test_group_match_only_uses_score_calculator():
    match = Match(
        id="m2",
        matchday=Matchday(number=1, season="wm2026"),
        home_team=Team(id="A", name="Team A"),
        away_team=Team(id="B", name="Team B"),
        kickoff=datetime(2026, 6, 15, 18, 0),
        match_type=MatchType.GROUP,
    )
    tip = Tip(player_id="p1", match_id="m2", score_tip=ScoreResult(2, 0))
    result = MatchResult(match_id="m2", score=ScoreResult(2, 0))

    evaluation = make_resolver().evaluate(tip, match, result)

    assert evaluation.total_points == 4
    assert "penalty_shootout" not in evaluation.breakdowns
