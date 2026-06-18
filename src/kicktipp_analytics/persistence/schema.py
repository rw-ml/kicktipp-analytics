"""
Star-Schema für Power BI: drei Dimensionstabellen plus drei Faktentabellen.
Mit SQLAlchemy Core definiert, damit dieselbe Definition identisch gegen
SQLite (Tests, einfache Power-BI-Desktop-Anbindung) und PostgreSQL
(Produktivbetrieb) funktioniert.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
)

metadata = MetaData()

dim_player = Table(
    "dim_player",
    metadata,
    Column("player_id", String, primary_key=True),
    Column("display_name", String, nullable=False),
)

dim_team = Table(
    "dim_team",
    metadata,
    Column("team_id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("short_name", String),
)

dim_match = Table(
    "dim_match",
    metadata,
    Column("match_id", String, primary_key=True),
    Column("matchday_number", Integer, nullable=False),
    Column("season", String, nullable=False),
    Column("home_team_id", String, ForeignKey("dim_team.team_id")),
    Column("away_team_id", String, ForeignKey("dim_team.team_id")),
    Column("kickoff", DateTime, nullable=False),
    Column("match_type", String, nullable=False),
    Column("actual_home_goals", Integer),
    Column("actual_away_goals", Integer),
)

fact_tip = Table(
    "fact_tip",
    metadata,
    Column("tip_id", String, primary_key=True),  # player_id:match_id
    Column("player_id", String, ForeignKey("dim_player.player_id")),
    Column("match_id", String, ForeignKey("dim_match.match_id")),
    Column("tipped_home_goals", Integer, nullable=False),
    Column("tipped_away_goals", Integer, nullable=False),
    Column("points_awarded", Integer, nullable=False),
    Column("is_tendency_correct", Boolean, nullable=False),
    Column("is_goal_difference_correct", Boolean, nullable=False),
    Column("is_exact_hit", Boolean, nullable=False),
    Column("penalty_points_awarded", Integer),
    Column("penalty_tip_correct", Boolean),
)

fact_ranking_snapshot = Table(
    "fact_ranking_snapshot",
    metadata,
    Column("snapshot_id", String, primary_key=True),  # player_id:matchday_number
    Column("player_id", String, ForeignKey("dim_player.player_id")),
    Column("matchday_number", Integer, nullable=False),
    Column("points_this_matchday", Integer, nullable=False),
    Column("is_matchday_winner", Boolean, nullable=False),
    Column("cumulative_points", Integer, nullable=False),
    Column("cumulative_matchday_wins", Integer, nullable=False),
    Column("rank_after_matchday", Integer, nullable=False),
)

fact_player_statistics = Table(
    "fact_player_statistics",
    metadata,
    Column("player_id", String, ForeignKey("dim_player.player_id"), primary_key=True),
    Column("total_tips", Integer, nullable=False),
    Column("exact_hits", Integer, nullable=False),
    Column("tendency_hits", Integer, nullable=False),
    Column("home_win_tips_correct", Integer, nullable=False),
    Column("draw_tips_correct", Integer, nullable=False),
    Column("away_win_tips_correct", Integer, nullable=False),
    Column("misses", Integer, nullable=False),
    Column("hit_rate", Float, nullable=False),
)