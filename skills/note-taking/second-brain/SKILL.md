---
name: second-brain
description: Obsidian 볼트를 단일 진실 소스(second brain)로 유지한다. 매일 볼트를 스캔해 MOC(Map of Content) 인덱스를 갱신하고, 고아 노트와 태그 정합성을 점검한다. 북마크 인박스/스와이프 파일이 여기에 파일링한다.
version: 1.0.0
prerequisites:
  env_vars: [OBSIDIAN_VAULT_PATH]
metadata:
  hermes:
    tags: [obsidian, second-brain, note-taking, moc, knowledge, cron]
---

# Obsidian 세컨드 브레인 (Karpathy-maxxing)

비즈니스/삶의 모든 것에 대한 단일 진실 소스. 다른 자동화(북마크 인박스, 스와이프 파일)가
여기로 파일링하고, 이 스킬이 매일 그래프를 정리한다.

볼트 경로: `OBSIDIAN_VAULT_PATH` 환경변수 (없으면 `~/Documents/Obsidian Vault`).
파일 접근은 `note-taking/obsidian` 스킬의 FS 패턴을 따른다 (경로에 공백 → 항상 따옴표).

## 볼트 구조 (PARA + 자동화 수신함)

```
00_Inbox/          ← 미분류 캡처 (나중에 분류)
10_Areas/          ← 지속 책임 영역 (QJC, 건강, 재무 …)
20_Resources/      ← 주제별 참고 자료
30_Archive/        ← 비활성/완료
Bookmarks/         ← bookmark-inbox 자동화가 파일링 (주제별 하위폴더)
Swipe File/        ← swipe-file 자동화가 파일링 (고성과 게시물 패턴)
MOC.md             ← 이 스킬이 자동 생성 (직접 편집 금지)
```

신규 볼트라면 이 폴더들을 먼저 만든다:
```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
mkdir -p "$VAULT"/{00_Inbox,10_Areas,20_Resources,30_Archive,Bookmarks,"Swipe File"}
```

## MOC 철학

폴더는 노트를 한 곳에만 둔다. **MOC는 같은 노트를 주제·태그·맥락별로 여러 번 연결한다.**
지식은 위치가 아니라 연결에서 나온다. `[[위키링크]]`로 노트를 엮어라.

**고아 노트 = 죽은 정보.** 인바운드 링크가 없는 노트는 저장만 됐지 그래프에 연결 안 된
것이다. 이 스킬은 매일 고아를 찾아 보고한다 — "디지털 클러터 대신 검색 가능한 지식".

## 실행 (cron: 매일 새벽 3시)

수집 스크립트가 볼트를 스캔해 `MOC.md`를 갱신하고 통계 JSON을 주입한다:

```bash
python skills/note-taking/second-brain/scripts/build_moc.py
```

출력 JSON: `{note_count, tag_count, orphan_count, orphans[], status}`.

### 에이전트 행동

주입된 통계를 보고 판단한다:
- `status: no_vault` → 사용자에게 `OBSIDIAN_VAULT_PATH` 설정 안내 (1회만).
- 고아 노트가 새로 늘었으면 → 상위 몇 개를 어디에 연결하면 좋을지 1–2개 제안.
- 변화가 없거나 고아 0개면 → **`[SILENT]`** (조용한 게 정상).

리포트가 아니라 큐레이터처럼. 매일 통계를 나열하지 마라. 행동이 필요할 때만 말한다.

## 다른 자동화와의 관계

- `bookmark-inbox` → `Bookmarks/{주제}/`에 3-bullet 요약 노트 생성.
- `swipe-file` → `Swipe File/`에 게시물 패턴 노트 생성.
- 두 자동화가 만든 노트도 이 스킬의 MOC 스캔에 포함되어 자동 인덱싱된다.
