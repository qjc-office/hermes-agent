---
name: daily-brief
description: 매일 아침 캘린더 일정, 긴급 이메일 3-5건, 날씨, 관심 피드 헤드라인을 한 번에 스캔 가능한 하나의 Telegram 메시지로 전달한다. 커피 전 5개 앱 여는 의식을 대체한다.
version: 1.0.0
prerequisites:
  env_vars: [TELEGRAM_HOME_CHANNEL]
  optional_env: [DAILY_BRIEF_CITY, DAILY_BRIEF_FEEDS, DAILY_BRIEF_HEADLINES, DAILY_BRIEF_MAIL_QUERY]
metadata:
  hermes:
    tags: [daily-brief, calendar, email, weather, feeds, cron, telegram]
---

# 데일리 브리프

매일 아침 7시, 하루를 한눈에 스캔할 수 있는 하나의 메시지를 만든다.
수집 스크립트가 4개 소스를 모아 JSON 으로 주입한다 — 너는 그것을 사람이 읽기 좋은
한국어 메시지로 정리만 하면 된다.

## 주입되는 데이터

`scripts/collect.py` 가 자동 실행되어 다음 JSON 을 프롬프트에 넣어준다:

```json
{
  "date_local": "2026-05-21 (Thu)",
  "weather": {"temp_c":"15","feels_like_c":"14","humidity":"60","desc":"Partly cloudy"},
  "calendar": [{"summary":"코베아 미팅","start":"2026-05-21T14:00:00+09:00"}],
  "urgent_mail": [{"from":"...","subject":"...","snippet":"..."}],
  "headlines": [{"title":"...","link":"...","feed":"..."}]
}
```

빈 배열/빈 객체는 "해당 소스 없음 또는 미인증"을 뜻한다 (날씨/헤드라인은 키 없이 작동,
캘린더/메일은 google-workspace 인증 시 작동).

## 출력 형식 (Telegram, plain text)

ANSI·마크다운 볼드 금지. 이모지는 섹션 앵커로 최소만. 한 번에 스캔되도록 짧게.

```
☀️ 5/21 (목) · 서울 15°C (체감 14°), 흐림

📅 오늘 일정
- 14:00 코베아 미팅
- 16:00 소영님 통화

📬 챙길 메일 (3)
- 노하련 대표 / 견적 회신 요청
- 김광오 / 세이프코리아 배포 일정
- 패스트캠퍼스 / 정산 안내

📰 헤드라인
- Anthropic, Claude Opus 4.7 1M 컨텍스트 출시
- OpenAI gpt-image-2 텍스트 정확도 99%
- (출처 링크는 생략 또는 끝에 모아서)
```

## 톤 규칙 (qjc-pm 차용 — "대시보드가 아니라 사람이다")

- 행동이 필요한 것 위주. 일정 10개면 다 나열하지 말고 핵심만.
- 긴급 메일은 발신자 + 한 줄 요지. 전체 snippet 붙이지 마라.
- 헤드라인은 제목만. 본문 요약 금지 (브리프지 뉴스레터가 아니다).
- 숫자 자랑("총 12개 일정") 금지. 그냥 보여줘라.

## 빈 날 처리

- 일정·메일·헤드라인이 **전부** 비었으면 (주말/공휴일) → 날씨 + 한 줄 인사만.
  예: "☀️ 5/24 (일) · 서울 18°C 맑음. 오늘은 일정도 급한 메일도 없어요. 좋은 하루 되세요."
- 모든 소스가 비어 의미 있는 브리프가 불가능하면 `[SILENT]` 보다는 짧은 인사를 선호
  (아침 브리프는 매일 와야 리듬이 생긴다).

## 커스터마이즈 (환경변수)

| 변수 | 기본 | 설명 |
|------|------|------|
| `DAILY_BRIEF_CITY` | Seoul | 날씨 도시 |
| `DAILY_BRIEF_FEEDS` | HN frontpage | RSS URL 쉼표 구분 (AI/관심 피드로 교체 권장) |
| `DAILY_BRIEF_HEADLINES` | 3 | 헤드라인 개수 |
| `DAILY_BRIEF_MAIL_QUERY` | 최근 2일 중요 | Gmail 검색식 (`is:unread` 쓰지 말 것 — email.md) |
| `TELEGRAM_HOME_CHANNEL` | (필수) | 전송 대상 chat_id |
