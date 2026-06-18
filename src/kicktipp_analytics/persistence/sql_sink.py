"""
IDataSink-Implementierung auf Basis von SQLAlchemy Core.

Funktioniert identisch gegen SQLite (lokale Tests, einfache Power-BI-
Desktop-Anbindung ohne eigenen DB-Server) und PostgreSQL (Produktivbetrieb
auf dem eigenen Server) - die Wahl ist allein eine Frage der
connection_url, der Code bleibt unverändert:

    SqlDataSink("sqlite:///kicktipp.db")
    SqlDataSink("postgresql+psycopg2://user:pass@host:5432/kicktipp")

Jede write_*-Methode ersetzt den kompletten Tabelleninhalt (Delete +
Insert) statt inkrementeller Upserts. Bei der Datenmenge eines privaten
Tippspiels (ein paar Dutzend Spiele, eine Handvoll Spieler) ist das völlig
ausreichend und deutlich einfacher als dialektübergreifende Upsert-Logik
(bewusste YAGNI-Entscheidung - ließe sich bei Bedarf später durch echte
Upserts ersetzen, ohne dass sich an der restlichen Pipeline etwas ändert).
"""
from __future__ import annotations

from sqlalchemy import create_engine, insert, update
from sqlalchemy.engine import Engine

from kicktipp_analytics.calculation.ranking import RankingSnapshot
from kicktipp_analytics.calculation.scoring_resolver import TipEvaluation
from kicktipp_analytics.calculation.statistics import PlayerStatistics
from kicktipp_analytics.domain.models import Match, MatchResult, Player, Team, Tip
from kicktipp_analytics.persistence.schema import (
    dim_match,
    dim_player,
    dim_team,
    fact_player_statistics,
    fact_ranking_snapshot,
    fact_tip,
    metadata,
)


class SqlDataSink:
    def __init__(self, connection_url: str):
        self._engine: Engine = create_engine(connection_url)
        metadata.create_all(self._engine)

    @property
    def engine(self) -> Engine:
        """Öffentlich für Tests/Power-BI-Connector-Konfiguration zugänglich."""
        return self._engine

    def write_dimensions(self, players: list[Player], matches: list[Match]) -> None:
        teams: dict[str, Team] = {}
        for m in matches:
            teams[m.home_team.id] = m.home_team
            teams[m.away_team.id] = m.away_team

        with self._engine.begin() as conn:
            conn.execute(dim_match.delete())
            conn.execute(dim_team.delete())
            conn.execute(dim_player.delete())

            if players:
                conn.execute(
                    insert(dim_player),
                    [{"player_id": p.id, "display_name": p.display_name} for p in players],
                )
            if teams:
                conn.execute(
                    insert(dim_team),
                    [
                        {"team_id": t.id, "name": t.name, "short_name": t.short_name}
                        for t in teams.values()
                    ],
                )
            if matches:
                conn.execute(
                    insert(dim_match),
                    [
                        {
                            "match_id": m.id,
                            "matchday_number": m.matchday.number,
                            "season": m.matchday.season,
                            "home_team_id": m.home_team.id,
                            "away_team_id": m.away_team.id,
                            "kickoff": m.kickoff,
                            "match_type": m.match_type.value,
                            "actual_home_goals": None,
                            "actual_away_goals": None,
                        }
                        for m in matches
                    ],
                )

    def write_results(self, results: list[MatchResult]) -> None:
        with self._engine.begin() as conn:
            for r in results:
                conn.execute(
                    update(dim_match)
                    .where(dim_match.c.match_id == r.match_id)
                    .values(
                        actual_home_goals=r.score.home_goals,
                        actual_away_goals=r.score.away_goals,
                    )
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
                    "tip_id": f"{tip.player_id}:{tip.match_id}",
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
                    "penalty_points_awarded": penalty_bd.points if penalty_bd else None,
                    "penalty_tip_correct": penalty_bd.is_exact_hit if penalty_bd else None,
                }
            )

        with self._engine.begin() as conn:
            conn.execute(fact_tip.delete())
            if rows:
                conn.execute(insert(fact_tip), rows)

    def write_ranking_snapshots(self, snapshots: list[RankingSnapshot]) -> None:
        with self._engine.begin() as conn:
            conn.execute(fact_ranking_snapshot.delete())
            if snapshots:
                conn.execute(
                    insert(fact_ranking_snapshot),
                    [
                        {
                            "snapshot_id": f"{s.player_id}:{s.matchday_number}",
                            "player_id": s.player_id,
                            "matchday_number": s.matchday_number,
                            "points_this_matchday": s.points_this_matchday,
                            "is_matchday_winner": s.is_matchday_winner,
                            "cumulative_points": s.cumulative_points,
                            "cumulative_matchday_wins": s.cumulative_matchday_wins,
                            "rank_after_matchday": s.rank_after_matchday,
                        }
                        for s in snapshots
                    ],
                )

    def write_statistics(self, statistics: list[PlayerStatistics]) -> None:
        with self._engine.begin() as conn:
            conn.execute(fact_player_statistics.delete())
            if statistics:
                conn.execute(
                    insert(fact_player_statistics),
                    [
                        {
                            "player_id": s.player_id,
                            "total_tips": s.total_tips,
                            "exact_hits": s.exact_hits,
                            "tendency_hits": s.tendency_hits,
                            "win_tips_correct": s.win_tips_correct,
                            "draw_tips_correct": s.draw_tips_correct,
                            "misses": s.misses,
                            "hit_rate": s.hit_rate,
                        }
                        for s in statistics
                    ],
                )