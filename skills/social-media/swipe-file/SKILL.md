---
name: swipe-file
description: 밤마다 내가 X에 올린 게시물을 확인해 참여도 임계값을 넘는 것을 훅·구조·주제·오프닝·통계와 함께 구조화 스와이프 파일로 추출한다. 시간이 지나며 나에게 효과적인 것의 정확한 지문(fingerprint)을 만든다.
version: 1.0.0
prerequisites:
  env_vars: [X_USERNAME, X_API_KEY, X_API_SECRET, X_BEARER_TOKEN, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET, OBSIDIAN_VAULT_PATH]
  optional_env: [SWIPE_LIKE_MULTIPLIER, SWIPE_MAX_POSTS]
metadata:
  hermes:
    tags: [social-media, x, swipe-file, content, obsidian, cron, self-improving]
---

# 바이럴 스와이프 파일 (자기 개선형)

내 고성과 게시물에서 "왜 잘 됐는지"를 추출해 누적한다. 매주 데이터가 쌓이며
내 글쓰기 지문이 선명해진다.

## 전제 조건 (X API)

`xitter` 스킬의 `x-cli` + X API 5종 키가 필요하다 (`skills/social-media/xitter/SKILL.md`).
키가 없으면 `collect.py` 가 `configured:false` 로 빈 결과를 반환한다 — 등록은 되고,
키를 채우면 즉시 작동.

## 주입되는 데이터

`scripts/collect.py` 가 "내 평균 대비 임계값"을 넘은 신규 게시물의 패턴을 준다:

```json
{
  "configured": true,
  "swipe_count": 2,
  "swipes": [{
    "id":"...", "hook":"이 한 줄이 사람을 멈춰세운다",
    "char_count":210, "line_count":5, "is_thread":true,
    "likes":340, "retweets":52, "replies":18,
    "has_question":true, "has_numbers":true, "text":"..."
  }]
}
```

임계값 = 내 평균 좋아요 × `SWIPE_LIKE_MULTIPLIER`(기본 2배). 절대 수치가 아니라
상대값이라 팔로워 규모와 무관하게 "나에게 효과적인 것"을 잡는다.

## 행동 — Obsidian Swipe File 에 저장

각 스와이프를 분석해 Obsidian `Swipe File/` 에 노트로 누적한다 (second-brain 스킬 구조):

```markdown
# Swipe: {hook 요약}

- **훅**: 이 한 줄이 사람을 멈춰세운다
- **구조**: 5줄 스레드 / 질문형 오프닝 / 숫자 포함
- **주제**: AI 자동화 (추론)
- **오프닝 라인**: "이 한 줄이..."
- **통계**: ♥340 RT52 💬18 (내 평균의 2.4배)
- **왜 통했나(가설)**: 구체적 숫자 + 질문으로 호기심 유발

#swipe #hook/question #topic/ai-automation
원문: {url}
```

## 지문(fingerprint) 누적

매 실행 후 패턴 빈도를 state 에 누적한다 (auto_lib.state):
- 어떤 훅 유형(질문/숫자/단언)이 자주 고성과인지
- 최적 길이(단문 vs 스레드)
- 잘 되는 주제

월 1회, 누적 지문을 요약해 "내 바이럴 공식"을 갱신한다. 이게 self-improving 의 핵심.

## 규칙

- 신규 고성과 글이 없으면 `[SILENT]`.
- 사실/통계는 collect.py 데이터에 근거. "주제"는 본문에서 추론하되 과한 해석 금지.
- LinkedIn/Threads 는 공식 API 가 제한적 — 현재는 X 만. 수동 입력분은 사용자가
  Swipe File 에 직접 추가하면 지문 분석에 포함된다 (확장점).
