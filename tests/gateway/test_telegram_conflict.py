import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig


def _ensure_telegram_mock():
    if "telegram" in sys.modules and hasattr(sys.modules["telegram"], "__file__"):
        return

    telegram_mod = MagicMock()
    telegram_mod.ext.ContextTypes.DEFAULT_TYPE = type(None)
    telegram_mod.constants.ParseMode.MARKDOWN_V2 = "MarkdownV2"
    telegram_mod.constants.ChatType.GROUP = "group"
    telegram_mod.constants.ChatType.SUPERGROUP = "supergroup"
    telegram_mod.constants.ChatType.CHANNEL = "channel"
    telegram_mod.constants.ChatType.PRIVATE = "private"

    # Provide real exception classes so ``except (NetworkError, ...)`` in
    # connect() doesn't blow up with "catching classes that do not inherit
    # from BaseException" when another xdist worker pollutes sys.modules.
    telegram_mod.error.NetworkError = type("NetworkError", (OSError,), {})
    telegram_mod.error.TimedOut = type("TimedOut", (OSError,), {})
    telegram_mod.error.BadRequest = type("BadRequest", (Exception,), {})

    for name in ("telegram", "telegram.ext", "telegram.constants", "telegram.request"):
        sys.modules.setdefault(name, telegram_mod)
    sys.modules.setdefault("telegram.error", telegram_mod.error)


_ensure_telegram_mock()

from gateway.platforms.telegram import TelegramAdapter  # noqa: E402


@pytest.fixture(autouse=True)
def _no_auto_discovery(monkeypatch):
    """Disable DoH auto-discovery so connect() uses the plain builder chain."""
    async def _noop():
        return []
    monkeypatch.setattr("gateway.platforms.telegram.discover_fallback_ips", _noop)
    # Mock HTTPXRequest so the builder chain doesn't fail
    monkeypatch.setattr("gateway.platforms.telegram.HTTPXRequest", lambda **kwargs: MagicMock())


@pytest.mark.asyncio
async def test_connect_rejects_same_host_token_lock(monkeypatch):
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="secret-token"))

    monkeypatch.setattr(
        "gateway.status.acquire_scoped_lock",
        lambda scope, identity, metadata=None: (False, {"pid": 4242}),
    )

    ok = await adapter.connect()

    assert ok is False
    assert adapter.fatal_error_code == "telegram-bot-token_lock"
    assert adapter.has_fatal_error is True
    assert "already in use" in adapter.fatal_error_message


@pytest.mark.asyncio
async def test_polling_conflict_retries_before_fatal(monkeypatch):
    """A single 409 should trigger a retry, not an immediate fatal error."""
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***"))
    fatal_handler = AsyncMock()
    adapter.set_fatal_error_handler(fatal_handler)

    monkeypatch.setattr(
        "gateway.status.acquire_scoped_lock",
        lambda scope, identity, metadata=None: (True, None),
    )
    monkeypatch.setattr(
        "gateway.status.release_scoped_lock",
        lambda scope, identity: None,
    )

    captured = {}

    async def fake_start_polling(**kwargs):
        captured["error_callback"] = kwargs["error_callback"]

    updater = SimpleNamespace(
        start_polling=AsyncMock(side_effect=fake_start_polling),
        stop=AsyncMock(),
        running=True,
    )
    bot = SimpleNamespace(set_my_commands=AsyncMock(), delete_webhook=AsyncMock())
    app = SimpleNamespace(
        bot=bot,
        updater=updater,
        add_handler=MagicMock(),
        initialize=AsyncMock(),
        start=AsyncMock(),
    )
    builder = MagicMock()
    builder.token.return_value = builder
    builder.request.return_value = builder
    builder.get_updates_request.return_value = builder
    builder.build.return_value = app
    monkeypatch.setattr("gateway.platforms.telegram.Application", SimpleNamespace(builder=MagicMock(return_value=builder)))

    # Speed up retries for testing
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    ok = await adapter.connect()

    assert ok is True
    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
    assert callable(captured["error_callback"])

    conflict = type("Conflict", (Exception,), {})

    # First conflict: should retry, NOT be fatal
    captured["error_callback"](conflict("Conflict: terminated by other getUpdates request"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # Give the scheduled task a chance to run
    for _ in range(10):
        await asyncio.sleep(0)

    assert adapter.has_fatal_error is False, "First conflict should not be fatal"
    assert adapter._polling_conflict_count == 0, "Count should reset after successful retry"


@pytest.mark.asyncio
async def test_polling_conflict_becomes_fatal_after_retries(monkeypatch):
    """After exhausting retries, the conflict should become fatal."""
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***"))
    fatal_handler = AsyncMock()
    adapter.set_fatal_error_handler(fatal_handler)

    monkeypatch.setattr(
        "gateway.status.acquire_scoped_lock",
        lambda scope, identity, metadata=None: (True, None),
    )
    monkeypatch.setattr(
        "gateway.status.release_scoped_lock",
        lambda scope, identity: None,
    )

    captured = {}

    async def fake_start_polling(**kwargs):
        captured["error_callback"] = kwargs["error_callback"]

    # Make start_polling fail on retries to exhaust retries
    call_count = {"n": 0}

    async def failing_start_polling(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call (initial connect) succeeds
            captured["error_callback"] = kwargs["error_callback"]
        else:
            # Retry calls fail
            raise Exception("Connection refused")

    updater = SimpleNamespace(
        start_polling=AsyncMock(side_effect=failing_start_polling),
        stop=AsyncMock(),
        running=True,
    )
    bot = SimpleNamespace(set_my_commands=AsyncMock(), delete_webhook=AsyncMock())
    app = SimpleNamespace(
        bot=bot,
        updater=updater,
        add_handler=MagicMock(),
        initialize=AsyncMock(),
        start=AsyncMock(),
    )
    builder = MagicMock()
    builder.token.return_value = builder
    builder.request.return_value = builder
    builder.get_updates_request.return_value = builder
    builder.build.return_value = app
    monkeypatch.setattr("gateway.platforms.telegram.Application", SimpleNamespace(builder=MagicMock(return_value=builder)))

    # Speed up retries for testing
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    ok = await adapter.connect()
    assert ok is True

    conflict = type("Conflict", (Exception,), {})

    # Directly call _handle_polling_conflict to avoid event-loop scheduling
    # complexity.  Each call simulates one 409 from Telegram.
    for i in range(4):
        await adapter._handle_polling_conflict(
            conflict("Conflict: terminated by other getUpdates request")
        )

    # After 3 failed retries (count 1-3 each enter the retry branch but
    # start_polling raises), the 4th conflict pushes count to 4 which
    # exceeds MAX_CONFLICT_RETRIES (3), entering the fatal branch.
    assert adapter.fatal_error_code == "telegram_polling_conflict", (
        f"Expected fatal after 4 conflicts, got code={adapter.fatal_error_code}, "
        f"count={adapter._polling_conflict_count}"
    )
    assert adapter.has_fatal_error is True
    fatal_handler.assert_awaited_once()
    # Sprint 2 follow-up #1 — fatal 진입 시 카운터 0 reset (동일 adapter 인스턴스
    # 재활용 시 다음 첫 conflict 부터 즉시 MAX 초과로 분기되어 retry 박탈되는 회귀 방지)
    assert adapter._polling_conflict_count == 0, (
        f"Counter must reset to 0 on fatal exhaustion, got {adapter._polling_conflict_count}"
    )


@pytest.mark.asyncio
async def test_polling_conflict_reacquire_failure_unifies_fatal_code(monkeypatch):
    """Sprint 2.2 H1 — 재획득 실패 시 fatal_error_code가 conflict guard 키와 통일되어야 한다.

    base.py의 ``_acquire_platform_lock`` 실패는 ``scope+'_lock'`` (예:
    ``telegram-bot-token_lock``) 으로 fatal_error_code 를 세팅하지만,
    ``_handle_polling_conflict`` line 261 조기 탈출 가드는
    ``telegram_polling_conflict`` 키를 기대한다. telegram.py 에서 명시
    ``_set_fatal_error`` 호출로 키를 통일해야 다음 conflict 호출에서
    무한 재시도를 막을 수 있다.
    """
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***"))
    fatal_handler = AsyncMock()
    adapter.set_fatal_error_handler(fatal_handler)

    acquire_calls = {"n": 0}

    def _acquire(scope, identity, metadata=None):
        acquire_calls["n"] += 1
        if acquire_calls["n"] == 1:
            return (True, None)
        return (False, {"pid": 9999})

    monkeypatch.setattr("gateway.status.acquire_scoped_lock", _acquire)
    monkeypatch.setattr("gateway.status.release_scoped_lock", lambda scope, identity: None)

    captured = {}

    async def fake_start_polling(**kwargs):
        captured["error_callback"] = kwargs["error_callback"]

    updater = SimpleNamespace(
        start_polling=AsyncMock(side_effect=fake_start_polling),
        stop=AsyncMock(),
        running=True,
    )
    bot = SimpleNamespace(set_my_commands=AsyncMock(), delete_webhook=AsyncMock())
    app = SimpleNamespace(
        bot=bot,
        updater=updater,
        add_handler=MagicMock(),
        initialize=AsyncMock(),
        start=AsyncMock(),
    )
    builder = MagicMock()
    builder.token.return_value = builder
    builder.request.return_value = builder
    builder.get_updates_request.return_value = builder
    builder.build.return_value = app
    monkeypatch.setattr(
        "gateway.platforms.telegram.Application",
        SimpleNamespace(builder=MagicMock(return_value=builder)),
    )
    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    ok = await adapter.connect()
    assert ok is True

    conflict = type("Conflict", (Exception,), {})
    await adapter._handle_polling_conflict(
        conflict("Conflict: terminated by other getUpdates request")
    )

    assert adapter.fatal_error_code == "telegram_polling_conflict", (
        f"reacquire failure should unify with conflict guard key, "
        f"got {adapter.fatal_error_code!r}"
    )
    assert adapter.has_fatal_error is True
    assert adapter.fatal_error_retryable is False
    # codex H2 — supervisor/recovery notify 가 트리거되어야 함
    fatal_handler.assert_awaited_once()
    # Sprint 2 follow-up #1 — fatal 진입 시 카운터 0 reset
    assert adapter._polling_conflict_count == 0, (
        f"Counter must reset to 0 on reacquire-failure fatal path, got {adapter._polling_conflict_count}"
    )


@pytest.mark.asyncio
async def test_polling_conflict_handles_app_disconnected_during_sleep(monkeypatch):
    """codex H1 race — sleep 중 disconnect() 가 self._app=None 만들면 NPE 없이 정상 return.

    release_platform_lock → asyncio.sleep → acquire_platform_lock 사이에 다른
    async task 가 ``adapter.disconnect()`` 를 호출하면 ``self._app`` 이 None 으로
    초기화될 수 있다. 이후 ``self._app.updater.start_polling(...)`` 시도가 NPE 를
    발생시키고 except 블록의 단순 ``return`` 은 방금 재획득한 platform lock 을
    release 하지 않아 supervisor 재기동 시 동일 token 확보가 영구 차단된다.

    가드: reacquire 직후 ``self._app`` / ``self._app.updater`` 가 None 이면
    재획득한 lock 을 즉시 release 하고 return.
    """
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***"))

    monkeypatch.setattr(
        "gateway.status.acquire_scoped_lock",
        lambda scope, identity, metadata=None: (True, None),
    )
    release_calls = []
    monkeypatch.setattr(
        "gateway.status.release_scoped_lock",
        lambda scope, identity: release_calls.append((scope, identity)),
    )

    captured = {}

    async def fake_start_polling(**kwargs):
        captured["error_callback"] = kwargs["error_callback"]

    updater = SimpleNamespace(
        start_polling=AsyncMock(side_effect=fake_start_polling),
        stop=AsyncMock(),
        running=True,
    )
    bot = SimpleNamespace(set_my_commands=AsyncMock(), delete_webhook=AsyncMock())
    app = SimpleNamespace(
        bot=bot,
        updater=updater,
        add_handler=MagicMock(),
        initialize=AsyncMock(),
        start=AsyncMock(),
    )
    builder = MagicMock()
    builder.token.return_value = builder
    builder.request.return_value = builder
    builder.get_updates_request.return_value = builder
    builder.build.return_value = app
    monkeypatch.setattr(
        "gateway.platforms.telegram.Application",
        SimpleNamespace(builder=MagicMock(return_value=builder)),
    )

    # sleep 중 disconnect() 동시 실행 흉내 — self._app=None 으로 초기화
    async def _disconnect_during_sleep(_):
        adapter._app = None

    monkeypatch.setattr("asyncio.sleep", _disconnect_during_sleep)

    ok = await adapter.connect()
    assert ok is True

    conflict = type("Conflict", (Exception,), {})

    # NPE 없이 정상 return 해야 함 (가드 작동)
    await adapter._handle_polling_conflict(
        conflict("Conflict: terminated by other getUpdates request")
    )

    # 가드 작동 검증: self._app=None 이므로 재획득 후 start_polling 시도 안 함 +
    # 재획득한 lock 도 release 되어 누수 없음 (release_scoped_lock 2회 호출).
    assert len(release_calls) >= 2, (
        f"Reacquired lock must be released when adapter disconnected during sleep, "
        f"got {len(release_calls)} release call(s)"
    )
    assert adapter.has_fatal_error is False, (
        "disconnect during sleep is normal teardown, not fatal"
    )


@pytest.mark.asyncio
async def test_polling_conflict_releases_reacquired_lock_on_cancel(monkeypatch):
    """Sprint 2 follow-up #3 (gemini MEDIUM) — start_polling 중 cancel 시 재획득 lock 누수 차단.

    부모 task 가 ``_handle_polling_conflict`` 진행 중 cancel 될 때 가장 위험한
    지점은 **재획득 후 start_polling 도중** cancel.  현재 코드는
    ``except Exception`` 만 catch 하므로 ``CancelledError`` (BaseException
    subclass, 3.8+ 부터 Exception 아님) 가 그대로 propagate 되며, 재획득한
    platform lock 이 release 되지 않아 supervisor 재기동 시 동일 token 확보가
    영구 차단된다.

    가드: retry branch 전체를 ``try/except asyncio.CancelledError`` 로 감싸고,
    cancel 발생 시 ``_release_platform_lock()`` (idempotent) 호출 후 propagate.
    """
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***"))

    monkeypatch.setattr(
        "gateway.status.acquire_scoped_lock",
        lambda scope, identity, metadata=None: (True, None),
    )
    release_calls = []
    monkeypatch.setattr(
        "gateway.status.release_scoped_lock",
        lambda scope, identity: release_calls.append((scope, identity)),
    )

    captured = {"calls": 0}

    async def fake_start_polling(**kwargs):
        captured["calls"] += 1
        if captured["calls"] == 1:
            # connect() 첫 호출 — 정상 setup
            captured["error_callback"] = kwargs["error_callback"]
            return
        # _handle_polling_conflict 의 재시도 호출 — cancel 흉내
        raise asyncio.CancelledError()

    updater = SimpleNamespace(
        start_polling=AsyncMock(side_effect=fake_start_polling),
        stop=AsyncMock(),
        running=True,
    )
    bot = SimpleNamespace(set_my_commands=AsyncMock(), delete_webhook=AsyncMock())
    app = SimpleNamespace(
        bot=bot,
        updater=updater,
        add_handler=MagicMock(),
        initialize=AsyncMock(),
        start=AsyncMock(),
    )
    builder = MagicMock()
    builder.token.return_value = builder
    builder.request.return_value = builder
    builder.get_updates_request.return_value = builder
    builder.build.return_value = app
    monkeypatch.setattr(
        "gateway.platforms.telegram.Application",
        SimpleNamespace(builder=MagicMock(return_value=builder)),
    )
    monkeypatch.setattr("asyncio.sleep", AsyncMock())  # sleep 통과

    ok = await adapter.connect()
    assert ok is True
    assert captured["calls"] == 1, "connect() should have called start_polling once"

    conflict = type("Conflict", (Exception,), {})

    # 재시도 호출 시 start_polling 이 CancelledError raise → 가드 작동해야 함
    with pytest.raises(asyncio.CancelledError):
        await adapter._handle_polling_conflict(
            conflict("Conflict: terminated by other getUpdates request")
        )

    # release 가 최소 2회 호출되어야 함 — line 287 첫 release + 가드 release
    # (재획득 lock 누수 차단 핵심 검증)
    assert len(release_calls) >= 2, (
        f"Reacquired lock must be released on CancelledError, got {len(release_calls)} call(s)"
    )
    assert adapter._platform_lock_identity is None, (
        "platform lock identity must be cleared after cancellation"
    )


@pytest.mark.asyncio
async def test_connect_marks_retryable_fatal_error_for_startup_network_failure(monkeypatch):
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***"))

    monkeypatch.setattr(
        "gateway.status.acquire_scoped_lock",
        lambda scope, identity, metadata=None: (True, None),
    )
    monkeypatch.setattr(
        "gateway.status.release_scoped_lock",
        lambda scope, identity: None,
    )

    builder = MagicMock()
    builder.token.return_value = builder
    builder.request.return_value = builder
    builder.get_updates_request.return_value = builder
    app = SimpleNamespace(
        bot=SimpleNamespace(delete_webhook=AsyncMock(), set_my_commands=AsyncMock()),
        updater=SimpleNamespace(),
        add_handler=MagicMock(),
        initialize=AsyncMock(side_effect=RuntimeError("Temporary failure in name resolution")),
        start=AsyncMock(),
    )
    builder.build.return_value = app
    monkeypatch.setattr("gateway.platforms.telegram.Application", SimpleNamespace(builder=MagicMock(return_value=builder)))

    ok = await adapter.connect()

    assert ok is False
    assert adapter.fatal_error_code == "telegram_connect_error"
    assert adapter.fatal_error_retryable is True
    assert "Temporary failure in name resolution" in adapter.fatal_error_message


@pytest.mark.asyncio
async def test_connect_clears_webhook_before_polling(monkeypatch):
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***"))

    monkeypatch.setattr(
        "gateway.status.acquire_scoped_lock",
        lambda scope, identity, metadata=None: (True, None),
    )
    monkeypatch.setattr(
        "gateway.status.release_scoped_lock",
        lambda scope, identity: None,
    )

    updater = SimpleNamespace(
        start_polling=AsyncMock(),
        stop=AsyncMock(),
        running=True,
    )
    bot = SimpleNamespace(
        delete_webhook=AsyncMock(),
        set_my_commands=AsyncMock(),
    )
    app = SimpleNamespace(
        bot=bot,
        updater=updater,
        add_handler=MagicMock(),
        initialize=AsyncMock(),
        start=AsyncMock(),
    )
    builder = MagicMock()
    builder.token.return_value = builder
    builder.request.return_value = builder
    builder.get_updates_request.return_value = builder
    builder.build.return_value = app
    monkeypatch.setattr(
        "gateway.platforms.telegram.Application",
        SimpleNamespace(builder=MagicMock(return_value=builder)),
    )

    ok = await adapter.connect()

    assert ok is True
    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)


@pytest.mark.asyncio
async def test_disconnect_skips_inactive_updater_and_app(monkeypatch):
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="***"))

    updater = SimpleNamespace(running=False, stop=AsyncMock())
    app = SimpleNamespace(
        updater=updater,
        running=False,
        stop=AsyncMock(),
        shutdown=AsyncMock(),
    )
    adapter._app = app

    warning = MagicMock()
    monkeypatch.setattr("gateway.platforms.telegram.logger.warning", warning)

    await adapter.disconnect()

    updater.stop.assert_not_awaited()
    app.stop.assert_not_awaited()
    app.shutdown.assert_awaited_once()
    warning.assert_not_called()
