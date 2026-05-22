"""멱등성 상태 저장소 — cron 자동화가 중복 처리를 피하기 위한 영속 상태.

cron은 매 실행마다 새 세션에서 깨어난다. "어제 이미 알린 메일을 또 알리지 않기",
"어제 본 북마크를 또 저장하지 않기"를 보장하려면 실행 간 영속되는 상태가 필요하다.
qjc-pm 의 pm_save_decision / pm_get_recent_decisions 패턴을 일반화한 것.

모든 상태는 get_hermes_home()/automation-state/{namespace}.json 에 저장된다.
HERMES_HOME 환경변수로 경로가 결정되므로 테스트(conftest)가 자동 격리한다.
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

# get_hermes_home 은 모든 ~/.hermes 경로의 SSOT (CLAUDE.md 불변식 #2).
# cron script 로 직접 실행될 때도 import 되도록 프로젝트 루트를 sys.path 에 보장.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from hermes_constants import get_hermes_home  # noqa: E402

_DEFAULT_MAX_KEEP = 1000
_SAFE_NS = re.compile(r"[^A-Za-z0-9_-]")


def _safe_namespace(namespace: str) -> str:
    """파일명으로 안전한 namespace (path traversal 방지)."""
    cleaned = _SAFE_NS.sub("-", str(namespace)).strip("-")
    if not cleaned:
        raise ValueError(f"invalid namespace: {namespace!r}")
    return cleaned


def _state_dir() -> Path:
    return get_hermes_home() / "automation-state"


def state_path(namespace: str) -> Path:
    """주어진 namespace 의 상태 파일 경로."""
    return _state_dir() / f"{_safe_namespace(namespace)}.json"


def load_state(namespace: str) -> Dict[str, Any]:
    """상태를 읽는다. 파일이 없거나 손상됐으면 빈 dict."""
    path = state_path(namespace)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(namespace: str, data: Dict[str, Any]) -> None:
    """상태를 원자적으로 저장한다 (0600).

    직렬화를 파일 쓰기 전에 수행하므로, 직렬화 실패 시 기존 파일이 보존된다.
    """
    payload = json.dumps(data, ensure_ascii=False, indent=2)  # 실패 시 여기서 raise
    path = state_path(namespace)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(dir=str(directory), prefix=f".{path.stem}_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)  # POSIX atomic
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _seen_list(namespace: str) -> List[str]:
    return list(load_state(namespace).get("seen", []))


def is_seen(namespace: str, item_id: Any) -> bool:
    """item_id 가 이미 처리된 적 있는지."""
    return str(item_id) in set(_seen_list(namespace))


def mark_seen(
    namespace: str,
    ids: Iterable[Any],
    max_keep: int = _DEFAULT_MAX_KEEP,
) -> None:
    """ids 를 처리됨으로 기록한다. 최근 max_keep 개만 유지 (무한 증가 방지)."""
    data = load_state(namespace)
    seen = list(data.get("seen", []))
    seen_set = set(seen)
    for raw in ids:
        sid = str(raw)
        if sid not in seen_set:
            seen.append(sid)
            seen_set.add(sid)
    if max_keep and len(seen) > max_keep:
        seen = seen[-max_keep:]
    data["seen"] = seen
    save_state(namespace, data)


def filter_new(
    namespace: str,
    items: Iterable[Any],
    key: Callable[[Any], Any],
    commit: bool = True,
    max_keep: int = _DEFAULT_MAX_KEEP,
) -> List[Any]:
    """아직 처리하지 않은 신규 항목만 반환한다.

    commit=True (기본) 이면 반환된 항목을 처리됨으로 기록 → 다음 실행에서 제외된다.
    commit=False 이면 미리보기/dry-run 용으로 기록하지 않는다.
    """
    seen_set = set(_seen_list(namespace))
    new_items: List[Any] = []
    new_ids: List[str] = []
    for it in items:
        sid = str(key(it))
        if sid not in seen_set:
            new_items.append(it)
            new_ids.append(sid)
            seen_set.add(sid)  # 같은 배치 내 중복 방지
    if commit and new_ids:
        mark_seen(namespace, new_ids, max_keep=max_keep)
    return new_items
