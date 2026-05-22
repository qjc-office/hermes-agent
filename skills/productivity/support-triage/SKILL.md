---
name: support-triage
description: 매일 아침 인박스를 스캔해 고객 지원 티켓을 찾아 이슈 유형별로 분류하고 회사 Discord에 로그한다. 월요일에는 지난주 top5 반복 이슈를 보고해 제품에서 실제 고칠 것을 드러낸다.
version: 1.0.0
prerequisites:
  env_vars: [DISCORD_HOME_CHANNEL]
  optional_env: [SUPPORT_TRIAGE_QUERY, SUPPORT_TRIAGE_MAX]
metadata:
  hermes:
    tags: [support, cs, triage, discord, cron]
---

# 고객지원 트리아지

매일 아침 인박스에서 지원 문의를 골라 분류하고 Discord 회사 채널에 로그한다.
주간 패턴을 누적해 "무엇을 제품에서 고쳐야 하는지"를 드러낸다.

## 주입되는 데이터

`scripts/collect.py` 가 신규 티켓 후보(이미 처리한 메일 제외)를 분류 힌트와 함께 준다:

```json
{
  "is_monday": false,
  "ticket_count": 3,
  "category_hints": {"refund": 1, "bug": 2},
  "tickets": [
    {"id":"...", "from":"...", "subject":"...", "snippet":"...", "hint":"bug"}
  ]
}
```

`hint` 는 키워드 기반 1차 분류일 뿐이다. **너가 본문을 읽고 최종 분류를 판단하라.**
유형: refund(환불) / billing(결제·정산) / bug(오류) / account(계정) / howto(사용법) / feature(기능요청) / other.

## 행동

### 1. 분류 + Discord 로그

신규 티켓을 유형별로 묶어 Discord 회사 채널에 로그한다. qjc-pm 의 `pm_send_notification`
패턴을 재사용 (plain text, embed 금지, @멘션은 긴급 건만).

```
오늘 지원 문의 3건
🔴 환불 1 — 김OO "결제 취소 요청" (어제 결제, 단순 변심)
🐛 버그 2 — 박OO "로그인 후 흰 화면" / 이OO "다운로드 안 됨"
→ 버그 2건 광오님 확인 부탁
```

긴급(서비스 장애·다수 동일 버그·환불 분쟁)은 `also_dm=true` 로 담당자 DM 병행.

### 2. 주간 누적 (state)

매 실행 후 유형별 카운트를 주간 상태에 누적한다:
```
state 키 "support-triage-weekly" 에 {refund: N, bug: N, ...} 누적
```
auto_lib.state.save_state("support-triage-weekly", counts) 로 갱신.

### 3. 월요일 주간 리포트 (is_monday=true)

지난주 누적 top5 반복 이슈를 보고하고 카운트를 리셋한다:
```
📊 지난주 지원 top5
1. 로그인 흰 화면 (7건) ← 제품 수정 1순위
2. 다운로드 실패 (4건)
3. 환불 문의 (3건)
...
→ 1번은 반복되니 근본 수정 검토 필요
```

## 톤 (qjc-pm 차용)

- 행동 필요한 것 위주. 단순 문의는 카운트만, 긴급은 구체적으로.
- 신규 티켓이 0건이면 (월요일 아니면) `[SILENT]`.
- "제품에서 고칠 것" 관점 유지 — 단순 응대 목록이 아니라 패턴을 드러내라.

## 경계

- 이 자동화는 **분류·로그·패턴 감지**만. 실제 고객 답변은 `cs-responder` 영역.
- 답변 초안이 필요하면 Discord 로그에서 사람이 cs-responder 로 이어받는다.
