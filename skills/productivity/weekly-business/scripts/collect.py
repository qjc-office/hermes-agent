#!/usr/bin/env python3
"""주간 비즈니스 리포트 수집 — 매출(WoW) + 소셜 + (옵션) Stripe.

cron(weekly-business)이 매주 월요일 아침 9시에 실행. QJC 매출 원장은 Supabase
transactions(data-policy.md)이므로 이를 1차 소스로 주간 대비(WoW) 집계하고,
소셜 팔로워/Stripe 는 환경변수가 있을 때만 보강한다. 결과 JSON 을 주입하면
에이전트가 단일 한국어 대시보드로 정리해 Telegram 전송.

환경변수 (모두 선택 — 없으면 해당 섹션 graceful skip):
  WEEKLY_BIZ_SUPABASE_URL / WEEKLY_BIZ_SUPABASE_KEY  (또는 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)
  WEEKLY_BIZ_TABLE        매출 테이블명 (기본 transactions)
  STRIPE_SECRET_KEY       Stripe 보강 (선택)
  WEEKLY_BIZ_SOCIAL_JSON  소셜 팔로워 스냅샷 JSON 경로 (선택)
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------- 순수 함수

def compute_wow(this_val: float, last_val: float) -> Dict:
    """주간 대비(Week-over-Week) 변화. 지난주가 0이면 비율 비교 불가(None)."""
    delta = round(this_val - last_val, 2)
    pct = round((delta / last_val) * 100, 1) if last_val else None
    return {"this": this_val, "last": last_val, "delta": delta, "pct": pct}


def _parse_date(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def summarize_transactions(rows: List[Dict], now: Optional[datetime] = None) -> Dict:
    """transactions 행을 이번 주 / 지난 주 매출 합계로 집계. 매출(income)만."""
    now = now or datetime.now(timezone.utc)
    this_start = now - timedelta(days=7)
    last_start = now - timedelta(days=14)
    this_sum = last_sum = 0.0
    for r in rows:
        if str(r.get("type", "income")).lower() in ("expense", "refund", "cost"):
            continue
        d = _parse_date(r.get("date") or r.get("created_at") or r.get("paid_at"))
        if d is None:
            continue
        amt = float(r.get("amount", 0) or 0)
        if d >= this_start:
            this_sum += amt
        elif d >= last_start:
            last_sum += amt
    return {"this_week": round(this_sum, 2), "last_week": round(last_sum, 2)}


# ---------------------------------------------------------------- 수집기 (env 가드)

def _supabase_creds():
    url = os.getenv("WEEKLY_BIZ_SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = os.getenv("WEEKLY_BIZ_SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    return url, key


def fetch_transactions(days: int = 14) -> List[Dict]:
    url, key = _supabase_creds()
    if not url or not key:
        return []
    table = os.getenv("WEEKLY_BIZ_TABLE", "transactions")
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    endpoint = (
        f"{url.rstrip('/')}/rest/v1/{table}?"
        + urllib.parse.urlencode({"select": "amount,type,date,created_at,paid_at",
                                  "date": f"gte.{since}"})
    )
    req = urllib.request.Request(endpoint, headers={
        "apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            data = json.loads(r.read())
            return data if isinstance(data, list) else []
    except Exception:
        return []


def fetch_social() -> Dict:
    """소셜 팔로워 스냅샷. 외부 수집기가 써둔 JSON 파일을 읽는다 (선택)."""
    path = os.getenv("WEEKLY_BIZ_SOCIAL_JSON", "")
    if not path or not Path(path).exists():
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def fetch_stripe() -> Dict:
    """Stripe 보강 (선택). 키 없으면 빈 dict."""
    if not os.getenv("STRIPE_SECRET_KEY"):
        return {}
    # Stripe 키가 설정되면 여기서 balance/charges 를 집계 (현재 QJC 기본 경로 아님).
    return {"note": "STRIPE_SECRET_KEY 감지됨 — Stripe 연동은 추가 구현 필요"}


def main() -> int:
    now = datetime.now(timezone.utc)
    rows = fetch_transactions()
    rev = summarize_transactions(rows, now=now)
    result = {
        "generated_at": now.isoformat(),
        "week_of": (now - timedelta(days=7)).date().isoformat(),
        "revenue": {
            **rev,
            "wow": compute_wow(rev["this_week"], rev["last_week"]),
            "currency": os.getenv("WEEKLY_BIZ_CURRENCY", "KRW"),
            "source": "supabase" if rows else "none",
        },
        "social": fetch_social(),
        "stripe": fetch_stripe(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
