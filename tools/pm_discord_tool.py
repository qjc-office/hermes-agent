"""QJC AI PM — Discord webhook embed 알림 도구.

Registers one LLM-callable tool:
- ``pm_send_notification`` -- Discord webhook으로 urgency별 색상 embed 발송
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

URGENCY_COLORS: Dict[str, int] = {
    "low": 0x3B82F6,       # 파랑
    "medium": 0xF59E0B,    # 주황
    "high": 0xEF4444,      # 빨강
    "critical": 0xEF4444,  # 빨강
}

_TIMEOUT = 10  # 초


# ---------------------------------------------------------------------------
# 설정 + 헬퍼
# ---------------------------------------------------------------------------


def _get_webhook_url() -> str:
    """Discord webhook URL (PM 전용 → dev 폴백)."""
    return (
        os.getenv("DISCORD_WEBHOOK_PM", "")
        or os.getenv("DISCORD_WEBHOOK_DEV", "")
    )


def _check_discord_available() -> bool:
    return bool(_get_webhook_url())


# ---------------------------------------------------------------------------
# 핸들러
# ---------------------------------------------------------------------------


def _handle_pm_send_notification(args: dict, **kw) -> str:
    """Discord webhook embed 발송."""
    try:
        title = args.get("title", "AI PM 알림")
        message = args.get("message", "")
        urgency = args.get("urgency", "low")
        fields: List[Dict[str, Any]] = args.get("fields", [])
        target = args.get("target", "")

        color = URGENCY_COLORS.get(urgency, URGENCY_COLORS["low"])

        embed: Dict[str, Any] = {
            "title": title,
            "description": message,
            "color": color,
        }

        if fields:
            embed["fields"] = [
                {
                    "name": f.get("name", ""),
                    "value": f.get("value", ""),
                    "inline": f.get("inline", True),
                }
                for f in fields[:10]  # 최대 10개
            ]

        if target:
            embed["footer"] = {"text": f"대상: {target}"}

        payload = {"embeds": [embed]}

        resp = httpx.post(
            _get_webhook_url(),
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

        return json.dumps({
            "success": True,
            "message": f"Discord 알림 발송 완료 (urgency={urgency})",
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_send_notification error: %s", e)
        return tool_error(f"Discord 알림 발송 실패: {e}")


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------

PM_SEND_NOTIFICATION_SCHEMA = {
    "name": "pm_send_notification",
    "description": (
        "QJC Discord 채널에 PM 알림 embed 발송. "
        "urgency에 따라 색상이 자동 결정됨 (low=파랑, medium=주황, high/critical=빨강)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "알림 제목.",
            },
            "message": {
                "type": "string",
                "description": "알림 본문 (마크다운 지원).",
            },
            "urgency": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "긴급도. 기본 low.",
            },
            "target": {
                "type": "string",
                "description": (
                    "알림 대상 (kwango/sangrok/all). "
                    "footer에 표시."
                ),
            },
            "fields": {
                "type": "array",
                "description": "추가 필드 목록 (name, value 쌍).",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "string"},
                        "inline": {"type": "boolean"},
                    },
                    "required": ["name", "value"],
                },
            },
        },
        "required": ["title", "message"],
    },
}


# ---------------------------------------------------------------------------
# 레지스트리 등록
# ---------------------------------------------------------------------------

from tools.registry import registry, tool_error  # noqa: E402

registry.register(
    name="pm_send_notification",
    toolset="pm",
    schema=PM_SEND_NOTIFICATION_SCHEMA,
    handler=_handle_pm_send_notification,
    check_fn=_check_discord_available,
    requires_env=["DISCORD_WEBHOOK_PM"],
    emoji="📢",
)
