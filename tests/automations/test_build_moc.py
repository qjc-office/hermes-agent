"""second-brain build_moc — Obsidian 볼트 스캔 + MOC 인덱스 생성 테스트."""

import importlib.util
from pathlib import Path

_MOC_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills" / "note-taking" / "second-brain" / "scripts" / "build_moc.py"
)
_spec = importlib.util.spec_from_file_location("build_moc", _MOC_PATH)
build_moc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_moc)


def _make_vault(tmp_path):
    vault = tmp_path / "vault"
    (vault / "10_Areas").mkdir(parents=True)
    (vault / "20_Resources").mkdir(parents=True)
    (vault / "10_Areas" / "QJC.md").write_text(
        "---\ntags: [business, qjc]\n---\n# QJC\n관련: [[자동화]]\n", encoding="utf-8"
    )
    (vault / "20_Resources" / "자동화.md").write_text(
        "# 자동화\n#workflow #ai\n내용\n", encoding="utf-8"
    )
    (vault / "20_Resources" / "고아노트.md").write_text(
        "# 고아\n아무도 링크 안 함\n", encoding="utf-8"
    )
    return vault


def test_scan_vault_finds_all_markdown(tmp_path):
    vault = _make_vault(tmp_path)
    notes = build_moc.scan_vault(vault)
    names = sorted(n["title"] for n in notes)
    assert names == ["QJC", "고아노트", "자동화"]


def test_extract_tags_from_frontmatter_and_inline():
    fm = "---\ntags: [business, qjc]\n---\n# T\nbody"
    assert build_moc.extract_tags(fm) == {"business", "qjc"}
    inline = "# T\n#workflow 그리고 #ai 태그\n"
    assert build_moc.extract_tags(inline) == {"workflow", "ai"}


def test_extract_links_wikilinks():
    text = "본문 [[자동화]] 그리고 [[QJC 사업|별칭]] 참조"
    assert build_moc.extract_links(text) == {"자동화", "QJC 사업"}


def test_find_orphans_detects_unlinked_notes(tmp_path):
    vault = _make_vault(tmp_path)
    notes = build_moc.scan_vault(vault)
    orphans = build_moc.find_orphans(notes)
    titles = {n["title"] for n in orphans}
    # 자동화는 QJC가 링크 → 고아 아님. 고아노트/QJC는 인바운드 링크 없음.
    assert "고아노트" in titles
    assert "자동화" not in titles


def test_render_moc_includes_all_notes_grouped_by_folder(tmp_path):
    vault = _make_vault(tmp_path)
    notes = build_moc.scan_vault(vault)
    md = build_moc.render_moc(notes, vault)
    assert "QJC" in md
    assert "자동화" in md
    assert "고아노트" in md
    # 폴더 그룹 헤더
    assert "10_Areas" in md
    assert "20_Resources" in md


def test_render_moc_lists_tag_index(tmp_path):
    vault = _make_vault(tmp_path)
    notes = build_moc.scan_vault(vault)
    md = build_moc.render_moc(notes, vault)
    assert "business" in md or "#business" in md


def test_scan_vault_missing_returns_empty(tmp_path):
    assert build_moc.scan_vault(tmp_path / "nope") == []
