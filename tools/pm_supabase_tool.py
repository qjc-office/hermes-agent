"""QJC AI PM — Supabase 프로젝트/태스크/GitHub/PRD 조회 + 워크플로우/태스크 업데이트 도구.

Registers six LLM-callable tools:
- ``pm_get_projects``       -- 활성 프로젝트 + 워크플로우 + 진행률 조회
- ``pm_get_tasks``          -- 프로젝트별 태스크 (필터: 상태/담당자/지연)
- ``pm_get_github_activity``-- 최근 N시간 커밋/PR
- ``pm_get_prds``           -- PRD 버전/상태 조회
- ``pm_advance_workflow``   -- 워크플로우 단계 전진 (UUID + 화이트리스트 검증)
- ``pm_update_task``        -- 태스크 상태 변경 (UUID + 화이트리스트 검증)

Authentication uses Supabase service_role_key via env vars.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

from tools.pm_members import (
    MEMBERS,
    MEMBER_CODE_BY_ID,
    MEMBER_NAME_BY_ID,
    PM_ENV_VARS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

VALID_WORKFLOW_STAGES = frozenset({
    "meeting", "prd", "tdl_creation",
    "notification", "tdl_progress", "review_meeting",
})

WORKFLOW_ORDER = [
    "meeting", "prd", "tdl_creation",
    "notification", "tdl_progress", "review_meeting",
]

VALID_TASK_STATUSES = frozenset({
    "pending", "active", "in_progress",
    "blocked", "done", "cancelled",
})

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_TASK_QUERY_LIMIT = 50  # 태스크 기본 조회 상한

_TIMEOUT = 15  # 초
_http_client: Optional[httpx.Client] = None

# ---------------------------------------------------------------------------
# 설정 + 헬퍼
# ---------------------------------------------------------------------------


def _get_config() -> Tuple[str, str]:
    """환경변수에서 (supabase_url, service_role_key) 반환.

    PM_SUPABASE_URL / PM_SUPABASE_SERVICE_ROLE_KEY 우선,
    없으면 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 폴백.
    주의: lru_cache 사용 금지 — secret rotation 시 stale key 방지.
    """
    return (
        (os.getenv("PM_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")).rstrip("/"),
        os.getenv("PM_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
    )


def _check_pm_available() -> bool:
    """PM 도구 사용 가능 여부 (환경변수 존재 확인)."""
    url, key = _get_config()
    return bool(url and key)


def _get_client() -> httpx.Client:
    """모듈 수준 httpx Client (연결 풀 재사용)."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _, key = _get_config()
        _http_client = httpx.Client(
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            timeout=_TIMEOUT,
        )
    return _http_client


def _safe_error_msg(operation: str, exc: Exception) -> str:
    """예외에서 민감 정보를 제거한 에러 메시지 생성."""
    if isinstance(exc, httpx.TimeoutException):
        return f"{operation}: 타임아웃 ({_TIMEOUT}초 초과)"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{operation}: HTTP {exc.response.status_code}"
    return f"{operation} (로그 확인)"


def _supabase_get(
    table: str,
    params: Optional[Dict[str, str]] = None,
) -> Any:
    """Supabase PostgREST GET 요청."""
    url, _ = _get_config()
    resp = _get_client().get(
        f"{url}/rest/v1/{table}",
        params=params or {},
    )
    resp.raise_for_status()
    return resp.json()


def _supabase_patch(
    table: str,
    row_id: str,
    data: Dict[str, Any],
) -> Any:
    """Supabase PostgREST PATCH 요청 (단일 행)."""
    url, _ = _get_config()
    resp = _get_client().patch(
        f"{url}/rest/v1/{table}",
        params={"id": f"eq.{row_id}"},
        json=data,
    )
    resp.raise_for_status()
    return resp.json()


def _supabase_post(table: str, data: Dict[str, Any]) -> Any:
    """Supabase PostgREST POST 요청 (INSERT)."""
    url, _ = _get_config()
    resp = _get_client().post(
        f"{url}/rest/v1/{table}",
        json=data,
    )
    resp.raise_for_status()
    return resp.json()


def _validate_uuid(value: str) -> bool:
    return bool(UUID_RE.match(value))


def _member_name(member_id: Optional[str]) -> str:
    if not member_id:
        return "미할당"
    return MEMBER_NAME_BY_ID.get(member_id, member_id[:8])


def _calc_delay_days(due_date_str: Optional[str]) -> Optional[int]:
    """due_date 기준 지연 일수. 양수=지연, 0=당일, 음수=여유. None=기한없음."""
    if not due_date_str:
        return None
    try:
        due = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - due).days
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 핸들러
# ---------------------------------------------------------------------------


def _handle_pm_get_projects(args: dict, **kw) -> str:
    """활성 프로젝트 + 워크플로우 + 진행률 조회."""
    try:
        rows = _supabase_get("os_project_task_summary", {
            "status": "eq.active",
            "select": (
                "id,name,workflow_stage,progress_pct,"
                "total_tasks,done_tasks,active_tasks,"
                "owner_id,owner_name,github_recent_commits,github_recent_prs"
            ),
            "order": "name.asc",
        })
        for row in rows:
            row["owner_code"] = MEMBER_CODE_BY_ID.get(row.get("owner_id"), "sangrok")
        return json.dumps({"count": len(rows), "projects": rows}, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_get_projects error: %s", e)
        return tool_error(_safe_error_msg("프로젝트 조회 실패", e))


def _handle_pm_get_tasks(args: dict, **kw) -> str:
    """프로젝트별 태스크 조회 (필터: project_id, status, assigned_to)."""
    try:
        params: Dict[str, str] = {
            "select": (
                "id,title,status,priority,owner_id,"
                "due_date,project_id,created_at"
            ),
            "order": "created_at.desc",
            "limit": str(_TASK_QUERY_LIMIT),
        }

        project_id = args.get("project_id")
        if project_id:
            if not _validate_uuid(project_id):
                return tool_error(f"잘못된 project_id: {project_id}")
            params["project_id"] = f"eq.{project_id}"

        status_filter = args.get("status")
        if status_filter:
            if status_filter not in VALID_TASK_STATUSES:
                return tool_error(f"잘못된 상태: {status_filter}. 허용: {', '.join(sorted(VALID_TASK_STATUSES))}")
            params["status"] = f"eq.{status_filter}"
        else:
            # 스키마 description과 일치: 생략 시 done/cancelled 제외
            params["status"] = "not.in.(done,cancelled)"

        assigned = args.get("assigned_to")
        if assigned:
            # 이름으로 입력 시 UUID 변환
            member = MEMBERS.get(assigned)
            if member:
                params["owner_id"] = f"eq.{member['id']}"
            elif _validate_uuid(assigned):
                params["owner_id"] = f"eq.{assigned}"

        rows = _supabase_get("os_tasks", params)

        # 지연 일수 + 담당자 이름 보강
        for row in rows:
            row["delay_days"] = _calc_delay_days(row.get("due_date"))
            row["assigned_name"] = _member_name(row.get("owner_id"))

        return json.dumps({"count": len(rows), "tasks": rows}, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_get_tasks error: %s", e)
        return tool_error(_safe_error_msg("태스크 조회 실패", e))


def _handle_pm_get_github_activity(args: dict, **kw) -> str:
    """최근 N시간 GitHub 커밋/PR 조회."""
    try:
        hours = int(args.get("hours", 24))
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        params: Dict[str, str] = {
            "select": (
                "id,event_type,repo_name,member_id,"
                "commit_message,branch,event_at"
            ),
            "event_at": f"gte.{since}",
            "order": "event_at.desc",
            "limit": "50",
        }

        member_id = args.get("member_id")
        if member_id:
            if not _validate_uuid(member_id):
                # 이름으로 입력 시 UUID 변환
                member = MEMBERS.get(member_id)
                if member:
                    params["member_id"] = f"eq.{member['id']}"
            else:
                params["member_id"] = f"eq.{member_id}"

        rows = _supabase_get("os_github_events", params)

        for row in rows:
            row["member_name"] = _member_name(row.get("member_id"))

        return json.dumps({"count": len(rows), "events": rows}, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_get_github_activity error: %s", e)
        return tool_error(_safe_error_msg("GitHub 활동 조회 실패", e))


def _handle_pm_get_prds(args: dict, **kw) -> str:
    """PRD 버전/상태 조회."""
    try:
        params: Dict[str, str] = {
            "select": "id,project_id,version,status,updated_at",
            "order": "updated_at.desc",
            "limit": "10",
        }

        project_id = args.get("project_id")
        if project_id:
            if not _validate_uuid(project_id):
                return tool_error(f"잘못된 project_id: {project_id}")
            params["project_id"] = f"eq.{project_id}"

        rows = _supabase_get("os_prds", params)
        return json.dumps({"count": len(rows), "prds": rows}, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_get_prds error: %s", e)
        return tool_error(_safe_error_msg("PRD 조회 실패", e))


def _handle_pm_advance_workflow(args: dict, **kw) -> str:
    """워크플로우 단계 전진 (검증: UUID + 화이트리스트 + 순서)."""
    try:
        project_id = args.get("project_id", "")
        new_stage = args.get("new_stage", "")

        if not _validate_uuid(project_id):
            return tool_error(f"잘못된 project_id: {project_id}")
        if new_stage not in VALID_WORKFLOW_STAGES:
            return tool_error(
                f"잘못된 워크플로우 단계: {new_stage}. "
                f"허용: {', '.join(WORKFLOW_ORDER)}"
            )

        # 현재 단계 조회 → 한 단계씩만 전진 허용
        current = _supabase_get("os_projects", {
            "id": f"eq.{project_id}",
            "select": "workflow_stage",
        })
        if not current:
            return tool_error("프로젝트를 찾을 수 없습니다")
        current_stage = current[0].get("workflow_stage")
        if current_stage in WORKFLOW_ORDER and new_stage in WORKFLOW_ORDER:
            cur_idx = WORKFLOW_ORDER.index(current_stage)
            new_idx = WORKFLOW_ORDER.index(new_stage)
            if new_idx != cur_idx + 1:
                return tool_error(
                    f"순서 위반: {current_stage} → {new_stage} "
                    f"(한 단계씩만 전진 가능)"
                )

        result = _supabase_patch("os_projects", project_id, {
            "workflow_stage": new_stage,
        })
        return json.dumps({
            "success": True,
            "project_id": project_id,
            "new_stage": new_stage,
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_advance_workflow error: %s", e)
        return tool_error(_safe_error_msg("워크플로우 전진 실패", e))


def _handle_pm_update_task(args: dict, **kw) -> str:
    """태스크 상태 변경 (검증: UUID + 화이트리스트)."""
    try:
        task_id = args.get("task_id", "")
        new_status = args.get("new_status", "")

        if not _validate_uuid(task_id):
            return tool_error(f"잘못된 task_id: {task_id}")
        if new_status not in VALID_TASK_STATUSES:
            return tool_error(
                f"잘못된 태스크 상태: {new_status}. "
                f"허용: {', '.join(sorted(VALID_TASK_STATUSES))}"
            )

        result = _supabase_patch("os_tasks", task_id, {
            "status": new_status,
        })
        return json.dumps({
            "success": True,
            "task_id": task_id,
            "new_status": new_status,
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_update_task error: %s", e)
        return tool_error(_safe_error_msg("태스크 상태 변경 실패", e))


# ---------------------------------------------------------------------------
# 스키마 (OpenAI Function Calling 형식)
# ---------------------------------------------------------------------------

PM_GET_PROJECTS_SCHEMA = {
    "name": "pm_get_projects",
    "description": (
        "QJC 활성 프로젝트 목록 조회. 워크플로우 단계, 진행률, "
        "태스크 현황, GitHub 최근 활동을 포함."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

PM_GET_TASKS_SCHEMA = {
    "name": "pm_get_tasks",
    "description": (
        "QJC 태스크 조회. 프로젝트별, 상태별, 담당자별 필터 가능. "
        "지연 일수 자동 계산."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "프로젝트 UUID (선택). 생략 시 전체.",
            },
            "status": {
                "type": "string",
                "description": (
                    "태스크 상태 필터. pending/active/in_progress/"
                    "blocked/done/cancelled. 생략 시 done/cancelled 제외."
                ),
            },
            "assigned_to": {
                "type": "string",
                "description": (
                    "담당자 필터. 이름(sangrok/kwango) 또는 UUID."
                ),
            },
        },
    },
}

PM_GET_GITHUB_ACTIVITY_SCHEMA = {
    "name": "pm_get_github_activity",
    "description": (
        "QJC 최근 GitHub 커밋/PR 조회. 기본 24시간. "
        "팀원별 필터 가능."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "hours": {
                "type": "integer",
                "description": "조회 범위 (시간). 기본 24.",
            },
            "member_id": {
                "type": "string",
                "description": (
                    "팀원 필터. 이름(sangrok/kwango) 또는 UUID."
                ),
            },
        },
    },
}

PM_GET_PRDS_SCHEMA = {
    "name": "pm_get_prds",
    "description": (
        "QJC PRD(제품 요구사항 문서) 버전/상태 조회. "
        "프로젝트별 필터 가능."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "프로젝트 UUID (선택). 생략 시 전체.",
            },
        },
    },
}

PM_ADVANCE_WORKFLOW_SCHEMA = {
    "name": "pm_advance_workflow",
    "description": (
        "QJC 프로젝트 워크플로우 단계 전진. "
        "순서: meeting → prd → tdl_creation → notification "
        "→ tdl_progress → review_meeting."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "프로젝트 UUID.",
            },
            "new_stage": {
                "type": "string",
                "enum": list(WORKFLOW_ORDER),
                "description": "전진할 워크플로우 단계.",
            },
        },
        "required": ["project_id", "new_stage"],
    },
}

PM_UPDATE_TASK_SCHEMA = {
    "name": "pm_update_task",
    "description": (
        "QJC 태스크 상태 변경. "
        "허용 상태: pending/active/in_progress/blocked/done/cancelled."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "태스크 UUID.",
            },
            "new_status": {
                "type": "string",
                "enum": sorted(VALID_TASK_STATUSES),
                "description": "변경할 상태.",
            },
        },
        "required": ["task_id", "new_status"],
    },
}


# ---------------------------------------------------------------------------
# 레지스트리 등록
# ---------------------------------------------------------------------------

from tools.registry import registry, tool_error  # noqa: E402

_PM_TOOLSET = "pm"

registry.register(
    name="pm_get_projects",
    toolset=_PM_TOOLSET,
    schema=PM_GET_PROJECTS_SCHEMA,
    handler=_handle_pm_get_projects,
    check_fn=_check_pm_available,
    requires_env=PM_ENV_VARS,
    emoji="📊",
)

registry.register(
    name="pm_get_tasks",
    toolset=_PM_TOOLSET,
    schema=PM_GET_TASKS_SCHEMA,
    handler=_handle_pm_get_tasks,
    check_fn=_check_pm_available,
    requires_env=PM_ENV_VARS,
    emoji="📋",
)

registry.register(
    name="pm_get_github_activity",
    toolset=_PM_TOOLSET,
    schema=PM_GET_GITHUB_ACTIVITY_SCHEMA,
    handler=_handle_pm_get_github_activity,
    check_fn=_check_pm_available,
    requires_env=PM_ENV_VARS,
    emoji="🔀",
)

registry.register(
    name="pm_get_prds",
    toolset=_PM_TOOLSET,
    schema=PM_GET_PRDS_SCHEMA,
    handler=_handle_pm_get_prds,
    check_fn=_check_pm_available,
    requires_env=PM_ENV_VARS,
    emoji="📝",
)

registry.register(
    name="pm_advance_workflow",
    toolset=_PM_TOOLSET,
    schema=PM_ADVANCE_WORKFLOW_SCHEMA,
    handler=_handle_pm_advance_workflow,
    check_fn=_check_pm_available,
    requires_env=PM_ENV_VARS,
    emoji="⏩",
)

registry.register(
    name="pm_update_task",
    toolset=_PM_TOOLSET,
    schema=PM_UPDATE_TASK_SCHEMA,
    handler=_handle_pm_update_task,
    check_fn=_check_pm_available,
    requires_env=PM_ENV_VARS,
    emoji="✅",
)
