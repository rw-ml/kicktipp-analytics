"""
Berechnet aus den TipEvaluations:

1. Spieltags-Tabellen (wer hat an welchem Spieltag wie viele Punkte/wer hat
   gewonnen).
2. Eine vollständige Zeitreihe von Ranking-Snapshots (eine Zeile pro Spieler
   und Spieltag mit kumulierten Werten) - genau die Granularität, die Power
   BI für Formkurve, Ranking-Entwicklung über die Saison UND die aktuelle
   Bestenliste (= Snapshot des letzten Spieltags) braucht. Eine Faktentabelle
   reicht damit für mehrere Dashboard-Anforderungen.

Tiebreak-Regel laut Liga-Konfiguration: Bei Punktgleichstand in der
Gesamtpunktzahl entscheidet die Anzahl der Spieltagssiege.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from kicktipp_analytics.calculation.scoring_resolver import TipEvaluation


@dataclass(frozen=True, slots=True)
class MatchdayStanding:
    matchday_number: int
    player_id: str
    points: int
    is_matchday_winner: bool


@dataclass(frozen=True, slots=True)
class RankingSnapshot:
    player_id: str
    matchday_number: int
    points_this_matchday: int
    is_matchday_winner: bool
    cumulative_points: int
    cumulative_matchday_wins: int
    rank_after_matchday: int


class RankingCalculator:
    def calculate_matchday_standings(
        self,
        evaluations: list[TipEvaluation],
        match_to_matchday: dict[str, int],
    ) -> list[MatchdayStanding]:
        points: dict[tuple[int, str], int] = defaultdict(int)
        for ev in evaluations:
            matchday = match_to_matchday[ev.match_id]
            points[(matchday, ev.player_id)] += ev.total_points

        best_per_matchday: dict[int, int] = defaultdict(int)
        for (matchday, _player), pts in points.items():
            best_per_matchday[matchday] = max(best_per_matchday[matchday], pts)

        return [
            MatchdayStanding(
                matchday_number=matchday,
                player_id=player,
                points=pts,
                is_matchday_winner=(pts == best_per_matchday[matchday] and pts > 0),
            )
            for (matchday, player), pts in points.items()
        ]

    def build_snapshots(self, standings: list[MatchdayStanding]) -> list[RankingSnapshot]:
        cumulative_points: dict[str, int] = defaultdict(int)
        cumulative_wins: dict[str, int] = defaultdict(int)
        snapshots: list[RankingSnapshot] = []

        standings_by_matchday: dict[int, list[MatchdayStanding]] = defaultdict(list)
        for s in standings:
            standings_by_matchday[s.matchday_number].append(s)

        for matchday in sorted(standings_by_matchday):
            for s in standings_by_matchday[matchday]:
                cumulative_points[s.player_id] += s.points
                if s.is_matchday_winner:
                    cumulative_wins[s.player_id] += 1

            ranked_players = sorted(
                cumulative_points.keys(),
                key=lambda p: (-cumulative_points[p], -cumulative_wins[p]),
            )
            rank_by_player = {p: rank for rank, p in enumerate(ranked_players, start=1)}

            for s in standings_by_matchday[matchday]:
                snapshots.append(
                    RankingSnapshot(
                        player_id=s.player_id,
                        matchday_number=matchday,
                        points_this_matchday=s.points,
                        is_matchday_winner=s.is_matchday_winner,
                        cumulative_points=cumulative_points[s.player_id],
                        cumulative_matchday_wins=cumulative_wins[s.player_id],
                        rank_after_matchday=rank_by_player[s.player_id],
                    )
                )

        return snapshots


def latest_ranking(snapshots: list[RankingSnapshot]) -> list[RankingSnapshot]:
    """Komfort-Funktion: aktuelle Bestenliste = Snapshot des letzten Spieltags."""
    if not snapshots:
        return []
    last_matchday = max(s.matchday_number for s in snapshots)
    current = [s for s in snapshots if s.matchday_number == last_matchday]
    return sorted(current, key=lambda s: s.rank_after_matchday)
