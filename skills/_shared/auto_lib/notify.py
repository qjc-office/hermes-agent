"""Gateway-safe 메시지 포맷 + 전송 억제 마커.

CLAUDE.md 불변식 #5: Gateway(Telegram/Discord) 출력에 ANSI 제어문자가 들어가면
메시지가 깨진다. 모든 자동화 알림은 이 모듈의 헬퍼를 거쳐 plain text 로 정리한다.

cron 에이전트가 보고할 내용이 없을 때는 응답을 SILENT_MARKER 로 시작하면
cron/scheduler.py 가 전송을 억제한다 (로컬 audit 로그에는 남는다).
"""

import sys
from pathlib import Path
from typing import Iterable, List

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from tools.ansi_strip import strip_ansi
except Exception:  # pragma: no cover - import 폴백
    import re as _re

    _ANSI = _re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

    def strip_ansi(text: str) -> str:
        return _ANSI.sub("", text)


# cron/scheduler.py:55 SILENT_MARKER 와 일치 (변경 시 양쪽 동기화 필요).
SILENT_MARKER = "[SILENT]"

# Telegram 단일 메시지 길이 제한 (Bot API 4096자).
TELEGRAM_MAX = 4096


def silent(reason: str = "") -> str:
    """전송 억제 응답. 변화/신규 항목이 없을 때 cron 에이전트가 반환한다."""
    return f"{SILENT_MARKER} {reason}".strip()


def clean(text: str) -> str:
    """ANSI 제거 + 각 줄 끝 공백 제거 + 양끝 트림."""
    stripped = strip_ansi(text or "")
    lines = [ln.rstrip() for ln in stripped.splitlines()]
    return "\n".join(lines).strip()


def truncate(text: str, limit: int) -> str:
    """limit 자 이내로 자르고 초과 시 말줄임표(…)를 붙인다."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def telegram_safe(text: str) -> str:
    """Telegram 전송용으로 정리 + 길이 제한."""
    return truncate(clean(text), TELEGRAM_MAX)


def section(title: str, lines: Iterable[str]) -> str:
    """제목 + 불릿 목록 섹션. 항목이 없으면 빈 문자열 (섹션 자체 생략)."""
    items: List[str] = [str(ln).strip() for ln in lines if str(ln).strip()]
    if not items:
        return ""
    body = "\n".join(f"- {it}" for it in items)
    return f"{title}\n{body}"
