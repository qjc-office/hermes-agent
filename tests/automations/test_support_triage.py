"""support-triage collect — 티켓 분류 힌트 + 멱등성 테스트."""

import importlib.util
import json
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills" / "productivity" / "support-triage" / "scripts" / "collect.py"
)
_spec = importlib.util.spec_from_file_location("support_triage_collect", _PATH)
collect = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect)


def test_classify_refund():
    assert collect.classify_hint("환불 요청드립니다", "결제 취소해주세요") == "refund"


def test_classify_bug():
    assert collect.classify_hint("오류가 발생합니다", "버튼이 작동 안 해요") == "bug"


def test_classify_billing():
    assert collect.classify_hint("세금계산서 정산 문의", "영수증 발급") == "billing"


def test_classify_howto():
    assert collect.classify_hint("사용 방법 질문", "어떻게 설정하나요?") == "howto"


def test_classify_feature():
    assert collect.classify_hint("기능 추가 제안", "이런 기능 됐으면 좋겠어요") == "feature"


def test_classify_other_when_no_keywords():
    assert collect.classify_hint("안녕하세요", "감사합니다") == "other"


def test_refund_beats_bug_in_priority():
    # 환불 + 오류 동시 언급 → 환불이 우선 (비즈니스 임팩트 큰 순)
    assert collect.classify_hint("환불해주세요 오류 때문에", "") == "refund"


def test_filter_new_excludes_already_seen(monkeypatch):
    msgs = [
        {"id": "m1", "subject": "환불", "from": "a@x.com", "snippet": ""},
        {"id": "m2", "subject": "버그", "from": "b@x.com", "snippet": ""},
    ]
    monkeypatch.setattr(collect, "_search_inbox", lambda *a, **k: msgs)
    first = collect.collect_tickets()
    assert len(first) == 2
    # 두 번째 실행 — 같은 메일은 이미 처리됨
    second = collect.collect_tickets()
    assert second == []


def test_main_emits_valid_json(monkeypatch):
    monkeypatch.setattr(collect, "_search_inbox", lambda *a, **k: [])
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        collect.main()
    data = json.loads(buf.getvalue())
    assert "tickets" in data and "generated_at" in data and "is_monday" in data
