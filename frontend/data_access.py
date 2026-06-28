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

from sqlalchemy import Integer, create_engine, func, select
from sqlalchemy.engine import Engine

from kicktipp_analytics.calculation.evaluators.tendenz_tordifferenz_ergebnis import (
    TendenzTordifferenzErgebnisCalculator,
)
from kicktipp_analytics.domain.models import MatchResult, ScoreResult, Tip
from kicktipp_analytics.persistence.schema import (
    dim_match,
    dim_player,
    dim_team,
    fact_player_bonus,
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
    # fact_ranking_snapshot enthält nur tatsächlich gespielte Spieltage -
    # dim_match würde auch zukünftige Spieltage zurückgeben und damit
    # current_ranking() leer laufen lassen.
    with get_engine().connect() as conn:
        return conn.execute(
            select(func.max(fact_ranking_snapshot.c.matchday_number))
        ).scalar()


_MATCHDAY_ABBREVIATIONS: dict[str, str] = {
    "sechzehntelfinale": "SF",
    "16. finale": "SF",
    "achtelfinale": "AF",
    "8. finale": "AF",
    "viertelfinale": "VF",
    "4. finale": "VF",
    "halbfinale": "HF",
    "2. finale": "HF",
    "finale": "F",
    "spiel um platz 3": "3.",
}

# Vollständige Anzeigenamen für die Seitenüberschrift
_MATCHDAY_FULL_NAMES: dict[str, str] = {
    "sf": "Sechzehntelfinale",
    "af": "Achtelfinale",
    "vf": "Viertelfinale",
    "hf": "Halbfinale",
    "f": "Finale",
    "3.": "Spiel um Platz 3",
}


def _matchday_display(raw_name: str | None, matchday_number: int) -> dict:
    """Gibt abbrev (für Nav-Button) und title (für Seitenüberschrift) zurück."""
    if not raw_name:
        return {
            "abbrev": None,
            "title": f"Spieltag {matchday_number}",
            "is_group": True,
        }
    lower = raw_name.strip().lower()
    abbrev = _MATCHDAY_ABBREVIATIONS.get(lower)
    if abbrev:
        full = _MATCHDAY_FULL_NAMES.get(abbrev.lower(), raw_name)
        return {"abbrev": abbrev, "title": full, "is_group": False}
    # Gruppenphase: "Spieltag N" oder ähnliches
    return {"abbrev": None, "title": raw_name, "is_group": True}


def all_matchday_numbers() -> list[int]:
    """Rückwärtskompatibel – gibt nur die Nummern zurück."""
    return [m["number"] for m in all_matchdays()]


def all_matchdays() -> list[dict]:
    """Alle Spieltage mit Nummer, Titel und Nav-Abkürzung."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(
                dim_match.c.matchday_number,
                dim_match.c.matchday_name,
            )
            .distinct()
            .order_by(dim_match.c.matchday_number)
        ).all()
    seen: set[int] = set()
    result = []
    for r in rows:
        if r.matchday_number in seen:
            continue
        seen.add(r.matchday_number)
        display = _matchday_display(r.matchday_name, r.matchday_number)
        result.append({"number": r.matchday_number, **display})
    return result


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

        # Bonus zuerst lesen – wird für Trend-Berechnung (previous_rank) gebraucht
        bonus_rows = conn.execute(
            select(
                fact_player_bonus.c.player_id,
                fact_player_bonus.c.bonus_points,
                fact_player_bonus.c.siege,
            )
        ).all()
        bonus_by_player = {r.player_id: r.bonus_points for r in bonus_rows}
        siege_by_player = {r.player_id: r.siege for r in bonus_rows}

        previous_rank: dict[str, int] = {}
        if last > 1:
            prev_rows = conn.execute(
                select(
                    fact_ranking_snapshot.c.player_id,
                    fact_ranking_snapshot.c.cumulative_points,
                ).where(fact_ranking_snapshot.c.matchday_number == last - 1)
            ).all()
            sorted_prev = sorted(
                prev_rows,
                key=lambda r: (
                    -(r.cumulative_points + bonus_by_player.get(r.player_id, 0)),
                    -siege_by_player.get(r.player_id, 0.0),
                ),
            )
            previous_rank = {r.player_id: rank for rank, r in enumerate(sorted_prev, start=1)}

        # Anzahl Spieltage mit echten Tipps pro Spieler (für korrekten Durchschnitt)
        tip_counts = conn.execute(
            select(
                fact_tip.c.player_id,
                func.count(func.distinct(dim_match.c.matchday_number)).label("tip_matchdays"),
            )
            .join(dim_match, dim_match.c.match_id == fact_tip.c.match_id)
            .group_by(fact_tip.c.player_id)
        ).all()
        tip_matchdays_by_player = {r.player_id: r.tip_matchdays for r in tip_counts}

    max_tip_matchdays = max(tip_matchdays_by_player.values(), default=1)

    ranking = []
    for row in current_rows:
        tip_md = tip_matchdays_by_player.get(row.player_id, 1)
        bonus = bonus_by_player.get(row.player_id, 0)
        siege = siege_by_player.get(row.player_id, 0.0)
        tip_points = row.cumulative_points
        ranking.append(
            {
                "player_id": row.player_id,
                "display_name": row.display_name,
                "tip_points": tip_points,
                "bonus_points": bonus,
                "points": tip_points + bonus,
                "matchday_wins": siege,
                "rank": 0,   # wird gleich gesetzt
                "trend": "gleich",  # wird gleich gesetzt
                "average_points_per_matchday": round(tip_points / tip_md, 1),
                "tip_matchdays": tip_md,
                "max_tip_matchdays": max_tip_matchdays,
                "tip_completeness": tip_md / max_tip_matchdays,
            }
        )

    # Rang inkl. Bonus berechnen
    ranking.sort(key=lambda e: (-(e["tip_points"] + e["bonus_points"]), -e["matchday_wins"]))
    for i, entry in enumerate(ranking, start=1):
        entry["rank"] = i

    # Trend erst NACH der Neusortierung berechnen – Vergleich neuer Rang vs. Vorgänger-Rang
    for entry in ranking:
        prev = previous_rank.get(entry["player_id"])
        if prev is None:
            entry["trend"] = "neu"
        elif prev > entry["rank"]:
            entry["trend"] = "auf"
        elif prev < entry["rank"]:
            entry["trend"] = "ab"
        else:
            entry["trend"] = "gleich"

    return ranking


def _last_tip_matchday_per_player() -> dict[str, int]:
    """Letzter Spieltag an dem jeder Spieler tatsächlich getippt hat.
    Basis für das Dashed-Styling in den Charts."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(
                fact_tip.c.player_id,
                func.max(dim_match.c.matchday_number).label("last_matchday"),
            )
            .join(dim_match, dim_match.c.match_id == fact_tip.c.match_id)
            .group_by(fact_tip.c.player_id)
        ).all()
    return {r.player_id: r.last_matchday for r in rows}


def _bonus_per_player() -> dict[str, int]:
    """Bonuspunkte pro Spieler aus fact_player_bonus."""
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                select(fact_player_bonus.c.player_id, fact_player_bonus.c.bonus_points)
            ).all()
        return {r.player_id: r.bonus_points for r in rows}
    except Exception:
        return {}


def formkurve_series() -> dict:
    """Pro Spieler eine Zeitreihe (Spieltag -> Gesamtpunkte inkl. Bonus).
    Index 0 = Bonuspunkte als Startpunkt (vor Spieltag 1)."""
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

    last_tip = _last_tip_matchday_per_player()
    bonus = _bonus_per_player()
    series: dict[str, dict] = {}
    matchdays: set[int] = set()
    for row in rows:
        matchdays.add(row.matchday_number)
        b = bonus.get(row.player_id, 0)
        entry = series.setdefault(
            row.player_id,
            {
                "display_name": row.display_name,
                "points_by_matchday": {},
                "last_tip_matchday": last_tip.get(row.player_id, 0),
                "bonus_points": b,
            },
        )
        # Gesamtpunkte = Tipppunkte kumuliert + Bonus
        entry["points_by_matchday"][row.matchday_number] = row.cumulative_points + b

    sorted_matchdays = sorted(matchdays)
    return {"matchdays": sorted_matchdays, "players": series}


def rank_history_series() -> dict:
    """Pro Spieler eine Zeitreihe (Spieltag -> Rang inkl. Bonus).
    Ränge werden pro Spieltag neu berechnet unter Einbeziehung der Bonuspunkte
    und des Kicktipp-Siege-Wertes (kann Bruchteile haben) als Tiebreaker."""
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

        # Bonus und Siege (fraktional) aus fact_player_bonus
        bonus_rows = conn.execute(
            select(
                fact_player_bonus.c.player_id,
                fact_player_bonus.c.bonus_points,
                fact_player_bonus.c.siege,
            )
        ).all()

    bonus = {r.player_id: r.bonus_points for r in bonus_rows}
    siege = {r.player_id: r.siege for r in bonus_rows}
    last_tip = _last_tip_matchday_per_player()

    from collections import defaultdict
    by_matchday: dict[int, list] = defaultdict(list)
    display_names: dict[str, str] = {}
    for row in rows:
        by_matchday[row.matchday_number].append(row)
        display_names[row.player_id] = row.display_name

    series: dict[str, dict] = {
        pid: {
            "display_name": display_names[pid],
            "rank_by_matchday": {},
            "last_tip_matchday": last_tip.get(pid, 0),
        }
        for pid in display_names
    }
    matchdays: set[int] = set()
    max_rank = 1

    for matchday, md_rows in by_matchday.items():
        matchdays.add(matchday)
        # Sortierung: Gesamtpunkte DESC, dann Kicktipp-Siege DESC (inkl. Bruchteile)
        sorted_rows = sorted(
            md_rows,
            key=lambda r: (
                -(r.cumulative_points + bonus.get(r.player_id, 0)),
                -siege.get(r.player_id, 0.0),
            ),
        )
        for rank, row in enumerate(sorted_rows, start=1):
            series[row.player_id]["rank_by_matchday"][matchday] = rank
            max_rank = max(max_rank, rank)

    sorted_matchdays = sorted(matchdays)
    return {"matchdays": sorted_matchdays, "players": series, "max_rank": max_rank}


def _build_scale_ticks(max_count: int) -> list[dict]:
    """
    Lineal-Striche für die Tippverteilungs-Balken: ein dünner Strich für
    jede ganze Zahl, ein dickerer für jeden 5er und ein noch dickerer für
    jeden 10er - damit lässt sich die Anzahl der Tippspieler direkt am
    Balken ablesen, auch wenn die Balkenlänge relativ zum häufigsten Tipp
    in diesem Spiel skaliert ist (der häufigste Tipp füllt die Spalte fast
    komplett aus).
    """
    ticks = []
    for n in range(1, max_count + 1):
        if n % 10 == 0:
            thickness = "thick"
        elif n % 5 == 0:
            thickness = "medium"
        else:
            thickness = "thin"
        ticks.append({"position_pct": round(n / max_count * 100, 2), "thickness": thickness})
    return ticks


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
        max_count = distribution_list[0]["count"] if distribution_list else 0
        for d in distribution_list:
            d["tier_class"] = points_tier_class(d["points"])
            d["bar_pct"] = round(d["count"] / max_count * 100, 2) if max_count else 0

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
                "scale_ticks": _build_scale_ticks(max_count),
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
    average_points_this_matchday = (
        round(sum(p["points"] for p in points_this_matchday) / len(points_this_matchday), 1)
        if points_this_matchday
        else 0.0
    )

    return {
        "matches": matches,
        "points_this_matchday": points_this_matchday,
        "average_points_this_matchday": average_points_this_matchday,
    }


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


def details_data() -> dict:
    """Kombinierte Daten für die Details-Seite.
    Qualitäts-Statistiken werden direkt aus fact_tip berechnet (immer aktuell),
    nicht aus fact_player_statistics (könnte veraltet sein wenn Pipeline-Fehler).
    """
    # ── Rang aus dem aktuellen Ranking ──────────────────────────────
    ranking = current_ranking()
    rank_by_player = {r["player_id"]: r["rank"] for r in ranking}

    # ── Qualitäts-Statistiken live aus fact_tip ───────────────────────
    # fact_tip enthält is_tendency_correct, is_goal_difference_correct,
    # is_exact_hit direkt als Spalten - kein Umweg über fact_player_statistics nötig.
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(
                fact_tip.c.player_id,
                dim_player.c.display_name,
                func.count().label("total_tips"),
                func.sum(func.cast(fact_tip.c.is_tendency_correct, Integer)).label("tendency_hits"),
                func.sum(
                    func.cast(
                        (fact_tip.c.is_goal_difference_correct == True) &  # noqa: E712
                        (fact_tip.c.is_exact_hit == False),  # noqa: E712
                        Integer,
                    )
                ).label("goal_difference_hits"),
                func.sum(func.cast(fact_tip.c.is_exact_hit, Integer)).label("exact_hits"),
                func.sum(func.cast(fact_tip.c.points_awarded == 0, Integer)).label("misses"),
            )
            .join(dim_player, dim_player.c.player_id == fact_tip.c.player_id)
            .group_by(fact_tip.c.player_id, dim_player.c.display_name)
        ).all()

    stats_by_player = {r.player_id: dict(r._mapping) for r in rows}

    # ── Tendenz-Verhalten (Sieg/Unentsch. Tipps + Treffer) ──────────
    tendency_by_player = {
        o["player_id"]: o
        for o in _compute_tendency_overview(_fetch_tips_with_team_context())
    }

    # ── Ergebnis-Qualität zusammenbauen ──────────────────────────────
    quality_rows = []
    for player_id, s in stats_by_player.items():
        total = s["total_tips"] or 0
        tendency = s["tendency_hits"] or 0
        goal_diff = s["goal_difference_hits"] or 0
        exact = s["exact_hits"] or 0
        misses = s["misses"] or 0
        goal_diff_total = goal_diff + exact

        quality_rows.append({
            "player_id": player_id,
            "display_name": s["display_name"],
            "rank": rank_by_player.get(player_id, "–"),
            "total_tips": total,
            "tendency_hits": tendency,
            "goal_difference_hits": goal_diff_total,
            "exact_hits": exact,
            "misses": misses,
            "hit_rate_tendency": round(tendency / total * 100, 1) if total else 0,
            "hit_rate_goaldiff": round(goal_diff_total / total * 100, 1) if total else 0,
            "hit_rate_exact": round(exact / total * 100, 1) if total else 0,
        })

    max_misses = max((r["misses"] for r in quality_rows), default=0)
    for r in quality_rows:
        r["is_bremsfett"] = r["misses"] == max_misses and max_misses > 0

    # Gleiche Reihenfolge wie Bestenliste (nach Rang, Spieler ohne Rang ans Ende)
    quality_rows.sort(key=lambda r: r["rank"] if isinstance(r["rank"], int) else 9999)

    # ── Tendenz-Verhalten zusammenbauen ──────────────────────────────
    tendency_rows = [
        {
            "player_id": player_id,
            "display_name": t["display_name"],
            "rank": rank_by_player.get(player_id, "–"),
            "win_total": t["win_total"],
            "win_correct": t["win_correct"],
            "draw_total": t["draw_total"],
            "draw_correct": t["draw_correct"],
        }
        for player_id, t in tendency_by_player.items()
    ]
    tendency_rows.sort(key=lambda r: r["display_name"])

    tip_rows = _fetch_tips_with_team_context()
    return {
        "quality": quality_rows,
        "tendency": tendency_rows,
        "similarity": _compute_similarity_matrix(tip_rows),
        "players": list_players(),
    }


def statistics_table() -> list[dict]:
    """Rückwärtskompatibel – intern durch details_data() abgedeckt."""
    return details_data()["quality"]


def list_players() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(dim_player.c.player_id, dim_player.c.display_name).order_by(
                dim_player.c.display_name
            )
        ).all()
    return [{"player_id": r.player_id, "display_name": r.display_name} for r in rows]


def _fetch_tips_with_team_context() -> list[dict]:
    """Jeder Tipp inkl. der Teams, die in diesem Spiel aufeinandertrafen, und
    dem tatsächlichen Ergebnis (falls schon gespielt) - Grundlage für
    sämtliche Tippverhalten-Auswertungen."""
    home_team = dim_team.alias("home_team")
    away_team = dim_team.alias("away_team")
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(
                fact_tip.c.player_id,
                dim_player.c.display_name,
                fact_tip.c.match_id,
                fact_tip.c.tipped_home_goals,
                fact_tip.c.tipped_away_goals,
                dim_match.c.home_team_id,
                dim_match.c.away_team_id,
                dim_match.c.actual_home_goals,
                dim_match.c.actual_away_goals,
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
    """
    Pro Spieler: wie oft wurde auf eine Entscheidung (Sieg) bzw. ein
    Unentschieden getippt, und wie oft lag der Tipp dabei richtig.

    Heim- und Auswärtssieg fließen in eine gemeinsame "Sieg"-Kategorie ein
    (bei einem Turnier auf neutralem Platz keine sinnvolle Trennung) - die
    korrekte Seite muss für "richtig" aber natürlich trotzdem stimmen.
    Nur bereits ausgewertete Spiele (mit bekanntem Ergebnis) zählen, sonst
    würden offene Tipps die Trefferquote künstlich verwässern.
    Reine Funktion (keine DB-Zugriffe) - dadurch ohne Datenbank testbar.
    """
    by_player: dict[str, dict] = {}
    for t in tip_rows:
        entry = by_player.setdefault(
            t["player_id"],
            {
                "display_name": t["display_name"],
                "win_total": 0,
                "win_correct": 0,
                "draw_total": 0,
                "draw_correct": 0,
            },
        )
        if t["actual_home_goals"] is None:
            continue  # Spiel noch nicht gespielt - fließt nicht in die Quote ein

        tipped_is_draw = t["tipped_home_goals"] == t["tipped_away_goals"]
        actual_is_draw = t["actual_home_goals"] == t["actual_away_goals"]

        if tipped_is_draw:
            entry["draw_total"] += 1
            if actual_is_draw:
                entry["draw_correct"] += 1
        else:
            entry["win_total"] += 1
            if not actual_is_draw:
                tipped_home_wins = t["tipped_home_goals"] > t["tipped_away_goals"]
                actual_home_wins = t["actual_home_goals"] > t["actual_away_goals"]
                if tipped_home_wins == actual_home_wins:
                    entry["win_correct"] += 1

    overview = [
        {
            "player_id": player_id,
            "display_name": e["display_name"],
            "win_total": e["win_total"],
            "win_correct": e["win_correct"],
            "draw_total": e["draw_total"],
            "draw_correct": e["draw_correct"],
        }
        for player_id, e in by_player.items()
    ]
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
_BIAS_THRESHOLD = 1.5


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
    all_scorelines = [
        {
            "home_goals": hg,
            "away_goals": ag,
            "count": count,
            "pct": round(count / total * 100),
        }
        for (hg, ag), count in scoreline_counts.most_common()
    ]
    top_scorelines = all_scorelines[:5]

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
        "all_scorelines": all_scorelines,
        "team_bias": team_bias,
    }


def tip_behavior_detail(player_id: str) -> dict | None:
    all_tips = _fetch_tips_with_team_context()
    player_tips = [t for t in all_tips if t["player_id"] == player_id]
    return _compute_player_detail(player_tips, player_id)


def _tendency_label(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if home_goals < away_goals:
        return "away"
    return "draw"


def _compute_similarity_matrix(tip_rows: list[dict]) -> dict:
    """
    Pragmatischer Ersatz für eine vollständige Cluster-Analyse (für eine
    private Tippspielrunde mit überschaubarer Spielerzahl aussagekräftiger
    als z.B. k-means): für jedes Spielerpaar wird der Anteil der gemeinsam
    getippten Spiele berechnet, bei denen beide dieselbe Tendenz (Heimsieg/
    Remis/Auswärtssieg) getippt haben. Reine Funktion, keine DB-Zugriffe.
    """
    by_match: dict[str, list[dict]] = defaultdict(list)
    for t in tip_rows:
        by_match[t["match_id"]].append(t)

    display_names: dict[str, str] = {}
    common_count: dict[tuple[str, str], int] = defaultdict(int)
    same_tendency_count: dict[tuple[str, str], int] = defaultdict(int)

    for tips_in_match in by_match.values():
        for t in tips_in_match:
            display_names[t["player_id"]] = t["display_name"]
        for i in range(len(tips_in_match)):
            for j in range(i + 1, len(tips_in_match)):
                a, b = tips_in_match[i], tips_in_match[j]
                key = tuple(sorted((a["player_id"], b["player_id"])))
                common_count[key] += 1
                tendency_a = _tendency_label(a["tipped_home_goals"], a["tipped_away_goals"])
                tendency_b = _tendency_label(b["tipped_home_goals"], b["tipped_away_goals"])
                if tendency_a == tendency_b:
                    same_tendency_count[key] += 1

    players = sorted(display_names.keys(), key=lambda p: display_names[p])
    matrix = []
    for p1 in players:
        row = []
        for p2 in players:
            if p1 == p2:
                row.append(None)
                continue
            key = tuple(sorted((p1, p2)))
            common = common_count.get(key, 0)
            same = same_tendency_count.get(key, 0)
            row.append(round(same / common * 100) if common else None)
        matrix.append(row)

    return {
        "player_ids": players,
        "display_names": [display_names[p] for p in players],
        "matrix": matrix,
    }


def player_similarity_matrix() -> dict:
    return _compute_similarity_matrix(_fetch_tips_with_team_context())