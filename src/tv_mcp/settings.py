import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=True)

HOST = os.getenv("TV_MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("TV_MCP_PORT", "8790"))
TOKEN = os.getenv("TV_MCP_TOKEN", "")
LIBRARY_TOKEN = os.getenv("LIBRARY_TOKEN", "")
LIBRARY_APP = os.getenv("LIBRARY_APP", "")
HISTORY_DB = os.getenv("HISTORY_DB", str(ROOT / "history.db"))
TUNNELD_URL = os.getenv("TUNNELD_URL", "http://127.0.0.1:49151")
SONOS_FOLLOW_ROOM = os.getenv("SONOS_FOLLOW_ROOM", "")
CLAUDE_CODE_OAUTH_TOKEN = os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "")


def load_tvs() -> list[dict]:
    tvs = []
    n = 1
    while os.getenv(f"ATV_{n}_NAME"):
        tvs.append({
            "name": os.getenv(f"ATV_{n}_NAME"),
            "id": os.getenv(f"ATV_{n}_ID", ""),
            "companion": os.getenv(f"ATV_{n}_COMPANION", ""),
            "udid": os.getenv(f"ATV_{n}_UDID", ""),
        })
        n += 1
    return tvs


def load_rokus() -> list[dict]:
    rokus = []
    n = 1
    while os.getenv(f"ROKU_{n}_NAME"):
        rokus.append({
            "name": os.getenv(f"ROKU_{n}_NAME"),
            "host": os.getenv(f"ROKU_{n}_HOST", ""),
            "player_id": os.getenv(f"ROKU_{n}_PLAYER_ID", ""),
        })
        n += 1
    return rokus


TVS = load_tvs()
ROKUS = load_rokus()
