"""QJC AI PM — Discord Bot API 기반 알림 도구 (채널 + DM + @멘션).

Registers two LLM-callable tools:
- ``pm_send_notification`` -- 채널에 embed + @멘션 발송 (전체 톡방 공유)
- ``pm_send_dm``           -- 개인 DM으로 직접 메시지 발송 (프레셔/리마인드)

Bot API 사용으로 webhook 대비 기능 확장:
- @멘션으로 담당자 태그
- DM으로 개인별 프레셔
- 채널 + DM 동시 발송 가능
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

# 팀원 Discord ID 매핑 (Supabase UUID와 별개)
DISCORD_MEMBERS: Dict[str, Dict[str, str]] = {
    "sangrok": {
        "discord_id": "905300831501430914",
        "name": "정상록",
    },
    "kwango": {
        "discord_id": "1404732845183864912",
        "name": "김광오",
    },
}

# PM 알림 채널 (#큐봇-브리핑)
PM_CHANNEL_ID = "1483687019573022751"

# 허용 채널 화이트리스트 (임의 채널 발송 차단)
ALLOWED_CHANNEL_IDS = frozenset({
    PM_CHANNEL_ID,                # #큐봇-브리핑
    "1483687068994633869",        # #일반
})

_TIMEOUT = 10
_DISCORD_API = "https://discord.com/api/v10"


# ---------------------------------------------------------------------------
# 설정 + 헬퍼
# ---------------------------------------------------------------------------


def _get_bot_token() -> str:
    return os.getenv("DISCORD_BOT_TOKEN", "")


def _get_webhook_url() -> str:
    """Webhook URL (폴백용)."""
    return os.getenv("DISCORD_WEBHOOK_PM", "") or os.getenv("DISCORD_WEBHOOK_DEV", "")


def _check_discord_available() -> bool:
    """Bot 토큰 또는 webhook 중 하나라도 있으면 사용 가능."""
    return bool(_get_bot_token() or _get_webhook_url())


def _bot_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bot {_get_bot_token()}",
        "Content-Type": "application/json",
    }


def _resolve_discord_id(target: str) -> Optional[str]:
    """target(sangrok/kwango) → Discord user ID."""
    member = DISCORD_MEMBERS.get(target)
    return member["discord_id"] if member else None


def _mention(target: str) -> str:
    """target → @멘션 문자열. 알 수 없으면 이름만."""
    did = _resolve_discord_id(target)
    if did:
        return f"<@{did}>"
    return target


def _send_channel_message(
    channel_id: str,
    content: str = "",
    embed: Optional[Dict] = None,
) -> Dict:
    """Bot API로 채널에 메시지 전송."""
    token = _get_bot_token()
    if not token:
        # 폴백: webhook으로 전송
        webhook = _get_webhook_url()
        if not webhook:
            raise ValueError("DISCORD_BOT_TOKEN 또는 DISCORD_WEBHOOK_PM 필요")
        payload: Dict[str, Any] = {}
        if content:
            payload["content"] = content
        if embed:
            payload["embeds"] = [embed]
        resp = httpx.post(webhook, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        return {"sent_via": "webhook"}

    payload = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]

    resp = httpx.post(
        f"{_DISCORD_API}/channels/{channel_id}/messages",
        headers=_bot_headers(),
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _send_dm(user_id: str, content: str = "", embed: Optional[Dict] = None) -> Dict:
    """Bot API로 개인 DM 전송."""
    token = _get_bot_token()
    if not token:
        raise ValueError("DM 발송에는 DISCORD_BOT_TOKEN 필수")

    # 1. DM 채널 생성 (이미 있으면 기존 반환)
    dm_resp = httpx.post(
        f"{_DISCORD_API}/users/@me/channels",
        headers=_bot_headers(),
        json={"recipient_id": user_id},
        timeout=_TIMEOUT,
    )
    dm_resp.raise_for_status()
    dm_channel_id = dm_resp.json()["id"]

    # 2. DM 채널에 메시지 전송
    payload: Dict[str, Any] = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]

    msg_resp = httpx.post(
        f"{_DISCORD_API}/channels/{dm_channel_id}/messages",
        headers=_bot_headers(),
        json=payload,
        timeout=_TIMEOUT,
    )
    msg_resp.raise_for_status()
    return msg_resp.json()


# ---------------------------------------------------------------------------
# 핸들러
# ---------------------------------------------------------------------------


def _handle_pm_send_notification(args: dict, **kw) -> str:
    """채널에 embed 발송 + @멘션으로 담당자 태그."""
    try:
        title = args.get("title", "AI PM 알림")
        message = args.get("message", "")
        urgency = args.get("urgency", "low")
        target = args.get("target", "all")
        fields: List[Dict[str, Any]] = args.get("fields", [])
        also_dm = args.get("also_dm", False)

        color = URGENCY_COLORS.get(urgency, URGENCY_COLORS["low"])

        embed: Dict[str, Any] = {
            "title": title,
            "description": message,
            "color": color,
        }

        if fields:
            embed["fields"] = [
                {"name": f.get("name", ""), "value": f.get("value", ""), "inline": f.get("inline", True)}
                for f in fields[:10]
            ]

        # @멘션 구성
        mention_text = ""
        if target == "all":
            mentions = [_mention(m) for m in DISCORD_MEMBERS]
            mention_text = " ".join(mentions)
        elif target in DISCORD_MEMBERS:
            mention_text = _mention(target)

        # 채널에 embed + @멘션 전송 (화이트리스트 검증)
        channel_id = args.get("channel_id", PM_CHANNEL_ID)
        if channel_id not in ALLOWED_CHANNEL_IDS:
            return tool_error(f"허용되지 않은 채널: {channel_id}")
        _send_channel_message(channel_id, content=mention_text, embed=embed)
        results = [f"채널 발송 완료 (#{channel_id})"]

        # also_dm=True이면 DM도 동시 발송
        if also_dm and _get_bot_token():
            dm_targets = []
            if target == "all":
                dm_targets = list(DISCORD_MEMBERS.keys())
            elif target in DISCORD_MEMBERS:
                dm_targets = [target]

            for t in dm_targets:
                did = _resolve_discord_id(t)
                if did:
                    try:
                        _send_dm(did, embed=embed)
                        results.append(f"DM 발송 완료 ({DISCORD_MEMBERS[t]['name']})")
                    except Exception as dm_err:
                        logger.warning("DM 발송 실패 (%s): %s", t, dm_err)
                        results.append(f"DM 발송 실패 ({t})")

        return json.dumps({
            "success": True,
            "message": "; ".join(results),
            "urgency": urgency,
            "target": target,
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_send_notification error: %s", e)
        return tool_error("Discord 알림 발송 실패 (로그 확인)")


def _handle_pm_send_dm(args: dict, **kw) -> str:
    """개인 DM으로 직접 메시지 발송 (에스컬레이션/프레셔)."""
    try:
        target = args.get("target", "")
        message = args.get("message", "")
        urgency = args.get("urgency", "medium")

        if target not in DISCORD_MEMBERS:
            return tool_error(f"알 수 없는 대상: {target}. 가능: {', '.join(DISCORD_MEMBERS.keys())}")

        discord_id = _resolve_discord_id(target)
        if not discord_id:
            return tool_error(f"{target}의 Discord ID를 찾을 수 없습니다")

        color = URGENCY_COLORS.get(urgency, URGENCY_COLORS["medium"])

        embed: Dict[str, Any] = {
            "title": "📋 PM 메시지",
            "description": message,
            "color": color,
        }

        fields = args.get("fields", [])
        if fields:
            embed["fields"] = [
                {"name": f.get("name", ""), "value": f.get("value", ""), "inline": f.get("inline", True)}
                for f in fields[:10]
            ]

        _send_dm(discord_id, embed=embed)

        return json.dumps({
            "success": True,
            "message": f"DM 발송 완료 → {DISCORD_MEMBERS[target]['name']}",
            "target": target,
        }, ensure_ascii=False)
    except Exception as e:
        logger.error("pm_send_dm error: %s", e)
        return tool_error("DM 발송 실패 (로그 확인)")


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------

PM_SEND_NOTIFICATION_SCHEMA = {
    "name": "pm_send_notification",
    "description": (
        "QJC Discord 팀 채널에 PM 알림 embed 발송. "
        "@멘션으로 담당자 태그. also_dm=true로 DM 동시 발송 가능. "
        "urgency: low=파랑, medium=주황, high/critical=빨강."
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
                "enum": ["kwango", "sangrok", "all"],
                "description": "알림 대상. 해당 사용자를 @멘션.",
            },
            "also_dm": {
                "type": "boolean",
                "description": "true면 채널 알림과 동시에 DM도 발송. 에스컬레이션/긴급 시 사용.",
            },
            "fields": {
                "type": "array",
                "description": "추가 필드 목록.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["name", "value"],
                },
            },
        },
        "required": ["title", "message"],
    },
}

PM_SEND_DM_SCHEMA = {
    "name": "pm_send_dm",
    "description": (
        "팀원 개인에게 Discord DM 직접 발송. "
        "에스컬레이션, 프레셔, 개인 리마인드에 사용. "
        "채널에는 게시되지 않음."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["kwango", "sangrok"],
                "description": "DM 대상.",
            },
            "message": {
                "type": "string",
                "description": "DM 본문 (친근하고 구체적으로).",
            },
            "urgency": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "긴급도 (embed 색상 결정). 기본 medium.",
            },
            "fields": {
                "type": "array",
                "description": "추가 정보 필드.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "required": ["name", "value"],
                },
            },
        },
        "required": ["target", "message"],
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
    requires_env=["DISCORD_BOT_TOKEN"],
    emoji="📢",
)

registry.register(
    name="pm_send_dm",
    toolset="pm",
    schema=PM_SEND_DM_SCHEMA,
    handler=_handle_pm_send_dm,
    check_fn=lambda: bool(_get_bot_token()),
    requires_env=["DISCORD_BOT_TOKEN"],
    emoji="💬",
)
