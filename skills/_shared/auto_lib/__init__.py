"""auto_lib — Hermes 자동화 9종이 공유하는 경량 라이브러리.

- state: cron 멱등성(이미 처리한 항목 재처리 방지) 상태 저장소
- notify: deliver 마커 + Telegram/Discord 메시지 포맷 헬퍼
"""

from skills._shared.auto_lib import notify, state  # noqa: F401

__all__ = ["state", "notify"]
