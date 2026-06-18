import csv
from datetime import datetime

from kicktipp_analytics.domain.models import Match, MatchType, Matchday, Player, Team
from kicktipp_analytics.persistence.csv_sink import CsvDataSink


def test_csv_sink_writes_dimension_files(tmp_path):
    sink = CsvDataSink(str(tmp_path))
    players = [Player(id="p1", display_name="Alice")]
    match = Match(
        id="m1",
        matchday=Matchday(number=1, season="wm2026"),
        home_team=Team(id="A", name="Team A"),
        away_team=Team(id="B", name="Team B"),
        kickoff=datetime(2026, 6, 15, 18, 0),
        match_type=MatchType.GROUP,
    )

    sink.write_dimensions(players, [match])

    with open(tmp_path / "dim_player.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["display_name"] == "Alice"

    with open(tmp_path / "dim_match.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["match_type"] == "group"
