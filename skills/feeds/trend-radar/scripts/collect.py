#!/usr/bin/env python3
"""트렌딩 워크플로우 레이더 수집 — Reddit + HN 에서 떠오르는 AI 워크플로우 감지.

cron(trend-radar)이 매일 아침 8시에 실행. Reddit(.json)과 HN(Algolia)을 무료로 긁어
velocity(score/age_hours)로 랭킹한 뒤 JSON 으로 주입한다. 에이전트는 상위 항목에서
콘텐츠 앵글 5개를 뽑아 한국어로 전달한다.

velocity = 점수 / 경과 시간(h) — "오래 쌓인 글"이 아니라 "빠르게 뜨는 글"을 잡는다.

환경변수:
  TREND_RADAR_SUBREDDITS  쉼표 구분 (기본: ChatGPT,automation,LocalLLaMA,artificial)
  TREND_RADAR_HN_QUERY    HN 검색어 (기본: AI agent)
  TREND_RADAR_TOP         상위 N (기본 5)
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_SUBS = ["ChatGPT", "automation", "LocalLLaMA", "artificial"]
_AGE_FLOOR_H = 0.5


# ---------------------------------------------------------------- 순수 파서

def parse_reddit(data: Dict, subreddit: str = "") -> List[Dict]:
    children = (data.get("data") or {}).get("children") or []
    out: List[Dict] = []
    for c in children:
        d = c.get("data") or {}
        if d.get("stickied"):
            continue
        permalink = d.get("permalink", "")
        out.append({
            "source": f"reddit/{subreddit}" if subreddit else "reddit",
            "title": d.get("title", ""),
            "score": int(d.get("score", 0) or 0),
            "comments": int(d.get("num_comments", 0) or 0),
            "created_utc": float(d.get("created_utc", 0) or 0),
            "url": f"https://reddit.com{permalink}" if permalink else d.get("url", ""),
        })
    return out


def parse_hn(data: Dict) -> List[Dict]:
    out: List[Dict] = []
    for h in data.get("hits", []) or []:
        if not h.get("title"):
            continue
        oid = h.get("objectID", "")
        out.append({
            "source": "hackernews",
            "title": h.get("title", ""),
            "score": int(h.get("points") or 0),
            "comments": int(h.get("num_comments") or 0),
            "created_utc": float(h.get("created_at_i") or 0),
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
        })
    return out


def compute_velocity(item: Dict, now: Optional[float] = None) -> float:
    now = now if now is not None else time.time()
    age_h = max((now - item.get("created_utc", now)) / 3600.0, _AGE_FLOOR_H)
    return item.get("score", 0) / age_h


def rank_topics(items: List[Dict], top: int = 5, now: Optional[float] = None) -> List[Dict]:
    scored = [{**it, "velocity": round(compute_velocity(it, now), 1)} for it in items]
    scored.sort(key=lambda x: x["velocity"], reverse=True)
    return scored[:top]


# ---------------------------------------------------------------- 네트워크

def _fetch_json(url: str, timeout: int = 15) -> Optional[Dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "HermesTrendRadar/1.0 (by /u/qjc)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
            return json.loads(r.read())
    except Exception:
        return None


def collect_reddit(subs: Optional[List[str]] = None, per_sub: int = 15) -> List[Dict]:
    if subs is None:
        env = os.getenv("TREND_RADAR_SUBREDDITS", "")
        subs = [s.strip() for s in env.split(",") if s.strip()] or DEFAULT_SUBS
    items: List[Dict] = []
    for sub in subs:
        data = _fetch_json(f"https://www.reddit.com/r/{urllib.parse.quote(sub)}/top.json?t=day&limit={per_sub}")
        if data:
            items.extend(parse_reddit(data, sub))
    return items


def collect_hn(query: Optional[str] = None) -> List[Dict]:
    query = query or os.getenv("TREND_RADAR_HN_QUERY", "AI agent")
    cutoff = int(time.time()) - 86400  # 최근 24시간
    url = (
        "https://hn.algolia.com/api/v1/search?"
        + urllib.parse.urlencode({
            "query": query, "tags": "story",
            "numericFilters": f"created_at_i>{cutoff}",
        })
    )
    data = _fetch_json(url)
    return parse_hn(data) if data else []


def main() -> int:
    top = int(os.getenv("TREND_RADAR_TOP", "5"))
    now = time.time()
    items = collect_reddit() + collect_hn()
    ranked = rank_topics(items, top=max(top * 2, 10), now=now)  # 여유롭게 뽑아 에이전트가 큐레이션
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources_scanned": {"reddit_subs": os.getenv("TREND_RADAR_SUBREDDITS", ",".join(DEFAULT_SUBS)),
                            "hn_query": os.getenv("TREND_RADAR_HN_QUERY", "AI agent")},
        "total_collected": len(items),
        "top": ranked,
        "want_angles": top,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
