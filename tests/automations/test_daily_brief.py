"""daily-brief collect — RSS/날씨 파서 테스트 (순수 함수, 네트워크 불필요)."""

import importlib.util
import json
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills" / "feeds" / "daily-brief" / "scripts" / "collect.py"
)
_spec = importlib.util.spec_from_file_location("daily_brief_collect", _PATH)
collect = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect)

RSS2 = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Feed</title>
<item><title>First headline</title><link>https://a.com/1</link></item>
<item><title>Second headline</title><link>https://a.com/2</link></item>
<item><title>Third headline</title><link>https://a.com/3</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom Feed</title>
<entry><title>Atom one</title><link href="https://b.com/1"/></entry>
<entry><title>Atom two</title><link href="https://b.com/2"/></entry>
</feed>"""

WEATHER_J1 = {
    "current_condition": [
        {
            "temp_C": "15",
            "FeelsLikeC": "14",
            "humidity": "60",
            "weatherDesc": [{"value": "Partly cloudy"}],
        }
    ]
}


def test_parse_rss_v2_extracts_headlines():
    items = collect.parse_rss(RSS2, limit=3)
    titles = [i["title"] for i in items]
    assert titles == ["First headline", "Second headline", "Third headline"]
    assert items[0]["link"] == "https://a.com/1"


def test_parse_rss_respects_limit():
    items = collect.parse_rss(RSS2, limit=2)
    assert len(items) == 2


def test_parse_rss_atom_format():
    items = collect.parse_rss(ATOM, limit=5)
    titles = [i["title"] for i in items]
    assert titles == ["Atom one", "Atom two"]
    assert items[0]["link"] == "https://b.com/1"


def test_parse_rss_malformed_returns_empty():
    assert collect.parse_rss(b"not xml at all", limit=3) == []


def test_parse_weather_extracts_summary():
    w = collect.parse_weather(WEATHER_J1)
    assert w["temp_c"] == "15"
    assert w["desc"] == "Partly cloudy"
    assert w["feels_like_c"] == "14"
    assert w["humidity"] == "60"


def test_parse_weather_empty_returns_empty_dict():
    assert collect.parse_weather({}) == {}


def test_main_emits_valid_json(capsys, monkeypatch):
    # 네트워크/gws 전부 비활성화 → graceful 빈 결과라도 유효 JSON 이어야 함
    monkeypatch.setattr(collect, "collect_weather", lambda *a, **k: {})
    monkeypatch.setattr(collect, "collect_rss", lambda *a, **k: [])
    monkeypatch.setattr(collect, "collect_calendar", lambda *a, **k: [])
    monkeypatch.setattr(collect, "collect_gmail_urgent", lambda *a, **k: [])
    collect.main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "weather" in data and "calendar" in data and "headlines" in data and "urgent_mail" in data
    assert "generated_at" in data
