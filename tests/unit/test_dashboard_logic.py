"""
Tests für die reinen Auswertungsfunktionen des Dashboards (data_access.py).
Bewusst ohne Datenbank - die DB-Zugriffsfunktionen sind dünne Wrapper um
diese reinen Funktionen, sodass sich die eigentliche Logik isoliert testen
lässt (genau wie in der calculation-Schicht der Pipeline).
"""
from data_access import (
    _compute_player_detail,
    _compute_similarity_matrix,
    _compute_tendency_overview,
    assign_competition_rank,
    points_tier_class,
)


def test_competition_rank_handles_ties_correctly():
    # Drei Spieler mit identischer Trefferquote teilen sich Rang 1,
    # der nächste abweichende Wert landet auf Rang 4 (nicht 2).
    stats = [
        {"display_name": "Anna", "hit_rate": 0.8},
        {"display_name": "Bernd", "hit_rate": 0.8},
        {"display_name": "Carla", "hit_rate": 0.8},
        {"display_name": "David", "hit_rate": 0.5},
    ]
    assign_competition_rank(stats, key="hit_rate")
    assert [s["rank"] for s in stats] == [1, 1, 1, 4]


def test_competition_rank_without_ties_is_sequential():
    stats = [{"hit_rate": 0.9}, {"hit_rate": 0.7}, {"hit_rate": 0.5}]
    assign_competition_rank(stats, key="hit_rate")
    assert [s["rank"] for s in stats] == [1, 2, 3]


def test_points_tier_class_mapping():
    assert points_tier_class(4) == "points-4"
    assert points_tier_class(3) == "points-3"
    assert points_tier_class(2) == "points-2"
    assert points_tier_class(1) == "points-1"
    assert points_tier_class(0) == "points-0"
    assert points_tier_class(None) == "points-unknown"


def _tip(player_id, name, home_goals, away_goals, home_team="A", away_team="B", home_name="Team A", away_name="Team B", match_id="m1"):
    return {
        "player_id": player_id,
        "display_name": name,
        "match_id": match_id,
        "tipped_home_goals": home_goals,
        "tipped_away_goals": away_goals,
        "home_team_id": home_team,
        "away_team_id": away_team,
        "home_team_name": home_name,
        "away_team_name": away_name,
    }


def test_tendency_overview_counts_home_draw_away_correctly():
    tips = [
        _tip("anna", "Anna", 2, 1),  # Heimsieg
        _tip("anna", "Anna", 1, 1),  # Remis
        _tip("anna", "Anna", 0, 2),  # Auswärtssieg
        _tip("anna", "Anna", 3, 0),  # Heimsieg
    ]
    overview = _compute_tendency_overview(tips)
    anna = overview[0]
    assert anna["total"] == 4
    assert anna["home_win_pct"] == 50.0
    assert anna["draw_pct"] == 25.0
    assert anna["away_win_pct"] == 25.0


def test_player_detail_finds_top_scoreline_and_team_bias():
    tips = [
        _tip("anna", "Anna", 3, 0, home_team="favorit", home_name="Favoritenteam"),
        _tip("anna", "Anna", 3, 1, home_team="favorit", home_name="Favoritenteam"),
        _tip("anna", "Anna", 1, 1, home_team="neutral", home_name="Neutralteam"),
        _tip("anna", "Anna", 1, 1, home_team="neutral", home_name="Neutralteam"),
    ]
    detail = _compute_player_detail(tips, "anna")

    assert detail["display_name"] == "Anna"
    assert detail["total_tips"] == 4
    assert detail["top_scorelines"][0]["home_goals"] == 1
    assert detail["top_scorelines"][0]["away_goals"] == 1
    assert detail["top_scorelines"][0]["count"] == 2

    bias_by_team = {b["team_name"]: b for b in detail["team_bias"]}
    assert "Favoritenteam" in bias_by_team
    assert bias_by_team["Favoritenteam"]["direction"] == "favorit"


def test_player_detail_returns_none_for_unknown_player():
    assert _compute_player_detail([], "unbekannt") is None


def test_similarity_matrix_finds_matching_and_diverging_tendencies():
    tips = [
        # Spiel 1: Anna und Bernd tippen beide Heimsieg -> gleiche Tendenz
        _tip("anna", "Anna", 2, 0, match_id="m1"),
        _tip("bernd", "Bernd", 1, 0, match_id="m1"),
        # Spiel 2: Anna tippt Heimsieg, Bernd tippt Auswärtssieg -> unterschiedlich
        _tip("anna", "Anna", 1, 0, match_id="m2"),
        _tip("bernd", "Bernd", 0, 1, match_id="m2"),
    ]
    matrix = _compute_similarity_matrix(tips)

    assert matrix["display_names"] == ["Anna", "Bernd"]
    anna_idx, bernd_idx = 0, 1
    # Übereinstimmung in 1 von 2 gemeinsamen Spielen -> 50%
    assert matrix["matrix"][anna_idx][bernd_idx] == 50
    assert matrix["matrix"][bernd_idx][anna_idx] == 50
    # Diagonale (Spieler mit sich selbst) bleibt leer
    assert matrix["matrix"][anna_idx][anna_idx] is None


def test_similarity_matrix_returns_none_for_players_without_common_matches():
    tips = [
        _tip("anna", "Anna", 1, 0, match_id="m1"),
        _tip("carla", "Carla", 0, 1, match_id="m2"),
    ]
    matrix = _compute_similarity_matrix(tips)
    anna_idx = matrix["display_names"].index("Anna")
    carla_idx = matrix["display_names"].index("Carla")
    assert matrix["matrix"][anna_idx][carla_idx] is None