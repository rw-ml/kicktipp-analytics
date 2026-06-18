"""
Alternative IDataSink-Implementierung ohne Datenbank: schreibt jede Tabelle
als eigene CSV-Datei. Praktisch für Power BI Desktop ohne DB-Treiber/Gateway
oder zum schnellen lokalen Testen. Implementiert exakt dasselbe Protocol wie
SqlDataSink - beide können in derselben Pipeline gleichzeitig verwendet
werden (siehe scheduler/run_pipeline.py), wodurch die Pipeline unabhängig
davon funktioniert, ob später Power BI Desktop (Dateien/lokale DB) oder
Power BI Pro/Premium mit Gateway (zentrale DB) zum Einsatz kommt.
"""
from __future__ import annotations

import csv
import os
from dataclasses import asdict

from kicktipp_analytics.calculation.ranking import RankingSnapshot
from kicktipp_analytics.calculation.scoring_resolver import TipEvaluation
from kicktipp_analytics.calculation.statistics import PlayerStatistics
from kicktipp_analytics.domain.models import Match, MatchResult, Player, Team, Tip


class CsvDataSink:
    def __init__(self, output_dir: str):
        self._dir = output_dir
        os.makedirs(self._dir, exist_ok=True)

    def _write_rows(self, filename: str, rows: list[dict]) -> None:
        path = os.path.join(self._dir, filename)
        if not rows:
            open(path, "w", encoding="utf-8").close()
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def write_dimensions(self, players: list[Player], matches: list[Match]) -> None:
        teams: dict[str, Team] = {}
        for m in matches:
            teams[m.home_team.id] = m.home_team
            teams[m.away_team.id] = m.away_team

        self._write_rows(
            "dim_player.csv",
            [{"player_id": p.id, "display_name": p.display_name} for p in players],
        )
        self._write_rows(
            "dim_team.csv",
            [
                {"team_id": t.id, "name": t.name, "short_name": t.short_name}
                for t in teams.values()
            ],
        )
        self._write_rows(
            "dim_match.csv",
            [
                {
                    "match_id": m.id,
                    "matchday_number": m.matchday.number,
                    "season": m.matchday.season,
                    "home_team_id": m.home_team.id,
                    "away_team_id": m.away_team.id,
                    "kickoff": m.kickoff.isoformat(),
                    "match_type": m.match_type.value,
                }
                for m in matches
            ],
        )

    def write_results(self, results: list[MatchResult]) -> None:
        self._write_rows(
            "fact_results.csv",
            [
                {
                    "match_id": r.match_id,
                    "home_goals": r.score.home_goals,
                    "away_goals": r.score.away_goals,
                }
                for r in results
            ],
        )

    def write_tip_evaluations(
        self, tips: list[Tip], evaluations: list[TipEvaluation]
    ) -> None:
        eval_by_key = {(e.player_id, e.match_id): e for e in evaluations}
        rows = []
        for tip in tips:
            ev = eval_by_key.get((tip.player_id, tip.match_id))
            if ev is None:
                continue
            score_bd = ev.breakdowns.get("score")
            penalty_bd = ev.breakdowns.get("penalty_shootout")
            rows.append(
                {
                    "player_id": tip.player_id,
                    "match_id": tip.match_id,
                    "tipped_home_goals": tip.score_tip.home_goals,
                    "tipped_away_goals": tip.score_tip.away_goals,
                    "points_awarded": ev.total_points,
                    "is_tendency_correct": bool(score_bd and score_bd.is_tendency_correct),
                    "is_goal_difference_correct": bool(
                        score_bd and score_bd.is_goal_difference_correct
                    ),
                    "is_exact_hit": bool(score_bd and score_bd.is_exact_hit),
                    "penalty_points_awarded": penalty_bd.points if penalty_bd else "",
                    "penalty_tip_correct": penalty_bd.is_exact_hit if penalty_bd else "",
                }
            )
        self._write_rows("fact_tip.csv", rows)

    def write_ranking_snapshots(self, snapshots: list[RankingSnapshot]) -> None:
        self._write_rows("fact_ranking_snapshot.csv", [asdict(s) for s in snapshots])

    def write_statistics(self, statistics: list[PlayerStatistics]) -> None:
        self._write_rows("fact_player_statistics.csv", [asdict(s) for s in statistics])
