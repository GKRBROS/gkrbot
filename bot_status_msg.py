"""
bot_status_msg.py — Persistent store for global developer announcements/status notices.
Can be updated via website (admin_api.py) or dev command (/devmessage).
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

STATUS_FILE = Path(__file__).resolve().parent / "bot_status_message.json"


def get_status_message() -> Optional[Dict[str, Any]]:
    """Retrieve the currently active status message, if any."""
    if not STATUS_FILE.exists():
        return None
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        if data.get("active") and data.get("message"):
            return data
    except Exception:
        pass
    return None


def get_all_status_info() -> Dict[str, Any]:
    """Retrieve full status record, even if disabled."""
    if not STATUS_FILE.exists():
        return {"active": False, "message": "", "author": "None", "updated_at": ""}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"active": False, "message": "", "author": "None", "updated_at": ""}


def set_status_message(message: str, author: str = "Dev", active: bool = True) -> Dict[str, Any]:
    """Save or update the global status notice."""
    record = {
        "active": bool(active),
        "message": (message or "").strip(),
        "author": str(author),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    }
    STATUS_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def clear_status_message() -> Dict[str, Any]:
    """Disable the active status notice."""
    return set_status_message("", author="System", active=False)
