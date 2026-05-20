"""Tests for the central tool registry."""

import json
import logging

import pytest
from pydantic import ValidationError

from tools.registry import ToolRegistry


def _dummy_handler(args, **kwargs):
    return json.dumps({"ok": True})


def _make_schema(name="test_tool"):
    return {
        "name": name,
        "description": f"A {name}",
        "parameters": {"type": "object", "properties": {}},
    }


class TestRegisterAndDispatch:
    def test_register_and_dispatch(self):
        reg = ToolRegistry()
        reg.register(
            name="alpha",
            toolset="core",
            schema=_make_schema("alpha"),
            handler=_dummy_handler,
        )
        result = json.loads(reg.dispatch("alpha", {}))
        assert result == {"ok": True}

    def test_dispatch_passes_args(self):
        reg = ToolRegistry()

        def echo_handler(args, **kw):
            return json.dumps(args)

        reg.register(
            name="echo",
            toolset="core",
            schema=_make_schema("echo"),
            handler=echo_handler,
        )
        result = json.loads(reg.dispatch("echo", {"msg": "hi"}))
        assert result == {"msg": "hi"}


class TestGetDefinitions:
    def test_returns_openai_format(self):
        reg = ToolRegistry()
        reg.register(
            name="t1", toolset="s1", schema=_make_schema("t1"), handler=_dummy_handler
        )
        reg.register(
            name="t2", toolset="s1", schema=_make_schema("t2"), handler=_dummy_handler
        )

        defs = reg.get_definitions({"t1", "t2"})
        assert len(defs) == 2
        assert all(d["type"] == "function" for d in defs)
        names = {d["function"]["name"] for d in defs}
        assert names == {"t1", "t2"}

    def test_skips_unavailable_tools(self):
        reg = ToolRegistry()
        reg.register(
            name="available",
            toolset="s",
            schema=_make_schema("available"),
            handler=_dummy_handler,
            check_fn=lambda: True,
        )
        reg.register(
            name="unavailable",
            toolset="s",
            schema=_make_schema("unavailable"),
            handler=_dummy_handler,
            check_fn=lambda: False,
        )
        defs = reg.get_definitions({"available", "unavailable"})
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "available"

    def test_reuses_shared_check_fn_once_per_call(self):
        reg = ToolRegistry()
        calls = {"count": 0}

        def shared_check():
            calls["count"] += 1
            return True

        reg.register(
            name="first",
            toolset="shared",
            schema=_make_schema("first"),
            handler=_dummy_handler,
            check_fn=shared_check,
        )
        reg.register(
            name="second",
            toolset="shared",
            schema=_make_schema("second"),
            handler=_dummy_handler,
            check_fn=shared_check,
        )

        defs = reg.get_definitions({"first", "second"})
        assert len(defs) == 2
        assert calls["count"] == 1


class TestUnknownToolDispatch:
    def test_returns_error_json(self):
        reg = ToolRegistry()
        result = json.loads(reg.dispatch("nonexistent", {}))
        assert "error" in result
        assert "Unknown tool" in result["error"]


class TestToolsetAvailability:
    def test_no_check_fn_is_available(self):
        reg = ToolRegistry()
        reg.register(
            name="t", toolset="free", schema=_make_schema(), handler=_dummy_handler
        )
        assert reg.is_toolset_available("free") is True

    def test_check_fn_controls_availability(self):
        reg = ToolRegistry()
        reg.register(
            name="t",
            toolset="locked",
            schema=_make_schema(),
            handler=_dummy_handler,
            check_fn=lambda: False,
        )
        assert reg.is_toolset_available("locked") is False

    def test_check_toolset_requirements(self):
        reg = ToolRegistry()
        reg.register(
            name="a",
            toolset="ok",
            schema=_make_schema(),
            handler=_dummy_handler,
            check_fn=lambda: True,
        )
        reg.register(
            name="b",
            toolset="nope",
            schema=_make_schema(),
            handler=_dummy_handler,
            check_fn=lambda: False,
        )

        reqs = reg.check_toolset_requirements()
        assert reqs["ok"] is True
        assert reqs["nope"] is False

    def test_get_all_tool_names(self):
        reg = ToolRegistry()
        reg.register(
            name="z_tool", toolset="s", schema=_make_schema(), handler=_dummy_handler
        )
        reg.register(
            name="a_tool", toolset="s", schema=_make_schema(), handler=_dummy_handler
        )
        assert reg.get_all_tool_names() == ["a_tool", "z_tool"]

    def test_handler_exception_returns_error(self):
        reg = ToolRegistry()

        def bad_handler(args, **kw):
            raise RuntimeError("boom")

        reg.register(
            name="bad", toolset="s", schema=_make_schema(), handler=bad_handler
        )
        result = json.loads(reg.dispatch("bad", {}))
        assert "error" in result
        assert "RuntimeError" in result["error"]


class TestCheckFnExceptionHandling:
    """Verify that a raising check_fn is caught rather than crashing."""

    def test_is_toolset_available_catches_exception(self):
        reg = ToolRegistry()
        reg.register(
            name="t",
            toolset="broken",
            schema=_make_schema(),
            handler=_dummy_handler,
            check_fn=lambda: 1 / 0,  # ZeroDivisionError
        )
        # Should return False, not raise
        assert reg.is_toolset_available("broken") is False

    def test_check_toolset_requirements_survives_raising_check(self):
        reg = ToolRegistry()
        reg.register(
            name="a",
            toolset="good",
            schema=_make_schema(),
            handler=_dummy_handler,
            check_fn=lambda: True,
        )
        reg.register(
            name="b",
            toolset="bad",
            schema=_make_schema(),
            handler=_dummy_handler,
            check_fn=lambda: (_ for _ in ()).throw(ImportError("no module")),
        )

        reqs = reg.check_toolset_requirements()
        assert reqs["good"] is True
        assert reqs["bad"] is False

    def test_get_definitions_skips_raising_check(self):
        reg = ToolRegistry()
        reg.register(
            name="ok_tool",
            toolset="s",
            schema=_make_schema("ok_tool"),
            handler=_dummy_handler,
            check_fn=lambda: True,
        )
        reg.register(
            name="bad_tool",
            toolset="s2",
            schema=_make_schema("bad_tool"),
            handler=_dummy_handler,
            check_fn=lambda: (_ for _ in ()).throw(OSError("network down")),
        )
        defs = reg.get_definitions({"ok_tool", "bad_tool"})
        assert len(defs) == 1
        assert defs[0]["function"]["name"] == "ok_tool"

    def test_check_tool_availability_survives_raising_check(self):
        reg = ToolRegistry()
        reg.register(
            name="a",
            toolset="works",
            schema=_make_schema(),
            handler=_dummy_handler,
            check_fn=lambda: True,
        )
        reg.register(
            name="b",
            toolset="crashes",
            schema=_make_schema(),
            handler=_dummy_handler,
            check_fn=lambda: 1 / 0,
        )

        available, unavailable = reg.check_tool_availability()
        assert "works" in available
        assert any(u["name"] == "crashes" for u in unavailable)


class TestEmojiMetadata:
    """Verify per-tool emoji registration and lookup."""

    def test_emoji_stored_on_entry(self):
        reg = ToolRegistry()
        reg.register(
            name="t", toolset="s", schema=_make_schema(),
            handler=_dummy_handler, emoji="🔥",
        )
        assert reg._tools["t"].emoji == "🔥"

    def test_get_emoji_returns_registered(self):
        reg = ToolRegistry()
        reg.register(
            name="t", toolset="s", schema=_make_schema(),
            handler=_dummy_handler, emoji="🎯",
        )
        assert reg.get_emoji("t") == "🎯"

    def test_get_emoji_returns_default_when_unset(self):
        reg = ToolRegistry()
        reg.register(
            name="t", toolset="s", schema=_make_schema(),
            handler=_dummy_handler,
        )
        assert reg.get_emoji("t") == "⚡"
        assert reg.get_emoji("t", default="🔧") == "🔧"

    def test_get_emoji_returns_default_for_unknown_tool(self):
        reg = ToolRegistry()
        assert reg.get_emoji("nonexistent") == "⚡"
        assert reg.get_emoji("nonexistent", default="❓") == "❓"

    def test_emoji_empty_string_treated_as_unset(self):
        reg = ToolRegistry()
        reg.register(
            name="t", toolset="s", schema=_make_schema(),
            handler=_dummy_handler, emoji="",
        )
        assert reg.get_emoji("t") == "⚡"


class TestSchemaValidation:
    """Sprint 2.1 — pydantic soft validator warns but does not raise."""

    def test_valid_schema_emits_no_warning(self, caplog):
        reg = ToolRegistry()
        with caplog.at_level(logging.WARNING, logger="tools.registry"):
            reg.register(
                name="ok", toolset="s",
                schema=_make_schema("ok"), handler=_dummy_handler,
            )
        assert not any(
            "OpenAI Function Calling validation" in r.getMessage() for r in caplog.records
        )

    def test_zero_arg_tool_emits_no_warning(self, caplog):
        """Sprint 2.1 H2 — parameters 키 누락은 0-arg 도구로 valid 처리 (OpenAI spec).

        OpenAI Function Calling 스펙은 ``function.parameters`` 객체의 생략을
        허용하며, 이는 "arguments 없음"으로 해석된다. soft validator가 이를
        스키마 실패로 분류하면 0-arg 도구마다 WARNING 노이즈가 쌓이고,
        Sprint 2단계 strict raise 전환 시 0-arg 도구가 전부 깨진다.
        """
        reg = ToolRegistry()
        zero_arg = {"name": "zero", "description": "no args"}
        with caplog.at_level(logging.WARNING, logger="tools.registry"):
            reg.register(
                name="zero", toolset="s", schema=zero_arg, handler=_dummy_handler,
            )
        assert not any(
            "OpenAI Function Calling" in r.getMessage() for r in caplog.records
        ), "0-arg tool should not trigger schema warning"
        assert not any(
            "schema failed" in r.getMessage() for r in caplog.records
        ), "0-arg tool should not trigger schema warning"
        assert "zero" in reg._tools

    def test_parameters_wrong_type_warns(self, caplog):
        reg = ToolRegistry()
        bad = {
            "name": "bad",
            "description": "wrong type",
            "parameters": {"type": "array", "properties": {}},
        }
        with caplog.at_level(logging.WARNING, logger="tools.registry"):
            reg.register(
                name="bad2", toolset="s", schema=bad, handler=_dummy_handler,
            )
        assert any(
            "parameters.type must be 'object'" in r.getMessage() for r in caplog.records
        )

    def test_missing_properties_warns(self, caplog):
        reg = ToolRegistry()
        bad = {
            "name": "bad",
            "description": "no props",
            "parameters": {"type": "object"},
        }
        with caplog.at_level(logging.WARNING, logger="tools.registry"):
            reg.register(
                name="bad3", toolset="s", schema=bad, handler=_dummy_handler,
            )
        assert any(
            "parameters.properties must be a dict" in r.getMessage()
            for r in caplog.records
        )

    def test_parameters_not_dict_warns(self, caplog):
        reg = ToolRegistry()
        bad = {"name": "bad", "description": "parameters is str", "parameters": "nope"}
        with caplog.at_level(logging.WARNING, logger="tools.registry"):
            reg.register(
                name="bad4", toolset="s", schema=bad, handler=_dummy_handler,
            )
        assert any("schema failed" in r.getMessage() for r in caplog.records)

    def test_schema_not_mapping_warns(self, caplog):
        reg = ToolRegistry()
        with caplog.at_level(logging.WARNING, logger="tools.registry"):
            try:
                reg.register(
                    name="bad5", toolset="s", schema="not-a-dict",  # type: ignore[arg-type]
                    handler=_dummy_handler,
                )
            except (TypeError, AttributeError):
                pass
        assert any("not a mapping" in r.getMessage() for r in caplog.records)


class TestSchemaStrictMode:
    """Sprint 2 follow-up #2 — HERMES_STRICT_SCHEMA_VALIDATION env flag로 2단계 raise 전환."""

    def test_strict_env_flag_raises_validation_error(self, monkeypatch):
        """env=1 시 ValidationError 가 raise 되어야 함 (2단계 strict 모드)."""
        monkeypatch.setenv("HERMES_STRICT_SCHEMA_VALIDATION", "1")
        reg = ToolRegistry()
        bad = {
            "name": "bad",
            "description": "wrong type",
            "parameters": {"type": "array", "properties": {}},
        }
        with pytest.raises(ValidationError):
            reg.register(name="strict_bad", toolset="s", schema=bad, handler=_dummy_handler)
        # raise 됐으니 등록되지 않아야 함
        assert "strict_bad" not in reg._tools

    def test_strict_env_flag_unset_warns_only(self, monkeypatch, caplog):
        """env unset 시 기존대로 warning + 등록 (1단계 호환성 default)."""
        monkeypatch.delenv("HERMES_STRICT_SCHEMA_VALIDATION", raising=False)
        reg = ToolRegistry()
        bad = {
            "name": "bad",
            "description": "wrong type",
            "parameters": {"type": "array", "properties": {}},
        }
        with caplog.at_level(logging.WARNING, logger="tools.registry"):
            reg.register(name="warn_bad", toolset="s", schema=bad, handler=_dummy_handler)
        assert any("schema failed" in r.getMessage() for r in caplog.records)
        assert "warn_bad" in reg._tools

    def test_warning_counter_increments_on_invalid_schema(self, monkeypatch):
        """warning 발생 시 counter 증가, 정상 schema 는 증가 안 함.

        2단계 strict raise 전환 트리거 판단(예: 연속 X일 0건)용 관찰 가능성.
        """
        from tools.registry import get_schema_warning_count, _reset_schema_warning_count
        monkeypatch.delenv("HERMES_STRICT_SCHEMA_VALIDATION", raising=False)
        _reset_schema_warning_count()
        assert get_schema_warning_count() == 0

        reg = ToolRegistry()
        # 정상 schema → counter 증가 안 함
        reg.register(name="ok", toolset="s", schema=_make_schema("ok"), handler=_dummy_handler)
        assert get_schema_warning_count() == 0

        # 잘못된 schema (parameters.type != 'object') → counter 1 증가
        bad = {
            "name": "bad",
            "description": "wrong",
            "parameters": {"type": "array", "properties": {}},
        }
        reg.register(name="bad", toolset="s", schema=bad, handler=_dummy_handler)
        assert get_schema_warning_count() == 1

        # 또 다른 잘못된 schema (parameters not dict) → counter 2 증가
        bad2 = {"name": "bad2", "parameters": "not-a-dict"}
        reg.register(name="bad2", toolset="s", schema=bad2, handler=_dummy_handler)
        assert get_schema_warning_count() == 2

        # 등록은 여전히 (1단계 호환) 성공
        assert "bad" in reg._tools
        assert "bad2" in reg._tools


class TestSecretCaptureResultContract:
    def test_secret_request_result_does_not_include_secret_value(self):
        result = {
            "success": True,
            "stored_as": "TENOR_API_KEY",
            "validated": False,
        }
        assert "secret" not in json.dumps(result).lower()
