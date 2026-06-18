"""
Implementiert Kicktipps "2-3-4 Punkteregel" (Tendenz / Tordifferenz / Ergebnis):

    Tendenz       Tordifferenz   Ergebnis
    Sieg            2               3            4
    Unentschieden   2               -            4

- Falsche Tendenz                                  -> 0 Punkte
- Richtige Tendenz                                 -> 2 Punkte
- Richtige Tendenz + richtige Tordifferenz
  (nur bei Sieg möglich, da die Tordifferenz bei
  einem Unentschieden immer 0 ist)                 -> 3 Punkte
- Exaktes Ergebnis                                 -> 4 Punkte

Gilt für jedes Spiel als Basis-Score-Regel, unabhängig vom Match-Typ.
"""
from __future__ import annotations

from kicktipp_analytics.calculation.interfaces import PointsBreakdown
from kicktipp_analytics.domain.models import Match, MatchResult, Tendency, Tip


class TendenzTordifferenzErgebnisCalculator:
    kind = "score"

    def applies_to(self, match: Match) -> bool:
        return True

    def calculate(self, tip: Tip, result: MatchResult) -> PointsBreakdown:
        tipped = tip.score_tip
        actual = result.score

        tendency_correct = tipped.tendency == actual.tendency
        if not tendency_correct:
            return PointsBreakdown(
                points=0,
                is_tendency_correct=False,
                is_goal_difference_correct=False,
                is_exact_hit=False,
            )

        exact_hit = (
            tipped.home_goals == actual.home_goals
            and tipped.away_goals == actual.away_goals
        )
        if exact_hit:
            return PointsBreakdown(
                points=4,
                is_tendency_correct=True,
                is_goal_difference_correct=True,
                is_exact_hit=True,
            )

        # Tordifferenz ist bei einem tatsächlichen Unentschieden immer 0 und
        # daher als eigene Kategorie nicht sinnvoll - dort führt "richtige
        # Tordifferenz" automatisch zum exakten Treffer oben.
        goal_difference_correct = (
            actual.tendency != Tendency.DRAW
            and tipped.goal_difference == actual.goal_difference
        )
        if goal_difference_correct:
            return PointsBreakdown(
                points=3,
                is_tendency_correct=True,
                is_goal_difference_correct=True,
                is_exact_hit=False,
            )

        return PointsBreakdown(
            points=2,
            is_tendency_correct=True,
            is_goal_difference_correct=False,
            is_exact_hit=False,
        )
