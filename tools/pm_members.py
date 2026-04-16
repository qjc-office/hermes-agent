"""QJC PM 팀원 단일 원장.

Supabase UUID, Discord ID, 이름을 한 곳에서 관리한다.
pm_supabase_tool.py, pm_discord_tool.py가 이 모듈을 임포트한다.
팀원 추가/변경 시 이 파일만 수정하면 된다.
"""

from typing import Dict

# ---------------------------------------------------------------------------
# 팀원 정의 (단일 소스)
# ---------------------------------------------------------------------------

MEMBERS: Dict[str, Dict[str, str]] = {
    "sangrok": {
        "id": "302bc407-b580-4633-95db-592f00b9fd8d",
        "name": "정상록",
        "discord_id": "905300831501430914",
    },
    "kwango": {
        "id": "0e77befe-8f50-4860-9b6f-de0ac9cd16a4",
        "name": "김광오",
        "discord_id": "1404732845183864912",
    },
}

# ---------------------------------------------------------------------------
# 파생 매핑 (역매핑)
# ---------------------------------------------------------------------------

# member_id → 이름
MEMBER_NAME_BY_ID: Dict[str, str] = {m["id"]: m["name"] for m in MEMBERS.values()}

# member_id → 코드명 (라우팅용: UUID → "sangrok"/"kwango")
MEMBER_CODE_BY_ID: Dict[str, str] = {v["id"]: k for k, v in MEMBERS.items()}

# 코드명 → Discord ID
DISCORD_ID_BY_CODE: Dict[str, str] = {k: v["discord_id"] for k, v in MEMBERS.items()}

# PM 환경변수 (Supabase 접근용)
PM_ENV_VARS = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
