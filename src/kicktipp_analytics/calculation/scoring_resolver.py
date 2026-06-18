"""
Der ScoringResolver kennt keine konkrete Punkteregel - er bekommt eine
Liste von IPointsCalculator-Strategien injiziert und wendet alle an, die
für das jeweilige Spiel zuständig sind (Dependency Inversion). Eine neue
Sonderregel hinzuzufügen bedeutet: neue Calculator-Klasse schreiben und
hier in der Liste registrieren - diese Klasse selbst bleibt unverändert
(Open/Closed Principle).
"""
from __future__ import annotations

from dataclasses import dataclass

from kicktipp_analytics.calculation.interfaces import IPointsCalculator, PointsBreakdown
from kicktipp_analytics.domain.models import Match, MatchResult, Tip


@dataclass(frozen=True, slots=True)
class TipEvaluation:
    match_id: str
    player_id: str
    total_points: int
    #: Ein Eintrag pro angewendeter Regel, z.B. {"score": ..., "penalty_shootout": ...}
    breakdowns: dict[str, PointsBreakdown]


class ScoringResolver:
    def __init__(self, calculators: list[IPointsCalculator]):
        self._calculators = calculators

    def evaluate(self, tip: Tip, match: Match, result: MatchResult) -> TipEvaluation:
        applicable = [c for c in self._calculators if c.applies_to(match)]
        if not applicable:
            raise ValueError(f"Kein PointsCalculator für Match '{match.id}' zuständig.")

        breakdowns = {c.kind: c.calculate(tip, result) for c in applicable}
        total_points = sum(b.points for b in breakdowns.values())

        return TipEvaluation(
            match_id=match.id,
            player_id=tip.player_id,
            total_points=total_points,
            breakdowns=breakdowns,
        )
