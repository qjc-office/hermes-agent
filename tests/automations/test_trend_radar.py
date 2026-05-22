"""trend-radar collect — Reddit/HN 파서 + velocity 랭킹 테스트."""

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills" / "feeds" / "trend-radar" / "scripts" / "collect.py"
)
_spec = importlib.util.spec_from_file_location("trend_radar_collect", _PATH)
collect = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect)

NOW = 1_700_000_000.0

REDDIT = {
    "data": {
        "children": [
            {"data": {"title": "Pinned", "score": 999, "num_comments": 5,
                      "created_utc": NOW - 3600, "permalink": "/r/x/p", "stickied": True}},
            {"data": {"title": "New AI workflow", "score": 240, "num_comments": 30,
                      "created_utc": NOW - 7200, "permalink": "/r/x/1", "url": "u1"}},
        ]
    }
}

HN = {
    "hits": [
        {"title": "Show HN: agent", "points": 120, "num_comments": 10,
         "created_at_i": NOW - 3600, "objectID": "42", "url": "h1"},
        {"title": "", "points": 5, "num_comments": 0, "created_at_i": NOW, "objectID": "0"},
    ]
}


def test_parse_reddit_skips_stickied():
    items = collect.parse_reddit(REDDIT, "automation")
    titles = [i["title"] for i in items]
    assert "Pinned" not in titles
    assert "New AI workflow" in titles
    assert items[0]["source"] == "reddit/automation"
    assert items[0]["score"] == 240


def test_parse_hn_skips_titleless_and_builds_url():
    items = collect.parse_hn(HN)
    assert len(items) == 1
    assert items[0]["title"] == "Show HN: agent"
    assert items[0]["score"] == 120
    assert items[0]["url"] == "h1"


def test_compute_velocity_score_over_age():
    item = {"score": 120, "created_utc": NOW - 3600}  # 1시간 전
    v = collect.compute_velocity(item, now=NOW)
    assert abs(v - 120.0) < 0.01


def test_compute_velocity_floors_age_to_avoid_div_by_zero():
    item = {"score": 50, "created_utc": NOW}  # 방금
    v = collect.compute_velocity(item, now=NOW)
    assert v == 50 / 0.5  # age floor 0.5h


def test_rank_topics_sorts_by_velocity_and_limits():
    items = [
        {"title": "slow", "score": 100, "created_utc": NOW - 36000},   # 10h → 10/h
        {"title": "fast", "score": 200, "created_utc": NOW - 3600},    # 1h → 200/h
        {"title": "mid", "score": 90, "created_utc": NOW - 3600},      # 1h → 90/h
    ]
    ranked = collect.rank_topics(items, top=2, now=NOW)
    assert [r["title"] for r in ranked] == ["fast", "mid"]
    assert ranked[0]["velocity"] >= ranked[1]["velocity"]


def test_parse_reddit_empty():
    assert collect.parse_reddit({}, "x") == []
