"""TDD 테스트 — pm_supabase_tool 5건 fix.

이슈:
- #3 HIGH: _TASK_QUERY_LIMIT 50 → 200 (134건 운영 규모 대응)
- #4 HIGH: pm_get_tasks SELECT에 os_projects(name) 조인 추가
- #5 MED: _get_client 키 stale 위험 — stateless 또는 매 요청 key 갱신
- #6 MED: pm_get_projects SELECT에 updated_at 추가
- #7 MED: pm_get_github_activity limit 파라미터화
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# 환경변수 기본값 (테스트 격리)
# ---------------------------------------------------------------------------
def _setup_env():
    os.environ.setdefault("PM_SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("PM_SUPABASE_SERVICE_ROLE_KEY", "test-key-1")


_setup_env()


# ---------------------------------------------------------------------------
# #3 HIGH: _TASK_QUERY_LIMIT 200 이상
# ---------------------------------------------------------------------------
def test_task_query_limit_should_handle_134_or_more_tasks():
    """운영 규모 134건 미완료 태스크를 누락 없이 조회해야 한다."""
    from tools.pm_supabase_tool import _TASK_QUERY_LIMIT

    assert _TASK_QUERY_LIMIT >= 200, (
        f"_TASK_QUERY_LIMIT={_TASK_QUERY_LIMIT}는 실제 미완료 134건 대비 부족. "
        "200 이상으로 상향 필요."
    )


# ---------------------------------------------------------------------------
# #4 HIGH: pm_get_tasks SELECT에 project_name 조인 포함
# ---------------------------------------------------------------------------
def test_pm_get_tasks_select_includes_project_name():
    """pm_get_tasks가 project_name(조인) 또는 os_projects(name)를 SELECT에 포함해야 한다."""
    captured_params = {}

    def fake_get(table, params):
        captured_params.update(params)
        return []

    with patch("tools.pm_supabase_tool._supabase_get", side_effect=fake_get):
        from tools.pm_supabase_tool import _handle_pm_get_tasks
        _handle_pm_get_tasks({})

    select_clause = captured_params.get("select", "")
    assert "os_projects" in select_clause or "project_name" in select_clause, (
        f"pm_get_tasks SELECT에 project_name 조인 누락: {select_clause}"
    )


# ---------------------------------------------------------------------------
# #5 MED: _get_client가 key rotation에 대응
# ---------------------------------------------------------------------------
def test_get_client_responds_to_key_rotation():
    """환경변수 key가 변경되면 새 클라이언트(또는 헤더)가 새 key를 사용해야 한다."""
    import tools.pm_supabase_tool as pst

    # 모듈 전역 상태 리셋
    pst._http_client = None

    os.environ["PM_SUPABASE_SERVICE_ROLE_KEY"] = "key-A"
    client_a = pst._get_client()
    header_a = client_a.headers.get("apikey") or client_a.headers.get("Authorization", "")

    # key rotation
    os.environ["PM_SUPABASE_SERVICE_ROLE_KEY"] = "key-B"
    client_b = pst._get_client()
    header_b = client_b.headers.get("apikey") or client_b.headers.get("Authorization", "")

    assert "key-B" in header_b, (
        f"key rotation 후에도 stale key 사용: header_b={header_b}, expected key-B"
    )


# ---------------------------------------------------------------------------
# #6 MED: pm_get_projects SELECT에 updated_at 포함
# ---------------------------------------------------------------------------
def test_pm_get_projects_select_includes_updated_at():
    """pm_get_projects가 updated_at 또는 last_task_activity를 SELECT에 포함해야 한다."""
    captured = {}

    def fake_get(table, params):
        captured.update(params)
        return []

    with patch("tools.pm_supabase_tool._supabase_get", side_effect=fake_get):
        from tools.pm_supabase_tool import _handle_pm_get_projects
        _handle_pm_get_projects({})

    select_clause = captured.get("select", "")
    assert "updated_at" in select_clause or "last_task_activity" in select_clause, (
        f"pm_get_projects SELECT에 최신 활동 시각 누락: {select_clause}"
    )


# ---------------------------------------------------------------------------
# #7 MED: pm_get_github_activity limit 파라미터화
# ---------------------------------------------------------------------------
def test_pm_get_github_activity_limit_is_parameterized():
    """pm_get_github_activity가 limit 인자를 받아 SQL에 반영해야 한다."""
    captured = {}

    def fake_get(table, params):
        captured.update(params)
        return []

    with patch("tools.pm_supabase_tool._supabase_get", side_effect=fake_get):
        from tools.pm_supabase_tool import _handle_pm_get_github_activity
        _handle_pm_get_github_activity({"hours": 24, "limit": 100})

    assert captured.get("limit") == "100", (
        f"pm_get_github_activity limit 파라미터 무시됨: {captured.get('limit')}"
    )
