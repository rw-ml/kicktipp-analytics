"""
Sonderregel für K.o.-Spiele: zusätzlicher Tipp "Wer gewinnt nach
Elfmeterschießen?". Flache 4 Punkte bei richtiger Antwort, sonst 0 - die
Reihenfolge/Tordifferenz-Logik der Standardregel ist hier nicht relevant,
da nur ein Sieger getippt wird ("Bei dieser Regel hat die Reihenfolge
keine Bedeutung").

Diese Regel ist additiv: sie kommt bei K.o.-Spielen zur Standard-Score-
Regel hinzu (siehe ScoringResolver), ersetzt sie nicht.
"""
from __future__ import annotations

from kicktipp_analytics.calculation.interfaces import PointsBreakdown
from kicktipp_analytics.domain.models import Match, MatchResult, Tip


class PenaltyWinnerCalculator:
    kind = "penalty_shootout"

    def applies_to(self, match: Match) -> bool:
        return match.requires_penalty_tip

    def calculate(self, tip: Tip, result: MatchResult) -> PointsBreakdown:
        if result.penalty_winner is None or tip.penalty_winner_tip is None:
            return PointsBreakdown(
                points=0,
                is_tendency_correct=False,
                is_goal_difference_correct=False,
                is_exact_hit=False,
            )

        correct = tip.penalty_winner_tip.team_id == result.penalty_winner.team_id
        points = 4 if correct else 0
        return PointsBreakdown(
            points=points,
            is_tendency_correct=correct,
            is_goal_difference_correct=correct,
            is_exact_hit=correct,
        )
