"""
Abstraktion für eine einzelne Punkteregel-Strategie.

Jede konkrete Regel (Standard-Tendenz/Tordifferenz/Ergebnis, Elfmeter-
Sonderregel, ...) implementiert dieses Protocol. Neue Regeln kommen als
neue Klassen hinzu, ohne bestehenden Code zu verändern (Open/Closed
Principle). Die Schnittstelle ist bewusst klein gehalten (Interface
Segregation): nur 'applies_to' und 'calculate'.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kicktipp_analytics.domain.models import Match, MatchResult, Tip


@dataclass(frozen=True, slots=True)
class PointsBreakdown:
    """Ergebnis der Bewertung eines einzelnen Tipps gegen das tatsächliche Resultat."""

    points: int
    is_tendency_correct: bool
    is_goal_difference_correct: bool
    is_exact_hit: bool


class IPointsCalculator(Protocol):
    """Eine einzelne, zustandslose Punkteregel-Strategie."""

    #: Eindeutiger Schlüssel, unter dem das Ergebnis dieser Regel im
    #: TipEvaluation.breakdowns-Dict abgelegt wird (z.B. "score",
    #: "penalty_shootout"). Macht den ScoringResolver generisch erweiterbar.
    kind: str

    def applies_to(self, match: Match) -> bool:
        """Ob diese Regel für das gegebene Spiel überhaupt relevant ist."""
        ...

    def calculate(self, tip: Tip, result: MatchResult) -> PointsBreakdown:
        ...
