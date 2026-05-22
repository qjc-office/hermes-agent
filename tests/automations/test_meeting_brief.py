"""meeting-brief collect — 임박 미팅 감지 + 참석자 추출 + 멱등성 테스트."""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills" / "productivity" / "meeting-brief" / "scripts" / "collect.py"
)
_spec = importlib.util.spec_from_file_location("meeting_brief_collect", _PATH)
collect = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect)

NOW = datetime(2026, 5, 21, 9, 0, tzinfo=timezone.utc)


def _evt(mins_from_now, eid, summary="미팅", attendees=None):
    start = (NOW + timedelta(minutes=mins_from_now)).isoformat()
    return {
        "id": eid,
        "summary": summary,
        "start": {"dateTime": start},
        "attendees": attendees or [],
    }


def test_find_imminent_only_within_window():
    events = [
        _evt(30, "soon"),     # 30분 후 → 포함
        _evt(90, "later"),    # 90분 후 → 제외 (window 60)
        _evt(-10, "past"),    # 지남 → 제외
    ]
    out = collect.find_imminent(events, now=NOW, window_min=60)
    ids = [e["id"] for e in out]
    assert ids == ["soon"]


def test_find_imminent_custom_window():
    events = [_evt(90, "x")]
    out = collect.find_imminent(events, now=NOW, window_min=120)
    assert [e["id"] for e in out] == ["x"]


def test_extract_attendees_excludes_self():
    evt = _evt(30, "m", attendees=[
        {"email": "me@qjc.com", "self": True},
        {"email": "client@acme.com"},
        {"email": "partner@beta.com", "self": False},
    ])
    assert collect.extract_attendees(evt) == ["client@acme.com", "partner@beta.com"]


def test_extract_attendees_empty():
    assert collect.extract_attendees(_evt(30, "m")) == []


def test_collect_briefs_idempotent(monkeypatch):
    events = [_evt(30, "meet-1", attendees=[{"email": "c@x.com"}])]
    monkeypatch.setattr(collect, "_list_calendar", lambda *a, **k: events)
    monkeypatch.setattr(collect, "_search_thread", lambda *a, **k: [])
    first = collect.collect_briefs(now=NOW)
    assert len(first) == 1
    # 같은 미팅은 두 번째 폴링에서 제외 (중복 알림 방지)
    second = collect.collect_briefs(now=NOW)
    assert second == []


def test_main_emits_valid_json(monkeypatch):
    monkeypatch.setattr(collect, "_list_calendar", lambda *a, **k: [])
    monkeypatch.setattr(collect, "_search_thread", lambda *a, **k: [])
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        collect.main()
    data = json.loads(buf.getvalue())
    assert "meetings" in data and "generated_at" in data
