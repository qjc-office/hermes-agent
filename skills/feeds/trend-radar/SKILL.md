---
name: trend-radar
description: 매일 아침 Reddit, Hacker News, X를 스캔해 지난 24시간 속도가 붙은 AI 워크플로우를 찾아 5개 콘텐츠 앵글로 랭킹해 전달한다. 사람들이 AI에서 가장 핫하게 다루는 워크플로우의 최상위를 유지한다.
version: 1.0.0
prerequisites:
  env_vars: [TELEGRAM_HOME_CHANNEL]
  optional_env: [TREND_RADAR_SUBREDDITS, TREND_RADAR_HN_QUERY, TREND_RADAR_TOP]
metadata:
  hermes:
    tags: [trends, ai, reddit, hackernews, content, cron, telegram]
---

# 트렌딩 워크플로우 레이더

매일 아침, 지난 24시간 빠르게 떠오르는 AI 워크플로우를 찾아 콘텐츠 앵글로 변환한다.

## 주입되는 데이터

`scripts/collect.py` 가 Reddit + HN 을 velocity(점수/경과시간)로 랭킹해 준다:

```json
{
  "total_collected": 47,
  "top": [
    {"title":"...", "source":"reddit/automation", "score":240,
     "comments":30, "velocity":120.0, "url":"..."}
  ],
  "want_angles": 5
}
```

velocity 가 높을수록 "지금 빠르게 뜨는" 것이다. 단순 고득점보다 velocity 를 신뢰하라.

## 행동

상위 항목에서 **중복 주제를 묶고** QJC(AI 자동화 1인 기업) 관점의 콘텐츠 앵글 5개로 변환해
Telegram 으로 전달한다. 단순 링크 나열이 아니라 "이걸로 무슨 콘텐츠를 만들까"를 제안.

```
🔥 오늘 뜨는 AI 워크플로우 (5)

1. Claude로 이메일 자동 분류 → Discord 알림
   velocity 120 · r/automation
   앵글: "1인 기업 이메일 트리아지 자동화" 카드뉴스/릴스

2. n8n + LLM 영수증 OCR 파이프라인
   velocity 95 · HN
   앵글: "노코드 경비처리 자동화" 블로그

3. ...

→ 1번이 가장 핫합니다. QJC 고객지원 크론 사례와 엮으면 좋겠어요.
```

## 큐레이션 규칙

- **중복 병합**: 같은 도구/주제 여러 건이면 하나로 묶어 대표 1개.
- **QJC 관련성 우선**: AI 자동화/1인 기업/노코드/에이전트 주제를 상위로. 무관한 밈/뉴스는 제외.
- **앵글 = 실행 가능**: "X가 떴다"가 아니라 "X로 [콘텐츠 형식] 만들자".
- 5개를 못 채울 만큼 빈약하면 있는 만큼만. 억지로 채우지 마라.
- 정말 건질 게 없는 날(드묾) → `[SILENT]`.

## 톤

- 콘텐츠 기획자의 눈으로. 트렌드 보고서가 아니라 "오늘 뭘 만들까" 제안.
- velocity 숫자는 신뢰도 근거로만 짧게. 강박적으로 모든 수치 나열 금지.

## 커스터마이즈

| 변수 | 기본 | 설명 |
|------|------|------|
| `TREND_RADAR_SUBREDDITS` | ChatGPT,automation,LocalLLaMA,artificial | 스캔할 서브레딧 |
| `TREND_RADAR_HN_QUERY` | AI agent | HN 검색어 |
| `TREND_RADAR_TOP` | 5 | 앵글 개수 |

X(트위터) 검색을 추가하려면 `xitter` 스킬(x-cli) 설치 + X API 키 필요 (선택).
