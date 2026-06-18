from kicktipp_analytics.extraction.mock_data_source import MockKicktippDataSource


def test_mock_data_source_returns_consistent_season_data():
    source = MockKicktippDataSource(season="wm2026")

    players = source.get_players()
    matches = source.get_matches("wm2026")
    results = source.get_results("wm2026")
    tips = source.get_tips("wm2026")

    assert len(players) == 4
    assert len(matches) == 5
    assert len(results) == 5

    match_ids = {m.id for m in matches}
    assert all(r.match_id in match_ids for r in results)
    assert all(t.match_id in match_ids for t in tips)

    knockout_matches = [m for m in matches if m.requires_penalty_tip]
    assert len(knockout_matches) == 1
    knockout_tips = [t for t in tips if t.match_id == knockout_matches[0].id]
    assert all(t.penalty_winner_tip is not None for t in knockout_tips)


def test_mock_data_source_returns_nothing_for_unknown_season():
    source = MockKicktippDataSource(season="wm2026")
    assert source.get_matches("andere-saison") == []
    assert source.get_tips("andere-saison") == []
