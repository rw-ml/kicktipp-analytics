"""
Test-Double für IKicktippDataSource mit fest verdrahteten, aber fachlich
realistischen Beispieldaten (fiktive Teams, damit keine Verwechslung mit
echten WM-2026-Begegnungen entsteht). Damit lässt sich die komplette
Pipeline samt Dashboard durchspielen, ohne echte Kicktipp-Zugangsdaten
oder Netzwerkzugriff zu brauchen - die Daten decken bewusst alle
Bewertungsfälle ab: exakter Treffer, Tendenz+Tordifferenz, nur Tendenz,
kompletter Fehltipp, sowie ein K.o.-Spiel mit Elfmeterschießen-Tipp.

Austauschbar 1:1 gegen KicktippScraper (beide implementieren
IKicktippDataSource) - Pipeline und Dashboard merken nicht, welche Quelle
verwendet wird (Dependency Inversion).
"""
from __future__ import annotations

from datetime import datetime

from kicktipp_analytics.domain.models import (
    Match,
    MatchResult,
    MatchType,
    Matchday,
    PenaltyWinner,
    Player,
    ScoreResult,
    Team,
    Tip,
)
from kicktipp_analytics.extraction.interfaces import IKicktippDataSource

_TEAMS = {
    "adlerstadt": Team(id="adlerstadt", name="Adlerstadt", short_name="ADL"),
    "rotweiss": Team(id="rotweiss", name="Rotweiß", short_name="ROT"),
    "sturmfeld": Team(id="sturmfeld", name="Sturmfeld", short_name="STU"),
    "nordpol": Team(id="nordpol", name="Nordpol FC", short_name="NOR"),
}

_PLAYERS = [
    Player(id="anna", display_name="Anna"),
    Player(id="bernd", display_name="Bernd"),
    Player(id="carla", display_name="Carla"),
    Player(id="david", display_name="David"),
]


def _match(
    match_id: str,
    matchday: int,
    season: str,
    home: str,
    away: str,
    kickoff: datetime,
    match_type: MatchType = MatchType.GROUP,
) -> Match:
    return Match(
        id=match_id,
        matchday=Matchday(number=matchday, season=season),
        home_team=_TEAMS[home],
        away_team=_TEAMS[away],
        kickoff=kickoff,
        match_type=match_type,
    )


class MockKicktippDataSource(IKicktippDataSource):
    def __init__(self, season: str = "wm2026"):
        self._season = season

        self._matches = [
            _match("m1", 1, season, "adlerstadt", "rotweiss", datetime(2026, 6, 14, 18, 0)),
            _match("m2", 1, season, "sturmfeld", "nordpol", datetime(2026, 6, 14, 21, 0)),
            _match("m3", 2, season, "adlerstadt", "sturmfeld", datetime(2026, 6, 18, 18, 0)),
            _match("m4", 2, season, "rotweiss", "nordpol", datetime(2026, 6, 18, 21, 0)),
            _match(
                "m5", 3, season, "adlerstadt", "nordpol", datetime(2026, 6, 22, 20, 0),
                match_type=MatchType.KNOCKOUT,
            ),
        ]

        self._results = [
            MatchResult(match_id="m1", score=ScoreResult(2, 1)),
            MatchResult(match_id="m2", score=ScoreResult(1, 1)),
            MatchResult(match_id="m3", score=ScoreResult(0, 0)),
            MatchResult(match_id="m4", score=ScoreResult(3, 2)),
            MatchResult(
                match_id="m5",
                score=ScoreResult(1, 1),
                penalty_winner=PenaltyWinner("adlerstadt"),
            ),
        ]

        self._tips = [
            # Spieltag 1
            Tip("anna", "m1", ScoreResult(2, 1)),
            Tip("bernd", "m1", ScoreResult(1, 0)),
            Tip("carla", "m1", ScoreResult(1, 1)),
            Tip("david", "m1", ScoreResult(3, 1)),
            Tip("anna", "m2", ScoreResult(1, 1)),
            Tip("bernd", "m2", ScoreResult(2, 2)),
            Tip("carla", "m2", ScoreResult(0, 0)),
            Tip("david", "m2", ScoreResult(2, 0)),
            # Spieltag 2
            Tip("anna", "m3", ScoreResult(1, 0)),
            Tip("bernd", "m3", ScoreResult(0, 0)),
            Tip("carla", "m3", ScoreResult(1, 1)),
            Tip("david", "m3", ScoreResult(0, 0)),
            Tip("anna", "m4", ScoreResult(2, 1)),
            Tip("bernd", "m4", ScoreResult(3, 2)),
            Tip("carla", "m4", ScoreResult(1, 0)),
            Tip("david", "m4", ScoreResult(0, 1)),
            # Spieltag 3 (K.o., zusätzlich Elfmeter-Tipp)
            Tip("anna", "m5", ScoreResult(1, 1), PenaltyWinner("adlerstadt")),
            Tip("bernd", "m5", ScoreResult(2, 1), PenaltyWinner("nordpol")),
            Tip("carla", "m5", ScoreResult(0, 0), PenaltyWinner("adlerstadt")),
            Tip("david", "m5", ScoreResult(1, 1), PenaltyWinner("nordpol")),
        ]

    def get_players(self) -> list[Player]:
        return list(_PLAYERS)

    def get_matches(self, season: str) -> list[Match]:
        return [m for m in self._matches if m.matchday.season == season]

    def get_results(self, season: str) -> list[MatchResult]:
        match_ids = {m.id for m in self._matches if m.matchday.season == season}
        return [r for r in self._results if r.match_id in match_ids]

    def get_tips(self, season: str) -> list[Tip]:
        match_ids = {m.id for m in self._matches if m.matchday.season == season}
        return [t for t in self._tips if t.match_id in match_ids]
