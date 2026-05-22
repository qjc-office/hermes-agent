---
name: bookmark-inbox
description: 내 X 북마크를 자동 모니터링한다. 새 북마크를 가져와 3개 불릿으로 요약하고 자동 태그를 붙인 후 주제별로 Obsidian 볼트에 파일링한다. 저장된 것이 디지털 클러터 대신 검색 가능한 지식으로 바뀐다.
version: 1.0.0
prerequisites:
  env_vars: [X_API_KEY, X_API_SECRET, X_BEARER_TOKEN, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET, OBSIDIAN_VAULT_PATH]
  optional_env: [BOOKMARK_MAX]
metadata:
  hermes:
    tags: [social-media, x, bookmarks, obsidian, knowledge, cron]
---

# 북마크 인박스

X 북마크를 검색 가능한 지식으로 변환한다. "나중에 봐야지" 하고 잊는 클러터를 없앤다.

## 전제 조건 (X API)

`xitter` 스킬의 `x-cli` + X API 5종 키 (`skills/social-media/xitter/SKILL.md`).
키 없으면 `configured:false` 빈 결과 — 키 채우면 작동.

## 주입되는 데이터

`scripts/collect.py` 가 이미 파일링한 것을 제외한 신규 북마크만 준다 (멱등성):

```json
{
  "configured": true,
  "new_count": 3,
  "bookmarks": [
    {"id":"...", "text":"전체 트윗 본문...", "author":"username", "url":"..."}
  ]
}
```

## 행동 — Obsidian Bookmarks 에 파일링

각 신규 북마크를:
1. **3개 불릿으로 요약** (핵심만, 원문 복붙 금지)
2. **자동 태그** (주제 추론: #ai, #automation, #marketing, #dev …)
3. **주제별 파일링** — Obsidian `Bookmarks/{주제}/` (second-brain 구조)

```markdown
# {핵심 한 줄 제목}

출처: @username — {url}

- 핵심 포인트 1
- 핵심 포인트 2
- 핵심 포인트 3

#bookmark #topic/ai-automation
```

기존 주제 폴더가 있으면 거기에, 없으면 새로 만든다. 같은 주제는 한 폴더로 모은다.

## 규칙

- 신규 북마크 0건이면 `[SILENT]` (6시간마다 도는데 매번 떠들지 마라).
- 요약은 사실 기반. 원문에 없는 내용 추가 금지.
- 태그는 기존 볼트 태그 체계와 일관되게 (second-brain MOC 가 인덱싱하므로 일관성 중요).
- 링크는 보존 (나중에 원문 확인용).

## second-brain 과의 관계

여기서 만든 노트는 `second-brain` 자동화의 매일 MOC 스캔에 자동 포함되어
태그 인덱스·고아 감지 대상이 된다. 즉 북마크가 지식 그래프에 자동 편입된다.
