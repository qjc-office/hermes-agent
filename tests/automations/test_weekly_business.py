"""weekly-business collect — WoW 집계 순수 함수 테스트."""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills" / "productivity" / "weekly-business" / "scripts" / "collect.py"
)
_spec = importlib.util.spec_from_file_location("weekly_business_collect", _PATH)
collect = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect)

NOW = datetime(2026, 5, 21, tzinfo=timezone.utc)


def test_compute_wow_positive():
    out = collect.compute_wow(100.0, 80.0)
    assert out["this"] == 100.0
    assert out["last"] == 80.0
    assert out["delta"] == 20.0
    assert out["pct"] == 25.0


def test_compute_wow_from_zero_last_week():
    out = collect.compute_wow(100.0, 0.0)
    assert out["pct"] is None  # 0 나눗셈 → 비교 불가 (신규)


def test_compute_wow_decline():
    out = collect.compute_wow(60.0, 100.0)
    assert out["delta"] == -40.0
    assert out["pct"] == -40.0


def test_summarize_transactions_splits_weeks():
    rows = [
        {"amount": 100, "date": (NOW - timedelta(days=2)).isoformat()},   # 이번 주
        {"amount": 50, "date": (NOW - timedelta(days=3)).isoformat()},    # 이번 주
        {"amount": 200, "date": (NOW - timedelta(days=10)).isoformat()},  # 지난 주
        {"amount": 999, "date": (NOW - timedelta(days=30)).isoformat()},  # 범위 밖
    ]
    out = collect.summarize_transactions(rows, now=NOW)
    assert out["this_week"] == 150.0
    assert out["last_week"] == 200.0


def test_summarize_skips_expenses_and_refunds():
    rows = [
        {"amount": 100, "type": "income", "date": (NOW - timedelta(days=1)).isoformat()},
        {"amount": 80, "type": "expense", "date": (NOW - timedelta(days=1)).isoformat()},
        {"amount": 30, "type": "refund", "date": (NOW - timedelta(days=1)).isoformat()},
    ]
    out = collect.summarize_transactions(rows, now=NOW)
    assert out["this_week"] == 100.0


def test_summarize_handles_bad_dates():
    rows = [{"amount": 100, "date": "not-a-date"}, {"amount": 50}]
    out = collect.summarize_transactions(rows, now=NOW)
    assert out["this_week"] == 0.0 and out["last_week"] == 0.0


def test_main_emits_valid_json(monkeypatch):
    monkeypatch.setattr(collect, "fetch_transactions", lambda *a, **k: [])
    monkeypatch.setattr(collect, "fetch_social", lambda *a, **k: {})
    monkeypatch.setattr(collect, "fetch_stripe", lambda *a, **k: {})
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        collect.main()
    data = json.loads(buf.getvalue())
    assert "revenue" in data and "generated_at" in data
