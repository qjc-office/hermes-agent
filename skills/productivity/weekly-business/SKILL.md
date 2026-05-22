---
name: weekly-business
description: 매주 월요일 아침 매출, 구독, 콘텐츠 뷰, 팔로워 성장, 이탈, 환불을 끌어와 이번 주 vs 지난 주(WoW) 단일 대시보드로 Telegram에 전달한다. QJC 매출은 Supabase transactions 원장 기반.
version: 1.0.0
prerequisites:
  env_vars: [TELEGRAM_HOME_CHANNEL]
  optional_env: [WEEKLY_BIZ_SUPABASE_URL, WEEKLY_BIZ_SUPABASE_KEY, STRIPE_SECRET_KEY, WEEKLY_BIZ_SOCIAL_JSON]
metadata:
  hermes:
    tags: [business, report, revenue, supabase, wow, cron, telegram]
---

# 주간 비즈니스 리포트

매주 월요일, 지난 한 주의 비즈니스 지표를 한 화면으로 본다.

## 주입되는 데이터

`scripts/collect.py` 가 Supabase transactions 기반 WoW 매출 + 소셜/Stripe(옵션)를 준다:

```json
{
  "week_of": "2026-05-14",
  "revenue": {
    "this_week": 3200000, "last_week": 2800000,
    "wow": {"delta": 400000, "pct": 14.3}, "currency": "KRW", "source": "supabase"
  },
  "social": {"youtube": 5200, "x": 1800},
  "stripe": {}
}
```

`source: "none"` 이면 Supabase 미설정 → 매출 섹션 생략하고 가능한 것만 보고.

## 출력 형식 (Telegram, plain text)

```
📊 주간 리포트 (5/14~5/20)

💰 매출 320만원 (지난주 280만 · +14.3% ▲)
📺 유튜브 5,200 (+200)
🐦 X 1,800 (+50)

이번 주 매출이 14% 늘었어요. 다음 주 포커스: 신규 견적 3건 마무리.
```

## 톤 (qjc-pm 차용)

- 숫자는 핵심만. WoW 화살표(▲▼)로 방향 직관적으로.
- 잘한 주는 칭찬, 빠진 주는 담담하게 + 다음 액션 1개.
- 모든 지표를 나열하지 마라. 의미 있는 변화 2-3개에 집중.
- 매출 0이고 모든 지표 비었으면 (Supabase 미설정 등) → 설정 안내 1줄 후 `[SILENT]` 대신
  "이번 주 데이터가 없어요. WEEKLY_BIZ_SUPABASE_URL 설정하면 매출이 자동 집계됩니다." 1회 안내.

## 데이터 소스 (QJC 맞춤)

| 지표 | 소스 | 상태 |
|------|------|------|
| 매출/구독 | Supabase `transactions` | env 설정 시 작동 (1차) |
| 팔로워/콘텐츠 뷰 | `WEEKLY_BIZ_SOCIAL_JSON` 스냅샷 | 외부 수집기 연동 시 |
| Stripe (해외 결제) | `STRIPE_SECRET_KEY` | 선택 (QJC 기본은 Supabase) |

매출 원장이 Supabase 인 이유: data-policy.md — 정형 매출/재무는 Supabase transactions.
Stripe 를 쓰면 키만 넣어라. 소셜 팔로워는 별도 수집기가 JSON 스냅샷을 써두면 읽는다.
