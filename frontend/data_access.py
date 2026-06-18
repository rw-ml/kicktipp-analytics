"""
Datenzugriff für das Dashboard. Liest bewusst NUR aus den Star-Schema-
Tabellen (dim_*/fact_*), genau wie Power BI das später auch tun wird - das
Dashboard ist damit eine Live-Vorschau auf exakt die Daten, die in Power BI
landen würden, unabhängig davon, ob sie aus dem echten Scraper oder aus
MockKicktippDataSource stammen.
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict
from functools import lru_cache

from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine

from kicktipp_analytics.calculation.evaluators.tendenz_tordifferenz_ergebnis import (
    TendenzTordifferenzErgebnisCalculator,
)
from kicktipp_analytics.domain.models import MatchResult, ScoreResult, Tip
from kicktipp_analytics.persistence.schema import (
    dim_match,
    dim_player,
    dim_team,
    fact_player_statistics,
    fact_ranking_snapshot,
    fact_tip,
)

_SCORE_CALCULATOR = TendenzTordifferenzErgebnisCalculator()


def _points_for_tipped_score(
    tipped_home: int, tipped_away: int, actual_home: int | None, actual_away: int | None
) -> int | None:
    """Wiederverwendung der echten Punkteregel, damit Dashboard und Pipeline
    garantiert dieselbe Logik anzeigen (keine Duplikation der Spielregeln)."""
    if actual_home is None or actual_away is None:
        return None
    tip = Tip(player_id="_", match_id="_", score_tip=ScoreResult(tipped_home, tipped_away))
    result = MatchResult(match_id="_", score=ScoreResult(actual_home, actual_away))
    return _SCORE_CALCULATOR.calculate(tip, result).points


def points_tier_class(points: int | None) -> str:
    """Ordnet eine Punktzahl einer CSS-Farbklasse zu. Die Liga-Regel selbst
    vergibt nur 0/2/3/4 Punkte pro Tipp - die Stufe 'points-1' existiert hier
    nur, damit sich andere Punkteregeln (z.B. 0-1-2-3-4-Skalen) jederzeit
    ohne Codeänderung an dieser Stelle einklinken könnten."""
    if points is None:
        return "points-unknown"
    if points >= 4:
        return "points-4"
    if points == 3:
        return "points-3"
    if points == 2:
        return "points-2"
    if points == 1:
        return "points-1"
    return "points-0"


def _connection_url() -> str:
    return os.environ.get("SQL_CONNECTION_URL", "sqlite:///sample.db")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(_connection_url())


def has_data() -> bool:
    with get_engine().connect() as conn:
        count = conn.execute(select(func.count()).select_from(dim_player)).scalar()
        return bool(count)


def latest_matchday_number() -> int | None:
    with get_engine().connect() as conn:
        return conn.execute(select(func.max(dim_match.c.matchday_number))).scalar()


def all_matchday_numbers() -> list[int]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(dim_match.c.matchday_number).distinct().order_by(dim_match.c.matchday_number)
        ).all()
        return [r[0] for r in rows]


def current_ranking() -> list[dict]:
    """Aktuelle Bestenliste inkl. Rangveränderung gegenüber dem vorherigen Spieltag."""
    last = latest_matchday_number()
    if last is None:
        return []

    with get_engine().connect() as conn:
        current_rows = conn.execute(
            select(
                fact_ranking_snapshot.c.player_id,
                dim_player.c.display_name,
                fact_ranking_snapshot.c.cumulative_points,
                fact_ranking_snapshot.c.cumulative_matchday_wins,
                fact_ranking_snapshot.c.rank_after_matchday,
            )
            .join(dim_player, dim_player.c.player_id == fact_ranking_snapshot.c.player_id)
            .where(fact_ranking_snapshot.c.matchday_number == last)
            .order_by(fact_ranking_snapshot.c.rank_after_matchday)
        ).all()

        previous_rank: dict[str, int] = {}
        if last > 1:
            prev_rows = conn.execute(
                select(
                    fact_ranking_snapshot.c.player_id,
                    fact_ranking_snapshot.c.rank_after_matchday,
                ).where(fact_ranking_snapshot.c.matchday_number == last - 1)
            ).all()
            previous_rank = {r.player_id: r.rank_after_matchday for r in prev_rows}

    ranking = []
    for row in current_rows:
        prev = previous_rank.get(row.player_id)
        if prev is None:
            trend = "neu"
        elif prev > row.rank_after_matchday:
            trend = "auf"
        elif prev < row.rank_after_matchday:
            trend = "ab"
        else:
            trend = "gleich"

        ranking.append(
            {
                "player_id": row.player_id,
                "display_name": row.display_name,
                "points": row.cumulative_points,
                "matchday_wins": row.cumulative_matchday_wins,
                "rank": row.rank_after_matchday,
                "trend": trend,
            }
        )
    return ranking


def formkurve_series() -> dict:
    """Pro Spieler eine Zeitreihe (Spieltag -> kumulierte Punkte) für das Liniendiagramm."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(
                fact_ranking_snapshot.c.player_id,
                dim_player.c.display_name,
                fact_ranking_snapshot.c.matchday_number,
                fact_ranking_snapshot.c.cumulative_points,
            )
            .join(dim_player, dim_player.c.player_id == fact_ranking_snapshot.c.player_id)
            .order_by(fact_ranking_snapshot.c.matchday_number)
        ).all()

    series: dict[str, dict] = {}
    matchdays: set[int] = set()
    for row in rows:
        matchdays.add(row.matchday_number)
        entry = series.setdefault(
            row.player_id, {"display_name": row.display_name, "points_by_matchday": {}}
        )
        entry["points_by_matchday"][row.matchday_number] = row.cumulative_points

    sorted_matchdays = sorted(matchdays)
    return {"matchdays": sorted_matchdays, "players": series}


def matchday_detail(matchday_number: int) -> dict:
    with get_engine().connect() as conn:
        home_team = dim_team.alias("home_team")
        away_team = dim_team.alias("away_team")

        match_rows = conn.execute(
            select(
                dim_match.c.match_id,
                dim_match.c.match_type,
                dim_match.c.kickoff,
                dim_match.c.actual_home_goals,
                dim_match.c.actual_away_goals,
                home_team.c.name.label("home_name"),
                away_team.c.name.label("away_name"),
            )
            .join(home_team, home_team.c.team_id == dim_match.c.home_team_id)
            .join(away_team, away_team.c.team_id == dim_match.c.away_team_id)
            .where(dim_match.c.matchday_number == matchday_number)
            .order_by(dim_match.c.kickoff)
        ).all()

        tip_rows = conn.execute(
            select(
                fact_tip.c.match_id,
                fact_tip.c.player_id,
                dim_player.c.display_name,
                fact_tip.c.tipped_home_goals,
                fact_tip.c.tipped_away_goals,
                fact_tip.c.points_awarded,
            )
            .join(dim_player, dim_player.c.player_id == fact_tip.c.player_id)
            .where(fact_tip.c.match_id.in_([m.match_id for m in match_rows]))
        ).all()

        points_rows = conn.execute(
            select(
                fact_ranking_snapshot.c.player_id,
                dim_player.c.display_name,
                fact_ranking_snapshot.c.points_this_matchday,
                fact_ranking_snapshot.c.is_matchday_winner,
            )
            .join(dim_player, dim_player.c.player_id == fact_ranking_snapshot.c.player_id)
            .where(fact_ranking_snapshot.c.matchday_number == matchday_number)
            .order_by(fact_ranking_snapshot.c.points_this_matchday.desc())
        ).all()

    tips_by_match: dict[str, list] = defaultdict(list)
    for t in tip_rows:
        tips_by_match[t.match_id].append(t)

    matches = []
    for m in match_rows:
        distribution: dict[tuple[int, int], list[str]] = defaultdict(list)
        for t in tips_by_match[m.match_id]:
            distribution[(t.tipped_home_goals, t.tipped_away_goals)].append(t.display_name)

        distribution_list = sorted(
            (
                {
                    "home_goals": hg,
                    "away_goals": ag,
                    "players": names,
                    "count": len(names),
                    "is_actual": (hg, ag) == (m.actual_home_goals, m.actual_away_goals),
                    "points": _points_for_tipped_score(
                        hg, ag, m.actual_home_goals, m.actual_away_goals
                    ),
                }
                for (hg, ag), names in distribution.items()
            ),
            key=lambda d: -d["count"],
        )
        for d in distribution_list:
            d["tier_class"] = points_tier_class(d["points"])

        matches.append(
            {
                "match_id": m.match_id,
                "home_name": m.home_name,
                "away_name": m.away_name,
                "match_type": m.match_type,
                "actual_home_goals": m.actual_home_goals,
                "actual_away_goals": m.actual_away_goals,
                "kickoff": m.kickoff,
                "tip_distribution": distribution_list,
            }
        )

    points_this_matchday = [
        {
            "display_name": p.display_name,
            "points": p.points_this_matchday,
            "is_matchday_winner": p.is_matchday_winner,
        }
        for p in points_rows
    ]

    return {"matches": matches, "points_this_matchday": points_this_matchday}


def assign_competition_rank(stats: list[dict], key: str) -> None:
    """
    Weist Rangplätze nach Sport-Ranking-Konvention zu: Gleichstände teilen
    sich denselben Rang, der nächste abweichende Wert überspringt die
    entsprechende Anzahl an Plätzen (z.B. drei Erstplatzierte -> 1., 1., 1.,
    4. statt fälschlich 1., 2., 3., 4.). Erwartet eine bereits nach `key`
    absteigend sortierte Liste; mutiert die Dicts um den Schlüssel "rank".
    """
    rank = 0
    previous_value = None
    for index, entry in enumerate(stats, start=1):
        value = entry[key]
        if value != previous_value:
            rank = index
            previous_value = value
        entry["rank"] = rank


def statistics_table() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(
                fact_player_statistics.c.player_id,
                dim_player.c.display_name,
                fact_player_statistics.c.total_tips,
                fact_player_statistics.c.exact_hits,
                fact_player_statistics.c.tendency_hits,
                fact_player_statistics.c.misses,
                fact_player_statistics.c.hit_rate,
            )
            .join(dim_player, dim_player.c.player_id == fact_player_statistics.c.player_id)
            .order_by(fact_player_statistics.c.hit_rate.desc())
        ).all()

    stats = [dict(r._mapping) for r in rows]
    assign_competition_rank(stats, key="hit_rate")
    max_misses = max((s["misses"] for s in stats), default=0)
    for s in stats:
        s["is_bremsfett_leader"] = s["misses"] == max_misses and max_misses > 0
    return stats


def list_players() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(dim_player.c.player_id, dim_player.c.display_name).order_by(
                dim_player.c.display_name
            )
        ).all()
    return [{"player_id": r.player_id, "display_name": r.display_name} for r in rows]


def _fetch_tips_with_team_context() -> list[dict]:
    """Jeder Tipp inkl. der Teams, die in diesem Spiel aufeinandertrafen -
    Grundlage für sämtliche Tippverhalten-Auswertungen."""
    home_team = dim_team.alias("home_team")
    away_team = dim_team.alias("away_team")
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(
                fact_tip.c.player_id,
                dim_player.c.display_name,
                fact_tip.c.tipped_home_goals,
                fact_tip.c.tipped_away_goals,
                dim_match.c.home_team_id,
                dim_match.c.away_team_id,
                home_team.c.name.label("home_team_name"),
                away_team.c.name.label("away_team_name"),
            )
            .join(dim_player, dim_player.c.player_id == fact_tip.c.player_id)
            .join(dim_match, dim_match.c.match_id == fact_tip.c.match_id)
            .join(home_team, home_team.c.team_id == dim_match.c.home_team_id)
            .join(away_team, away_team.c.team_id == dim_match.c.away_team_id)
        ).all()
    return [dict(r._mapping) for r in rows]


def _compute_tendency_overview(tip_rows: list[dict]) -> list[dict]:
    """Pro Spieler: Anteil Heimsieg-/Remis-/Auswärtssieg-Tipps. Reine Funktion
    (keine DB-Zugriffe) - dadurch ohne Datenbank testbar."""
    by_player: dict[str, dict] = {}
    for t in tip_rows:
        entry = by_player.setdefault(
            t["player_id"],
            {"display_name": t["display_name"], "home_win": 0, "draw": 0, "away_win": 0, "total": 0},
        )
        if t["tipped_home_goals"] > t["tipped_away_goals"]:
            entry["home_win"] += 1
        elif t["tipped_home_goals"] < t["tipped_away_goals"]:
            entry["away_win"] += 1
        else:
            entry["draw"] += 1
        entry["total"] += 1

    overview = []
    for player_id, e in by_player.items():
        total = e["total"] or 1
        overview.append(
            {
                "player_id": player_id,
                "display_name": e["display_name"],
                "total": e["total"],
                "home_win_pct": e["home_win"] / total * 100,
                "draw_pct": e["draw"] / total * 100,
                "away_win_pct": e["away_win"] / total * 100,
            }
        )
    overview.sort(key=lambda o: o["display_name"])
    return overview


def tip_behavior_overview() -> list[dict]:
    return _compute_tendency_overview(_fetch_tips_with_team_context())


#: Ab dieser Mindestanzahl an Tipps für ein Team wird eine Team-Tendenz
#: überhaupt erst angezeigt - sonst wäre ein einzelner Tipp schon ein
#: "Muster", was bei wenigen Spieltagen sehr leicht in die Irre führt.
_MIN_TEAM_APPEARANCES = 2
#: Ab dieser Abweichung (in Toren) vom eigenen Schnitt gilt ein Team als
#: auffällig bevorzugt/benachteiligt getippt.
_BIAS_THRESHOLD = 0.5


def _compute_player_detail(tip_rows: list[dict], player_id: str) -> dict | None:
    """Reine Auswertungsfunktion für einen einzelnen Spieler: häufigste
    getippte Ergebnisse und auffällige Team-Vorlieben. Erwartet bereits auf
    den Spieler gefilterte tip_rows (siehe tip_behavior_detail)."""
    if not tip_rows:
        return None

    display_name = tip_rows[0]["display_name"]
    total = len(tip_rows)

    scoreline_counts = Counter(
        (t["tipped_home_goals"], t["tipped_away_goals"]) for t in tip_rows
    )
    top_scorelines = [
        {
            "home_goals": hg,
            "away_goals": ag,
            "count": count,
            "pct": round(count / total * 100),
        }
        for (hg, ag), count in scoreline_counts.most_common(5)
    ]

    goals_by_team: dict[str, list[int]] = defaultdict(list)
    team_names: dict[str, str] = {}
    all_tipped_goals: list[int] = []
    for t in tip_rows:
        goals_by_team[t["home_team_id"]].append(t["tipped_home_goals"])
        goals_by_team[t["away_team_id"]].append(t["tipped_away_goals"])
        team_names[t["home_team_id"]] = t["home_team_name"]
        team_names[t["away_team_id"]] = t["away_team_name"]
        all_tipped_goals.append(t["tipped_home_goals"])
        all_tipped_goals.append(t["tipped_away_goals"])

    global_average = sum(all_tipped_goals) / len(all_tipped_goals) if all_tipped_goals else 0.0

    team_bias = []
    for team_id, goals in goals_by_team.items():
        if len(goals) < _MIN_TEAM_APPEARANCES:
            continue
        team_average = sum(goals) / len(goals)
        bias = team_average - global_average
        if abs(bias) >= _BIAS_THRESHOLD:
            team_bias.append(
                {
                    "team_name": team_names[team_id],
                    "average_goals": round(team_average, 1),
                    "bias": round(bias, 1),
                    "appearances": len(goals),
                    "direction": "favorit" if bias > 0 else "underdog",
                }
            )
    team_bias.sort(key=lambda b: -abs(b["bias"]))

    return {
        "display_name": display_name,
        "total_tips": total,
        "global_average_goals": round(global_average, 2),
        "top_scorelines": top_scorelines,
        "team_bias": team_bias,
    }


def tip_behavior_detail(player_id: str) -> dict | None:
    all_tips = _fetch_tips_with_team_context()
    player_tips = [t for t in all_tips if t["player_id"] == player_id]
    return _compute_player_detail(player_tips, player_id)