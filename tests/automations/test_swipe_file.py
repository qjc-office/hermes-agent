"""swipe-file collect — 임계값/고성과 필터/패턴 추출 테스트."""

import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills" / "social-media" / "swipe-file" / "scripts" / "collect.py"
)
_spec = importlib.util.spec_from_file_location("swipe_file_collect", _PATH)
collect = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect)


def test_compute_threshold_average_times_multiplier():
    assert collect.compute_threshold([10, 20, 30], multiplier=2.0) == 40.0


def test_compute_threshold_empty_returns_zero():
    assert collect.compute_threshold([], multiplier=2.0) == 0.0


def test_filter_high_performers():
    posts = [{"likes": 50}, {"likes": 30}, {"likes": 41}]
    out = collect.filter_high_performers(posts, threshold=40.0)
    assert [p["likes"] for p in out] == [50, 41]


def test_extract_pattern_captures_hook_and_stats():
    post = {
        "id": "1",
        "text": "이 한 줄이 훅이다\n본문 둘째 줄\n숫자 3개 있음?",
        "likes": 100, "retweets": 20, "replies": 5,
    }
    pat = collect.extract_pattern(post)
    assert pat["hook"] == "이 한 줄이 훅이다"
    assert pat["line_count"] == 3
    assert pat["has_question"] is True
    assert pat["has_numbers"] is True
    assert pat["likes"] == 100


def test_extract_pattern_empty_text():
    pat = collect.extract_pattern({"id": "2", "text": "", "likes": 0})
    assert pat["hook"] == ""
    assert pat["line_count"] == 0


def test_collect_swipes_graceful_without_xcli(monkeypatch):
    # x-cli 미설치 → 빈 결과여도 예외 없이 동작
    monkeypatch.setattr(collect, "_fetch_my_posts", lambda *a, **k: [])
    assert collect.collect_swipes() == []
