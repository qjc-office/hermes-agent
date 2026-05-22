"""auto_lib.state — 멱등성 상태 저장소 테스트.

cron은 매 실행마다 새 세션에서 깨어나므로, "이미 처리한 항목을 다시 처리하지 않기"를
보장할 영속 상태가 필요하다. conftest의 _isolate_hermes_home 픽스처가 HERMES_HOME을
임시 디렉토리로 격리하므로 실제 ~/.hermes 를 건드리지 않는다.
"""

import json
import os
import stat

import pytest

from skills._shared.auto_lib import state


def test_load_state_returns_empty_for_unknown_namespace():
    assert state.load_state("nope-never-seen") == {}


def test_save_then_load_roundtrip():
    state.save_state("ns1", {"a": 1, "b": ["x", "y"]})
    assert state.load_state("ns1") == {"a": 1, "b": ["x", "y"]}


def test_state_file_lives_under_hermes_home(tmp_path):
    # HERMES_HOME is the isolated fake home from conftest
    state.save_state("ns2", {"k": "v"})
    p = state.state_path("ns2")
    hermes_home = os.environ["HERMES_HOME"]
    assert str(p).startswith(hermes_home)
    assert p.exists()


def test_state_file_is_owner_only_permission():
    state.save_state("ns-perm", {"k": "v"})
    p = state.state_path("ns-perm")
    mode = stat.S_IMODE(p.stat().st_mode)
    # 0o600 — 시크릿/개인정보가 담길 수 있으므로 소유자만 읽기/쓰기
    assert mode == 0o600


def test_filter_new_first_run_returns_all_then_empty():
    items = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    first = state.filter_new("feed", items, key=lambda x: x["id"])
    assert [i["id"] for i in first] == ["1", "2", "3"]
    # 두 번째 실행 — 같은 항목은 이미 본 것이므로 빈 리스트 (멱등성)
    second = state.filter_new("feed", items, key=lambda x: x["id"])
    assert second == []


def test_filter_new_detects_only_new_items():
    state.filter_new("feed2", [{"id": "a"}, {"id": "b"}], key=lambda x: x["id"])
    out = state.filter_new(
        "feed2",
        [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}],
        key=lambda x: x["id"],
    )
    assert [i["id"] for i in out] == ["c", "d"]


def test_mark_seen_and_is_seen():
    assert state.is_seen("bm", "tweet-99") is False
    state.mark_seen("bm", ["tweet-99"])
    assert state.is_seen("bm", "tweet-99") is True


def test_filter_new_dry_run_does_not_persist():
    items = [{"id": "x"}]
    out = state.filter_new("dry", items, key=lambda x: x["id"], commit=False)
    assert [i["id"] for i in out] == ["x"]
    # commit=False 이므로 다음 실행에서도 여전히 신규로 잡혀야 함
    again = state.filter_new("dry", items, key=lambda x: x["id"], commit=False)
    assert [i["id"] for i in again] == ["x"]


def test_seen_ids_are_pruned_to_max_keep():
    ids = [f"id-{n}" for n in range(50)]
    state.mark_seen("prune", ids, max_keep=10)
    data = state.load_state("prune")
    # 최근 10개만 유지 — 무한 증가 방지
    assert len(data["seen"]) == 10
    assert "id-49" in data["seen"]
    assert "id-0" not in data["seen"]


def test_save_state_is_atomic_no_partial_file(monkeypatch):
    # 직렬화 불가 객체로 저장 시도 → 예외, 그러나 기존 파일은 보존
    state.save_state("atomic", {"ok": True})

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        state.save_state("atomic", {"bad": Unserializable()})
    # 기존 데이터가 손상되지 않아야 함
    assert state.load_state("atomic") == {"ok": True}
