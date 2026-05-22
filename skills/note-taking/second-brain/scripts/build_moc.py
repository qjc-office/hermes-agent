#!/usr/bin/env python3
"""Obsidian 볼트 스캔 → MOC(Map of Content) 인덱스 생성.

cron(second-brain)이 매일 새벽 실행한다. 볼트 전체를 스캔해서:
- 폴더별 노트 목록
- 태그 인덱스 (같은 노트를 주제별로 다중 연결)
- 고아 노트 감지 (인바운드 [[링크]]가 없는 = 그래프에 연결 안 된 노트)
를 MOC.md 로 만들고, 통계 JSON 을 stdout 으로 출력한다 (AI 프롬프트에 주입됨).

볼트 경로: OBSIDIAN_VAULT_PATH 환경변수 (없으면 ~/Documents/Obsidian Vault).
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

_TAG_RE = re.compile(r"(?:^|\s)#([A-Za-z0-9가-힣_/-]+)")
_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_FM_TAGS_INLINE = re.compile(r"tags:\s*\[([^\]]*)\]")


def extract_tags(text: str) -> Set[str]:
    """frontmatter tags + 인라인 #태그 합집합."""
    tags: Set[str] = set()
    body = text
    m = _FM_RE.match(text)
    if m:
        fm = m.group(1)
        if yaml:
            try:
                data = yaml.safe_load(fm) or {}
                t = data.get("tags")
                if isinstance(t, list):
                    tags |= {str(x).strip() for x in t if str(x).strip()}
                elif isinstance(t, str):
                    tags |= {t.strip()}
            except Exception:
                pass
        inline = _FM_TAGS_INLINE.search(fm)  # yaml 없을 때 폴백
        if inline:
            tags |= {x.strip().strip("\"'") for x in inline.group(1).split(",") if x.strip()}
        body = text[m.end():]
    for tm in _TAG_RE.finditer(body):
        tags.add(tm.group(1))
    return tags


def extract_links(text: str) -> Set[str]:
    """[[위키링크]] 와 [[링크|별칭]] 에서 대상 노트명 추출."""
    return {m.group(1).strip() for m in _LINK_RE.finditer(text)}


def scan_vault(vault) -> List[Dict]:
    """볼트의 모든 .md 노트를 스캔한다. 없으면 빈 리스트."""
    vault = Path(vault)
    if not vault.exists():
        return []
    notes: List[Dict] = []
    for p in sorted(vault.rglob("*.md")):
        if p.name == "MOC.md":  # 자기 자신 제외
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = p.relative_to(vault)
        folder = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        notes.append({
            "title": p.stem,
            "path": str(p),
            "rel": str(rel),
            "folder": folder,
            "tags": sorted(extract_tags(text)),
            "links": sorted(extract_links(text)),
        })
    return notes


def find_orphans(notes: List[Dict]) -> List[Dict]:
    """다른 노트로부터 인바운드 [[링크]]를 받지 못한 노트."""
    linked: Set[str] = set()
    for n in notes:
        linked.update(n["links"])
    return [n for n in notes if n["title"] not in linked]


def render_moc(notes: List[Dict], vault) -> str:
    """폴더별 + 태그 인덱스 + 고아 노트 섹션을 가진 MOC 마크다운."""
    by_folder: Dict[str, List[Dict]] = defaultdict(list)
    for n in notes:
        by_folder[n["folder"]].append(n)
    tag_index: Dict[str, List[str]] = defaultdict(list)
    for n in notes:
        for t in n["tags"]:
            tag_index[t].append(n["title"])
    orphans = find_orphans(notes)
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# 🧠 MOC — Map of Content",
        "",
        f"> 자동 생성 ({now}). 노트 {len(notes)}개 · 태그 {len(tag_index)}개 · 고아 {len(orphans)}개.",
        "> 이 파일은 second-brain 자동화가 매일 갱신합니다. 직접 편집하지 마세요.",
        "",
        "## 폴더별",
        "",
    ]
    for folder in sorted(by_folder):
        lines.append(f"### {folder}")
        for n in sorted(by_folder[folder], key=lambda x: x["title"]):
            tag_suffix = f"  ({', '.join('#' + t for t in n['tags'])})" if n["tags"] else ""
            lines.append(f"- [[{n['title']}]]{tag_suffix}")
        lines.append("")

    if tag_index:
        lines.append("## 태그 인덱스")
        lines.append("")
        for tag in sorted(tag_index):
            titles = ", ".join(f"[[{t}]]" for t in sorted(set(tag_index[tag])))
            lines.append(f"- **#{tag}**: {titles}")
        lines.append("")

    if orphans:
        lines.append("## 🔗 고아 노트 (인바운드 링크 없음 — 연결 필요)")
        lines.append("")
        for n in sorted(orphans, key=lambda x: x["title"]):
            lines.append(f"- [[{n['title']}]] — `{n['rel']}`")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    vault_str = os.getenv("OBSIDIAN_VAULT_PATH") or str(
        Path.home() / "Documents" / "Obsidian Vault"
    )
    vault = Path(vault_str)
    notes = scan_vault(vault)
    result = {
        "vault": str(vault),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note_count": len(notes),
        "tag_count": len({t for n in notes for t in n["tags"]}),
        "orphan_count": len(find_orphans(notes)),
    }
    if not vault.exists():
        result["status"] = "no_vault"
        result["hint"] = "OBSIDIAN_VAULT_PATH 환경변수를 설정하세요."
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    moc = render_moc(notes, vault)
    try:
        (vault / "MOC.md").write_text(moc, encoding="utf-8")
        result["status"] = "ok"
        result["moc_path"] = str(vault / "MOC.md")
        result["orphans"] = [n["title"] for n in find_orphans(notes)][:20]
    except OSError as e:
        result["status"] = "write_failed"
        result["error"] = str(e)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
