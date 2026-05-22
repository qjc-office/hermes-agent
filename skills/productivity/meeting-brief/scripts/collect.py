#!/usr/bin/env python3
"""미팅 준비 브리핑 수집 — 임박한 미팅 + 참석자 컨텍스트 + 최근 메일 스레드.

cron(meeting-brief)이 30분마다 폴링한다. 다음 window(기본 60분) 내 시작하는 미팅을 찾아,
참석자별 최근 Gmail 스레드를 끌어와 JSON 으로 주입한다. 같은 미팅은 state 멱등성으로
한 번만 알린다 (폴링이 겹쳐도 중복 브리프 방지).

환경변수:
  MEETING_BRIEF_WINDOW_MIN  임박 판단 창 (기본 60분)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skills._shared.auto_lib import state  # noqa: E402

_GAPI = PROJECT_ROOT / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py"


# ---------------------------------------------------------------- 순수 함수

def _parse_dt(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _event_start(event: Dict) -> Optional[datetime]:
    s = event.get("start", {})
    raw = s.get("dateTime", s.get("date")) if isinstance(s, dict) else s
    return _parse_dt(raw)


def find_imminent(events: List[Dict], now: datetime, window_min: int = 60) -> List[Dict]:
    """지금부터 window_min 분 안에 시작하는 (아직 시작 안 한) 미팅."""
    out = []
    for e in events:
        start = _event_start(e)
        if start is None:
            continue
        mins = (start - now).total_seconds() / 60.0
        if 0 < mins <= window_min:
            out.append(e)
    return out


def extract_attendees(event: Dict) -> List[str]:
    """본인(self)을 제외한 참석자 이메일."""
    out = []
    for a in event.get("attendees", []) or []:
        if isinstance(a, dict):
            if a.get("self"):
                continue
            email = a.get("email", "")
        else:
            email = str(a)
        if email:
            out.append(email)
    return out


# ---------------------------------------------------------------- gws 연동

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


def _list_calendar(now: datetime, window_min: int) -> List[Dict]:
    end = now + timedelta(minutes=window_min + 30)
    out = _run_gapi(["calendar", "list", "--start", now.isoformat(),
                     "--end", end.isoformat(), "--max", "20"])
    if not out:
        return []
    try:
        data = json.loads(out)
        return data if isinstance(data, list) else data.get("events", data.get("items", []))
    except Exception:
        return []


def _search_thread(email: str, limit: int = 2) -> List[Dict]:
    out = _run_gapi(["gmail", "search", f"from:{email} OR to:{email}", "--max", str(limit)])
    if not out:
        return []
    try:
        data = json.loads(out)
        msgs = data if isinstance(data, list) else data.get("messages", data.get("results", []))
        return [{"subject": m.get("subject", ""), "snippet": (m.get("snippet", "") or "")[:160]}
                for m in msgs[:limit]]
    except Exception:
        return []


def collect_briefs(now: Optional[datetime] = None) -> List[Dict]:
    now = now or datetime.now(timezone.utc)
    window = int(os.getenv("MEETING_BRIEF_WINDOW_MIN", "60"))
    events = _list_calendar(now, window)
    imminent = find_imminent(events, now, window)
    fresh = state.filter_new("meeting-brief", imminent,
                             key=lambda e: e.get("id", e.get("summary", "")))
    briefs = []
    for e in fresh:
        attendees = extract_attendees(e)
        threads = {a: _search_thread(a) for a in attendees}
        briefs.append({
            "summary": e.get("summary", "(제목 없음)"),
            "start": (_event_start(e) or now).isoformat(),
            "attendees": attendees,
            "threads": threads,
            "location": e.get("location", ""),
        })
    return briefs


def main() -> int:
    now = datetime.now(timezone.utc)
    meetings = collect_briefs(now=now)
    result = {
        "generated_at": now.isoformat(),
        "meeting_count": len(meetings),
        "meetings": meetings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
