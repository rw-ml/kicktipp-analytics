"""
Domain-Modelle für die Kicktipp-Analyse.

Diese Klassen tragen ausschließlich Daten - keine Berechnungs- oder
Persistenzlogik (Single Responsibility Principle). Sie sind die gemeinsame
"Sprache" zwischen Extraction-, Calculation- und Persistence-Schicht und
kennen keine dieser Schichten.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MatchType(str, Enum):
    """Gruppenspiele werden anders bewertet als K.o.-Spiele (Elfmeter-Sonderregel)."""

    GROUP = "group"
    KNOCKOUT = "knockout"


class Tendency(str, Enum):
    HOME_WIN = "home_win"
    DRAW = "draw"
    AWAY_WIN = "away_win"


@dataclass(frozen=True, slots=True)
class Team:
    id: str
    name: str
    short_name: str | None = None


@dataclass(frozen=True, slots=True)
class Player:
    id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class Matchday:
    number: int
    season: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class Match:
    id: str
    matchday: Matchday
    home_team: Team
    away_team: Team
    kickoff: datetime
    match_type: MatchType = MatchType.GROUP

    @property
    def requires_penalty_tip(self) -> bool:
        """Nur K.o.-Spiele haben einen zusätzlichen 'Elfmeterschießen-Sieger'-Tipp."""
        return self.match_type == MatchType.KNOCKOUT


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Ein Spielstand - egal ob getippt oder tatsächlich. Reihenfolge (Heim:Auswärts) zählt."""

    home_goals: int
    away_goals: int

    @property
    def tendency(self) -> Tendency:
        if self.home_goals > self.away_goals:
            return Tendency.HOME_WIN
        if self.home_goals < self.away_goals:
            return Tendency.AWAY_WIN
        return Tendency.DRAW

    @property
    def goal_difference(self) -> int:
        return self.home_goals - self.away_goals


@dataclass(frozen=True, slots=True)
class PenaltyWinner:
    """Sieger nach Elfmeterschießen - nur die Mannschaft zählt, kein Ergebnis."""

    team_id: str


@dataclass(frozen=True, slots=True)
class MatchResult:
    match_id: str
    score: ScoreResult
    penalty_winner: PenaltyWinner | None = None


@dataclass(frozen=True, slots=True)
class Tip:
    player_id: str
    match_id: str
    score_tip: ScoreResult
    penalty_winner_tip: PenaltyWinner | None = None
    submitted_at: datetime | None = None
