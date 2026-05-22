#!/usr/bin/env python3
"""데일리 브리프 데이터 수집 — 캘린더 + 긴급 메일 + 날씨 + 헤드라인.

cron(daily-brief)이 매일 아침 7시에 실행하기 직전 이 스크립트를 돌려, 출력 JSON 을
에이전트 프롬프트에 주입한다. 에이전트는 이를 하나의 한국어 메시지로 정리해 Telegram 전송.

각 소스는 독립적으로 graceful: 하나가 실패해도 나머지는 수집된다.
- 날씨(wttr.in) / RSS: 키 불필요 — 즉시 작동.
- 캘린더 / Gmail: google-workspace 스킬(gws 인증) 경유 — 인증되면 작동.

환경변수:
  DAILY_BRIEF_CITY        날씨 도시 (기본 Seoul)
  DAILY_BRIEF_FEEDS       RSS 피드 URL 쉼표 구분 (기본 HN)
  DAILY_BRIEF_HEADLINES   헤드라인 개수 (기본 3)
  DAILY_BRIEF_MAIL_QUERY  Gmail 검색 쿼리 (기본: 최근 2일 중요 메일)
"""

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[4]
_GAPI = PROJECT_ROOT / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py"

DEFAULT_FEEDS = ["https://hnrss.org/frontpage"]


# ---------------------------------------------------------------- 순수 파서

def _localname(tag: str) -> str:
    return tag.split("}")[-1]


def parse_rss(data: bytes, limit: int = 3) -> List[Dict[str, str]]:
    """RSS 2.0 (<item>) 와 Atom (<entry>) 모두에서 헤드라인 추출."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    items: List[Dict[str, str]] = []
    for el in root.iter():
        if _localname(el.tag) not in ("item", "entry"):
            continue
        title: Optional[str] = None
        link: Optional[str] = None
        for child in el:
            ln = _localname(child.tag)
            if ln == "title" and title is None:
                title = (child.text or "").strip()
            elif ln == "link" and link is None:
                link = (child.text or "").strip() or child.get("href", "")
        if title:
            items.append({"title": title, "link": link or ""})
        if len(items) >= limit:
            break
    return items


def parse_weather(j1: Dict) -> Dict[str, str]:
    """wttr.in ?format=j1 에서 현재 날씨 요약."""
    cc = j1.get("current_condition") or []
    if not cc or not cc[0]:
        return {}
    c = cc[0]
    desc = ""
    wd = c.get("weatherDesc") or []
    if wd:
        desc = wd[0].get("value", "")
    return {
        "temp_c": c.get("temp_C", ""),
        "feels_like_c": c.get("FeelsLikeC", ""),
        "humidity": c.get("humidity", ""),
        "desc": desc,
    }


# ---------------------------------------------------------------- 네트워크/CLI

def _fetch(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (HermesAuto)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (고정 https 소스)
        return r.read()


def _run_gapi(args: List[str], timeout: int = 30) -> Optional[str]:
    """google-workspace 래퍼 호출. 미설치/인증실패 시 None."""
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


def collect_weather(city: Optional[str] = None) -> Dict[str, str]:
    city = city or os.getenv("DAILY_BRIEF_CITY", "Seoul")
    try:
        raw = _fetch(f"https://wttr.in/{urllib.parse.quote(city)}?format=j1")
        return parse_weather(json.loads(raw))
    except Exception:
        return {}


def collect_rss(urls: Optional[List[str]] = None, limit: int = 3) -> List[Dict[str, str]]:
    if urls is None:
        env = os.getenv("DAILY_BRIEF_FEEDS", "")
        urls = [u.strip() for u in env.split(",") if u.strip()] or DEFAULT_FEEDS
    headlines: List[Dict[str, str]] = []
    for url in urls:
        try:
            headlines.extend({**it, "feed": url} for it in parse_rss(_fetch(url), limit=limit))
        except Exception:
            continue
    return headlines[:limit]


def collect_calendar() -> List[Dict[str, str]]:
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    out = _run_gapi(["calendar", "list", "--start", start.isoformat(),
                     "--end", end.isoformat(), "--max", "20"])
    if not out:
        return []
    try:
        data = json.loads(out)
        events = data if isinstance(data, list) else data.get("events", data.get("items", []))
        result = []
        for e in events:
            s = e.get("start", {})
            when = s.get("dateTime", s.get("date", "")) if isinstance(s, dict) else str(s)
            result.append({"summary": e.get("summary", "(제목 없음)"), "start": when})
        return result
    except Exception:
        return []


def collect_gmail_urgent(limit: int = 5) -> List[Dict[str, str]]:
    # email.md 규칙: is:unread 금지(읽었지만 미답장 핵심 메일 누락 방지). 최근+중요로 대체.
    query = os.getenv(
        "DAILY_BRIEF_MAIL_QUERY",
        "newer_than:2d -category:promotions -category:social -category:updates",
    )
    out = _run_gapi(["gmail", "search", query, "--max", str(limit)])
    if not out:
        return []
    try:
        data = json.loads(out)
        msgs = data if isinstance(data, list) else data.get("messages", data.get("results", []))
        result = []
        for m in msgs[:limit]:
            result.append({
                "from": m.get("from", m.get("sender", "")),
                "subject": m.get("subject", ""),
                "snippet": (m.get("snippet", "") or "")[:120],
            })
        return result
    except Exception:
        return []


def main() -> int:
    limit = int(os.getenv("DAILY_BRIEF_HEADLINES", "3"))
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date_local": datetime.now().astimezone().strftime("%Y-%m-%d (%a)"),
        "weather": collect_weather(),
        "calendar": collect_calendar(),
        "urgent_mail": collect_gmail_urgent(),
        "headlines": collect_rss(limit=limit),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
