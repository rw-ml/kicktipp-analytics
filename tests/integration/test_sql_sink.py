from datetime import datetime

from kicktipp_analytics.calculation.interfaces import PointsBreakdown
from kicktipp_analytics.calculation.ranking import RankingSnapshot
from kicktipp_analytics.calculation.scoring_resolver import TipEvaluation
from kicktipp_analytics.calculation.statistics import PlayerStatistics
from kicktipp_analytics.domain.models import (
    Match,
    MatchResult,
    MatchType,
    Matchday,
    Player,
    ScoreResult,
    Team,
    Tip,
)
from kicktipp_analytics.persistence.schema import dim_match, dim_player, fact_tip
from kicktipp_analytics.persistence.sql_sink import SqlDataSink


def test_sql_sink_roundtrip(tmp_path):
    db_path = tmp_path / "test.db"
    sink = SqlDataSink(f"sqlite:///{db_path}")

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

    sink.write_results([MatchResult(match_id="m1", score=ScoreResult(2, 1))])

    tip = Tip(player_id="p1", match_id="m1", score_tip=ScoreResult(2, 1))
    breakdown = PointsBreakdown(
        points=4, is_tendency_correct=True, is_goal_difference_correct=True, is_exact_hit=True
    )
    evaluation = TipEvaluation(
        match_id="m1", player_id="p1", total_points=4, breakdowns={"score": breakdown}
    )
    sink.write_tip_evaluations([tip], [evaluation])

    snapshot = RankingSnapshot(
        player_id="p1",
        matchday_number=1,
        points_this_matchday=4,
        is_matchday_winner=True,
        cumulative_points=4,
        cumulative_matchday_wins=1,
        rank_after_matchday=1,
    )
    sink.write_ranking_snapshots([snapshot])

    stats = PlayerStatistics(
        player_id="p1",
        total_tips=1,
        exact_hits=1,
        tendency_hits=1,
        home_win_tips_correct=1,
        draw_tips_correct=0,
        away_win_tips_correct=0,
        misses=0,
        hit_rate=1.0,
    )
    sink.write_statistics([stats])

    with sink.engine.connect() as conn:
        player_rows = conn.execute(dim_player.select()).fetchall()
        assert len(player_rows) == 1
        assert player_rows[0].display_name == "Alice"

        tip_rows = conn.execute(fact_tip.select()).fetchall()
        assert tip_rows[0].points_awarded == 4

        match_rows = conn.execute(dim_match.select()).fetchall()
        assert match_rows[0].actual_home_goals == 2
        assert match_rows[0].actual_away_goals == 1