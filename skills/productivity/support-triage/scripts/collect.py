#!/usr/bin/env python3
"""고객지원 트리아지 수집 — 인박스에서 지원 티켓 후보를 모아 분류 힌트를 붙인다.

cron(support-triage)이 매일 아침 9시에 실행. google-workspace(gws) 로 최근 인박스를
검색하고, 이미 처리한 메일은 state 멱등성으로 제외, 키워드 기반 분류 힌트를 부착해
JSON 으로 주입한다. 에이전트는 이를 보고 최종 분류 + Discord 회사 채널 로그.

환경변수:
  SUPPORT_TRIAGE_QUERY  Gmail 검색식 (기본: 최근 1일, 프로모션/소셜 제외)
  SUPPORT_TRIAGE_MAX    최대 메일 수 (기본 30)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skills._shared.auto_lib import state  # noqa: E402

_GAPI = PROJECT_ROOT / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py"

# 우선순위 순서 — 비즈니스 임팩트 큰 순으로 첫 매치 반환.
CATEGORIES = [
    ("refund", ["환불", "결제 취소", "반환", "refund", "취소해"]),
    ("billing", ["정산", "세금계산서", "영수증", "청구", "인보이스", "invoice", "payment", "결제"]),
    ("bug", ["오류", "에러", "안 돼", "안돼", "작동", "버그", "안 됨", "안됨", "깨졌", "error", "broken", "안 열", "먹통"]),
    ("account", ["로그인", "계정", "비밀번호", "회원가입", "login", "password", "가입"]),
    ("howto", ["어떻게", "방법", "사용법", "설정", "how to", "howto"]),
    ("feature", ["기능", "추가", "됐으면", "제안", "건의", "요청"]),
]


def classify_hint(subject: str, snippet: str = "") -> str:
    """제목+본문 키워드로 티켓 유형 1차 분류. 최종 판단은 에이전트가 한다."""
    text = f"{subject} {snippet}".lower()
    for category, keywords in CATEGORIES:
        if any(kw.lower() in text for kw in keywords):
            return category
    return "other"


def _run_gapi(args: List[str], timeout: int = 30) -> Optional[str]:
    if not _GAPI.exists():
        return None
    try:
        r = subprocess.run(
            [sys.executable, str(_GAPI), *args],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return None


def _search_inbox(query: str, limit: int) -> List[Dict[str, str]]:
    out = _run_gapi(["gmail", "search", query, "--max", str(limit)])
    if not out:
        return []
    try:
        data = json.loads(out)
        msgs = data if isinstance(data, list) else data.get("messages", data.get("results", []))
        result = []
        for m in msgs[:limit]:
            result.append({
                "id": str(m.get("id", m.get("messageId", m.get("subject", "")))),
                "from": m.get("from", m.get("sender", "")),
                "subject": m.get("subject", ""),
                "snippet": (m.get("snippet", "") or "")[:200],
            })
        return result
    except Exception:
        return []


def collect_tickets() -> List[Dict[str, str]]:
    query = os.getenv(
        "SUPPORT_TRIAGE_QUERY",
        "newer_than:1d -category:promotions -category:social",
    )
    limit = int(os.getenv("SUPPORT_TRIAGE_MAX", "30"))
    msgs = _search_inbox(query, limit)
    new = state.filter_new("support-triage", msgs, key=lambda m: m.get("id", ""))
    for m in new:
        m["hint"] = classify_hint(m.get("subject", ""), m.get("snippet", ""))
    return new


def main() -> int:
    is_monday = datetime.now().astimezone().weekday() == 0
    tickets = collect_tickets()
    counts: Dict[str, int] = {}
    for t in tickets:
        counts[t["hint"]] = counts.get(t["hint"], 0) + 1
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_monday": is_monday,
        "ticket_count": len(tickets),
        "category_hints": counts,
        "tickets": tickets,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
