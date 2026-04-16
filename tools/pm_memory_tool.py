"""QJC AI PM — 판단 기록/조회 도구 (os_pm_agent_decisions).

Registers two LLM-callable tools:
- ``pm_save_decision``        -- PM 판단 기록 INSERT
- ``pm_get_recent_decisions`` -- 최근 N개 판단 조회 (컨텍스트 체이닝)
"""

import json
import logging
from typing import Dict, Optional

from tools.pm_supabase_tool import (
    _check_pm_available,
    _safe_error_msg,
    _supabase_get,
    _supabase_post,
)

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 5000

VALID_RUN_TYPES = frozenset({
    "progress_check", "morning_briefing",
    "daily_report", "weekly_report",
})


# ---------------------------------------------------------------------------
# 핸들러
# ---------------------------------------------------------------------------


def _handle_pm_save_decision(args: dict, **kw) -> str:
    """PM 판단을 os_pm_agent_decisions에 기록."""
    try:
        run_type = args.get("run_type", "progress_check")
        reasoning = args.get("reasoning", "")
        actions = args.get("actions", [])
        context_summary = args.get("context_summary", "")

        if not reasoning:
            return tool_error("reasoning은 필수입니다.")

        data = {
            "run_type": run_type,
            "reasoning": reasoning,
            "actions": actions if isinstance(actions, list) else [],
            "actions_executed": len(actions) if isinstance(actions, list) else 0,
            "context_summary": context_summary[:_MAX_CONTEXT_CHARS] if context_summary else None,
            "model_used": args.get("model_used"),
            "tokens_used": args.get("tokens_used"),
        }

        result = _supabase_post("os_pm_agent_decisions", data)

        return json.dumps({
            "success": True,
            "message": f"PM 판단 기록 완료 (run_type={run_type}, actions={len(actions)}건)",
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_save_decision error: %s", e)
        return tool_error(_safe_error_msg("판단 기록 실패", e))


def _handle_pm_get_recent_decisions(args: dict, **kw) -> str:
    """최근 N개 PM 판단 조회."""
    try:
        limit = min(int(args.get("limit", 5)), 20)

        params: Dict[str, str] = {
            "select": "id,run_type,reasoning,actions,actions_executed,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        }

        run_type = args.get("run_type")
        if run_type:
            if run_type not in VALID_RUN_TYPES:
                return tool_error(f"잘못된 run_type: {run_type}. 허용: {', '.join(sorted(VALID_RUN_TYPES))}")
            params["run_type"] = f"eq.{run_type}"

        rows = _supabase_get("os_pm_agent_decisions", params)

        return json.dumps({
            "count": len(rows),
            "decisions": rows,
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_get_recent_decisions error: %s", e)
        return tool_error(_safe_error_msg("판단 이력 조회 실패", e))


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------

PM_SAVE_DECISION_SCHEMA = {
    "name": "pm_save_decision",
    "description": (
        "PM 판단/행동을 기록. 매 실행 후 호출하여 "
        "판단 이력을 누적 (컨텍스트 체이닝)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "run_type": {
                "type": "string",
                "enum": [
                    "progress_check", "morning_briefing",
                    "daily_report", "weekly_report",
                ],
                "description": "실행 유형.",
            },
            "reasoning": {
                "type": "string",
                "description": "분석 + 판단 근거 (2-3문장).",
            },
            "actions": {
                "type": "array",
                "description": "실행한 액션 목록 (type, target, message 등).",
                "items": {"type": "object"},
            },
            "context_summary": {
                "type": "string",
                "description": "컨텍스트 요약 (최대 5000자).",
            },
            "model_used": {
                "type": "string",
                "description": "사용 모델 (선택).",
            },
            "tokens_used": {
                "type": "integer",
                "description": "토큰 사용량 (선택).",
            },
        },
        "required": ["run_type", "reasoning"],
    },
}

PM_GET_RECENT_DECISIONS_SCHEMA = {
    "name": "pm_get_recent_decisions",
    "description": (
        "최근 PM 판단 이력 조회. 반복 알림 방지 + "
        "판단 일관성을 위한 컨텍스트 체이닝."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "조회 개수 (기본 5, 최대 20).",
            },
            "run_type": {
                "type": "string",
                "description": "실행 유형 필터 (선택).",
            },
        },
    },
}


# ---------------------------------------------------------------------------
# 레지스트리 등록
# ---------------------------------------------------------------------------

from tools.registry import registry, tool_error  # noqa: E402

_PM_ENV = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]

registry.register(
    name="pm_save_decision",
    toolset="pm",
    schema=PM_SAVE_DECISION_SCHEMA,
    handler=_handle_pm_save_decision,
    check_fn=_check_pm_available,
    requires_env=_PM_ENV,
    emoji="🧠",
)

registry.register(
    name="pm_get_recent_decisions",
    toolset="pm",
    schema=PM_GET_RECENT_DECISIONS_SCHEMA,
    handler=_handle_pm_get_recent_decisions,
    check_fn=_check_pm_available,
    requires_env=_PM_ENV,
    emoji="🧠",
)
