---
name: meeting-brief
description: 모든 Google Calendar 미팅 시작 약 30분 전, 참석자 목록을 끌어와 그들의 컨텍스트와 최근 이메일 스레드를 요약한 1페이지 브리프를 Telegram에 보낸다. 스레드를 파헤치지 않고도 모든 통화에 준비된 상태로 들어간다.
version: 1.0.0
prerequisites:
  env_vars: [TELEGRAM_HOME_CHANNEL]
  optional_env: [MEETING_BRIEF_WINDOW_MIN]
metadata:
  hermes:
    tags: [meeting, calendar, briefing, gmail, cron, telegram]
---

# 미팅 준비 브리핑

미팅 직전, 참석자와 지난 대화 맥락을 1페이지로 정리해 준다.

## 폴링 방식

cron 이 30분마다 깨어나 다음 60분 내 시작하는 미팅을 찾는다. 같은 미팅은 **한 번만**
브리핑한다 (state 멱등성). 임박한 미팅이 없으면 `[SILENT]`.

## 주입되는 데이터

`scripts/collect.py` 가 임박 미팅 + 참석자별 최근 메일 스레드를 준다:

```json
{
  "meeting_count": 1,
  "meetings": [{
    "summary": "코베아 자동화 제안 미팅",
    "start": "2026-05-21T14:00:00+09:00",
    "location": "Google Meet",
    "attendees": ["lee@kovea.com", "park@kovea.com"],
    "threads": {
      "lee@kovea.com": [{"subject":"제안서 회신","snippet":"견적 검토했습니다..."}]
    }
  }]
}
```

## 출력 형식 (Telegram, 1페이지)

```
📋 30분 후 미팅: 코베아 자동화 제안 (14:00, Google Meet)

참석자
- lee@kovea.com — 최근: "제안서 회신, 견적 검토했습니다"
- park@kovea.com — 최근 메일 없음

체크포인트
- 지난 스레드에서 견적 검토 완료 언급 → 오늘 계약 조건 논의 가능
- 준비물: 수정 견적서, ROI 시뮬레이션

좋은 미팅 되세요.
```

## 행동 규칙

- 참석자별 **마지막 대화 한 줄**만. 전체 스레드 붙이지 마라.
- 메일 스레드에서 "다음 단계/미해결 질문"을 추론해 체크포인트 1-2개 제시.
- 내부 미팅(참석자 전원 @quantumjumpclub.com)은 가볍게. 외부 미팅은 더 꼼꼼히.
- 참석자 LinkedIn/회사 컨텍스트는 메일 스레드로 대체 (LinkedIn API 미연동 — 향후 확장점).

## 경계

- 이 자동화는 **자동 사전 알림**(폴링). 사용자가 명시적으로 특정 미팅 준비를 요청하면
  `meeting-prep` 스킬(더 깊은 CRM/Notion 통합)이 담당한다. 둘은 상호보완.
