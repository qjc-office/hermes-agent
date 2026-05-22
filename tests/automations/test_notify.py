"""auto_lib.notify — Gateway-safe 메시지 포맷 + 전송 억제 마커 테스트."""

from skills._shared.auto_lib import notify


def test_silent_marker_matches_scheduler():
    # cron/scheduler.py 의 SILENT_MARKER 와 반드시 일치해야 전송 억제가 동작
    assert notify.SILENT_MARKER == "[SILENT]"
    assert notify.silent().startswith("[SILENT]")


def test_clean_strips_ansi_escape_codes():
    colored = "\x1b[31mRED\x1b[0m text"
    assert notify.clean(colored) == "RED text"


def test_clean_strips_trailing_whitespace_per_line():
    assert notify.clean("a   \nb\t\n") == "a\nb"


def test_truncate_keeps_short_text():
    assert notify.truncate("hello", 100) == "hello"


def test_truncate_long_text_adds_ellipsis_and_respects_limit():
    out = notify.truncate("x" * 50, 20)
    assert len(out) <= 20
    assert out.endswith("…")


def test_section_formats_title_and_bullets():
    out = notify.section("오늘 일정", ["10시 미팅", "14시 통화"])
    assert "오늘 일정" in out
    assert "- 10시 미팅" in out
    assert "- 14시 통화" in out


def test_section_empty_lines_returns_empty_string():
    assert notify.section("빈 섹션", []) == ""


def test_telegram_safe_under_limit():
    long = "줄\n" * 5000
    out = notify.telegram_safe(long)
    assert len(out) <= notify.TELEGRAM_MAX
