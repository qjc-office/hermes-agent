#!/usr/bin/env python3
"""바이럴 스와이프 파일 수집 — 내 고성과 게시물에서 패턴(훅/구조/통계)을 추출.

cron(swipe-file)이 매일 새벽 2시에 실행. x-cli(X API)로 내 최근 게시물 + 참여도를 모아,
"내 평균 대비 N배" 임계값을 넘는 글만 골라 패턴을 추출한다. 이미 추출한 글은 state
멱등성으로 제외. 에이전트가 Obsidian Swipe File 에 구조화 저장한다.

임계값은 절대 수치가 아니라 **본인 평균 대비 배수** — 팔로워 규모와 무관하게
"나에게 효과적인 것의 지문"을 만든다.

전제: x-cli 설치 + X API 5종 키 (xitter 스킬 참조). 키 없으면 graceful 빈 결과.

환경변수:
  X_USERNAME             내 X 핸들 (timeline 조회용)
  SWIPE_LIKE_MULTIPLIER  임계 배수 (기본 2.0 = 평균의 2배)
  SWIPE_MAX_POSTS        조회할 최근 게시물 수 (기본 50)
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


# ---------------------------------------------------------------- 순수 함수

def compute_threshold(like_counts: List[int], multiplier: float = 2.0) -> float:
    """본인 평균 좋아요 × 배수. 데이터 없으면 0."""
    if not like_counts:
        return 0.0
    return (sum(like_counts) / len(like_counts)) * multiplier


def filter_high_performers(posts: List[Dict], threshold: float) -> List[Dict]:
    return [p for p in posts if (p.get("likes", 0) or 0) >= threshold]


def extract_pattern(post: Dict) -> Dict:
    """게시물에서 재사용 가능한 패턴 신호를 추출한다."""
    text = post.get("text", "") or ""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    hook = lines[0] if lines else ""
    return {
        "id": str(post.get("id", "")),
        "hook": hook,
        "opening_line": hook,
        "char_count": len(text),
        "line_count": len(lines),
        "likes": post.get("likes", 0) or 0,
        "retweets": post.get("retweets", 0) or 0,
        "replies": post.get("replies", 0) or 0,
        "has_question": "?" in text,
        "has_numbers": any(c.isdigit() for c in text),
        "is_thread": len(lines) > 4,
        "text": text,
    }


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


def _fetch_my_posts() -> List[Dict]:
    """내 최근 게시물 + 참여도. x-cli/키 없으면 빈 리스트."""
    username = os.getenv("X_USERNAME", "")
    if not username:
        return []
    limit = int(os.getenv("SWIPE_MAX_POSTS", "50"))
    out = _run_xcli(["user", "timeline", username, "--max", str(limit)])
    if not out:
        return []
    try:
        data = json.loads(out)
        items = data if isinstance(data, list) else data.get("data", data.get("tweets", []))
        posts = []
        for t in items:
            metrics = t.get("public_metrics", t) if isinstance(t, dict) else {}
            posts.append({
                "id": str(t.get("id", t.get("id_str", ""))),
                "text": t.get("text", t.get("full_text", "")),
                "likes": int(metrics.get("like_count", t.get("likes", 0)) or 0),
                "retweets": int(metrics.get("retweet_count", t.get("retweets", 0)) or 0),
                "replies": int(metrics.get("reply_count", t.get("replies", 0)) or 0),
            })
        return posts
    except Exception:
        return []


def collect_swipes() -> List[Dict]:
    posts = _fetch_my_posts()
    if not posts:
        return []
    multiplier = float(os.getenv("SWIPE_LIKE_MULTIPLIER", "2.0"))
    threshold = compute_threshold([p["likes"] for p in posts], multiplier)
    high = filter_high_performers(posts, threshold)
    fresh = state.filter_new("swipe-file", high, key=lambda p: p.get("id", ""))
    return [extract_pattern(p) for p in fresh]


def main() -> int:
    now = datetime.now(timezone.utc)
    swipes = collect_swipes()
    result = {
        "generated_at": now.isoformat(),
        "swipe_count": len(swipes),
        "swipes": swipes,
        "configured": bool(os.getenv("X_USERNAME") and shutil.which("x-cli")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
