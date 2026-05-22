"""자동화 통합 검증 — 멱등성, 동시성 안전성, 휴머나이저 자료, cron 가드 회귀.

conftest 의 _isolate_hermes_home(autouse) 가 HERMES_HOME 을 임시로 격리한다.
"""

import threading
from pathlib import Path

import pytest

from skills._shared.auto_lib import state

PROJECT = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------- 멱등성

def test_idempotency_real_state_file():
    items = [{"id": "A"}, {"id": "B"}]
    first = state.filter_new("idem", items, key=lambda x: x["id"])
    second = state.filter_new("idem", items, key=lambda x: x["id"])
    third = state.filter_new("idem", items + [{"id": "C"}], key=lambda x: x["id"])
    assert [x["id"] for x in first] == ["A", "B"]
    assert second == []                       # 재실행 시 중복 0
    assert [x["id"] for x in third] == ["C"]  # 신규만
    assert state.state_path("idem").exists()  # 실제 파일 영속


# ----------------------------------------------------------- 동시성

def test_concurrent_writes_no_corruption():
    """10스레드가 같은 namespace 에 동시 mark_seen → atomic write 로 파일 무손상."""
    errors = []

    def worker(n):
        try:
            for i in range(20):
                state.mark_seen("stress", [f"t{n}-{i}"])
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    data = state.load_state("stress")     # atomic 이라 항상 유효 JSON
    assert isinstance(data, dict)
    assert isinstance(data.get("seen", []), list)


# ----------------------------------------------------------- 휴머나이저 자료

def test_humanizer_covers_common_english_tells():
    tells = (PROJECT / "skills/creative/humanizer/references/ai-tells.md").read_text(
        encoding="utf-8"
    ).lower()
    for kw in ["delve", "tapestry", "robust", "seamless", "tricolon",
               "em-dash", "furthermore", "in conclusion", "it's not just"]:
        assert kw in tells, f"ai-tells.md 누락: {kw}"


def test_humanizer_covers_korean_tells():
    ko = (PROJECT / "skills/creative/humanizer/references/ko-tells.md").read_text(
        encoding="utf-8"
    )
    for kw in ["할 수 있습니다", "또한", "결론적으로", "당신은", "3단 병렬"]:
        assert kw in ko, f"ko-tells.md 누락: {kw}"


# ----------------------------------------------------------- cron 가드 회귀

def test_cron_wrapper_pattern_passes_guard(tmp_path, monkeypatch):
    """~/.hermes/scripts/auto/X.py 래퍼는 가드 통과, 프로젝트 밖 경로는 차단."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from cron.scheduler import _run_job_script

    auto = tmp_path / "scripts" / "auto"
    auto.mkdir(parents=True)
    (auto / "demo.py").write_text('print("{\\"ok\\": true}")', encoding="utf-8")

    ok, out = _run_job_script("auto/demo.py")
    assert ok is True
    assert "ok" in out

    # 프로젝트 밖 절대경로(원래 결함)는 반드시 차단되어야 함
    blocked, msg = _run_job_script(str(PROJECT / "skills/feeds/daily-brief/scripts/collect.py"))
    assert blocked is False
    assert "Blocked" in msg


def test_register_deploys_skills_via_sync():
    """register_automations.py 가 cron 등록 시 skills_sync 를 호출하는지 회귀 검증.

    근본 결함: 스킬은 ~/.hermes/skills/(SKILLS_DIR)에서 로드되는데, 프로젝트 skills/ 에서만
    만들고 sync 를 안 하면 런타임이 'Skill not found' 로 실패한다. register 가 sync 를
    호출하도록 통합했으므로, 누가 이를 제거하면 이 테스트가 잡는다.
    """
    src = (PROJECT / "scripts/register_automations.py").read_text(encoding="utf-8")
    assert "from tools.skills_sync import sync_skills" in src
    assert "sync_skills(" in src


def test_all_skill_names_resolve_when_deployed():
    """배포된 환경에서 9개 스킬이 Hermes 스킬 로더로 발견되는지.

    conftest 가 HERMES_HOME 을 격리하면 실제 배포 상태가 아니므로 skip.
    """
    import os
    if os.getenv("HERMES_HOME"):
        pytest.skip("isolated HERMES_HOME — 실제 배포 상태 아님")
    from agent.skill_commands import scan_skill_commands
    cmds = scan_skill_commands()
    for s in ["humanizer", "second-brain", "daily-brief", "trend-radar",
              "support-triage", "weekly-business", "meeting-brief",
              "swipe-file", "bookmark-inbox"]:
        assert f"/{s}" in cmds, f"스킬 미발견: {s}"


def test_registered_jobs_use_wrapper_paths():
    """등록된 auto: job 의 script 가 가드를 통과하는 auto/ 상대경로인지 (회귀 방지).

    실제 ~/.hermes 의 등록 상태를 확인 — 등록 안 됐으면 skip.
    """
    import os
    if os.getenv("HERMES_HOME"):  # 격리 환경에서는 실제 등록이 없음
        pytest.skip("isolated HERMES_HOME — 실제 등록 상태 아님")
    from cron.jobs import list_jobs
    autos = [j for j in list_jobs() if str(j.get("name", "")).startswith("auto:")]
    if not autos:
        pytest.skip("auto: job 미등록")
    for j in autos:
        script = j.get("script")
        if script:
            assert script.startswith("auto/"), f"{j['name']} script 가 래퍼 경로 아님: {script}"
