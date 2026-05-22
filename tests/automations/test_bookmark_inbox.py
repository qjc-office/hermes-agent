"""bookmark-inbox collect — 북마크 파싱 + 멱등성 테스트."""

import importlib.util
import json
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills" / "social-media" / "bookmark-inbox" / "scripts" / "collect.py"
)
_spec = importlib.util.spec_from_file_location("bookmark_inbox_collect", _PATH)
collect = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect)


def test_parse_bookmarks_list_form():
    data = [{"id": "1", "text": "first", "author": "alice"}]
    out = collect.parse_bookmarks(data)
    assert out[0]["id"] == "1"
    assert out[0]["text"] == "first"
    assert out[0]["author"] == "alice"


def test_parse_bookmarks_data_wrapper():
    data = {"data": [{"id": "9", "text": "wrapped"}]}
    out = collect.parse_bookmarks(data)
    assert out[0]["id"] == "9"


def test_parse_bookmarks_author_object():
    data = [{"id": "1", "text": "t", "author": {"username": "bob"}}]
    out = collect.parse_bookmarks(data)
    assert out[0]["author"] == "bob"


def test_parse_bookmarks_empty():
    assert collect.parse_bookmarks({}) == []
    assert collect.parse_bookmarks([]) == []


def test_collect_new_bookmarks_idempotent(monkeypatch):
    bms = [{"id": "b1", "text": "t1"}, {"id": "b2", "text": "t2"}]
    monkeypatch.setattr(collect, "_fetch_bookmarks", lambda *a, **k: bms)
    first = collect.collect_new_bookmarks()
    assert len(first) == 2
    second = collect.collect_new_bookmarks()
    assert second == []  # 이미 파일링한 북마크 재처리 안 함


def test_main_emits_valid_json(monkeypatch):
    monkeypatch.setattr(collect, "_fetch_bookmarks", lambda *a, **k: [])
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        collect.main()
    data = json.loads(buf.getvalue())
    assert "bookmarks" in data and "generated_at" in data
