#!/usr/bin/env python3
"""북마크 인박스 수집 — 새 X 북마크를 감지해 에이전트가 요약/태깅하도록 넘긴다.

cron(bookmark-inbox)이 6시간마다 실행. x-cli 로 내 북마크를 가져와 이미 파일링한 것은
state 멱등성으로 제외하고, 신규 북마크만 JSON 으로 주입한다. 에이전트가 각 북마크를
3-bullet 로 요약 + 자동 태깅 + Obsidian Bookmarks/{주제}/ 에 파일링한다.

전제: x-cli 설치 + X API 5종 키 (xitter 스킬). 키 없으면 graceful 빈 결과.

환경변수:
  BOOKMARK_MAX  조회할 북마크 수 (기본 50)
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skills._shared.auto_lib import state  # noqa: E402


# ---------------------------------------------------------------- 순수 파서

def parse_bookmarks(data) -> List[Dict]:
    """x-cli -j me bookmarks 출력 파싱 (list 또는 {data:[...]} 형태 모두 지원)."""
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("data", data.get("bookmarks", []))
    else:
        items = []
    out = []
    for t in items or []:
        author = t.get("author", "")
        if isinstance(author, dict):
            author = author.get("username", author.get("name", ""))
        out.append({
            "id": str(t.get("id", t.get("id_str", ""))),
            "text": t.get("text", t.get("full_text", "")),
            "author": author,
            "url": t.get("url", ""),
        })
    return out


# ---------------------------------------------------------------- x-cli 연동

def _run_xcli(args: List[str], timeout: int = 30) -> Optional[str]:
    if not shutil.which("x-cli"):
        return None
    try:
        r = subprocess.run(["x-cli", "-j", *args], capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    return None


def _fetch_bookmarks() -> List[Dict]:
    limit = int(os.getenv("BOOKMARK_MAX", "50"))
    out = _run_xcli(["me", "bookmarks", "--max", str(limit)])
    if not out:
        return []
    try:
        return parse_bookmarks(json.loads(out))
    except Exception:
        return []


def collect_new_bookmarks() -> List[Dict]:
    bookmarks = _fetch_bookmarks()
    return state.filter_new("bookmark-inbox", bookmarks, key=lambda b: b.get("id", ""))


def main() -> int:
    now = datetime.now(timezone.utc)
    new_bms = collect_new_bookmarks()
    result = {
        "generated_at": now.isoformat(),
        "new_count": len(new_bms),
        "bookmarks": new_bms,
        "configured": bool(shutil.which("x-cli")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
