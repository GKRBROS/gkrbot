"""
registration.py — Dynamic Registration & Application System for JADE / GKR Bot.

A complete, production-ready system providing:
  • Multi-form builder with dynamic question types (Short Text, Paragraph, Number,
    Yes/No, Single Select, Multiple Select, User, Role, Channel, Date, URL).
  • Multi-step dynamic modal and interactive component runner handling Discord limitations.
  • Deep validation engine with type-safe rules (min/max length, number ranges, date parsing, URL protocol).
  • Post-registration automations: automatic Nickname change from answer, multi-role additions & removals,
    and conditional roles based on user answers.
  • Optional staff review system with persistent interactive action buttons and rejection modal.
  • Dedicated Discord audit logging and database event logs.
  • Persistent panel buttons and review buttons surviving bot restarts.
  • Member commands to view, check status, and cancel pending applications.
"""

from __future__ import annotations

import os
import re
import json
import time
import uuid
import sqlite3
import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands

from bot_config import BOT_NAME
from gkr_ui import C, embed_success, embed_error, embed_info, embed_warning, fmt_ts, fmt_rel

DB_PATH = os.path.join(os.path.dirname(__file__), "registration.sqlite3")

# Supported Field Types
FIELD_TYPES = {
    "short_text": "Short Text (Single Line)",
    "paragraph": "Paragraph (Multi-line Text)",
    "number": "Number (Numeric Input)",
    "yes_no": "Yes / No (Boolean Choice)",
    "single_select": "Single Choice (Dropdown)",
    "multiple_select": "Multiple Choice (Dropdown)",
    "user_select": "Discord User Selector",
    "role_select": "Discord Role Selector",
    "channel_select": "Discord Channel Selector",
    "date": "Date (YYYY-MM-DD)",
    "url": "Website / Portfolio URL"
}

BUTTON_STYLES = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger
}


# ---------------------------------------------------------------------------
# Database Management
# ---------------------------------------------------------------------------

class RegistrationDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.initialize()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS registration_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    channel_id TEXT DEFAULT NULL,
                    panel_message_id TEXT DEFAULT NULL,
                    button_label TEXT NOT NULL DEFAULT 'Register',
                    button_emoji TEXT NOT NULL DEFAULT '📝',
                    button_style TEXT NOT NULL DEFAULT 'primary',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    
                    auto_role_enabled INTEGER NOT NULL DEFAULT 0,
                    add_role_ids TEXT DEFAULT '[]',
                    remove_role_enabled INTEGER NOT NULL DEFAULT 0,
                    remove_role_ids TEXT DEFAULT '[]',
                    conditional_roles TEXT DEFAULT '{}',
                    
                    change_nickname_enabled INTEGER NOT NULL DEFAULT 0,
                    nickname_question_id INTEGER DEFAULT NULL,
                    nickname_format TEXT DEFAULT '{name}',
                    
                    approval_mode TEXT NOT NULL DEFAULT 'automatic',
                    review_channel_id TEXT DEFAULT NULL,
                    log_channel_id TEXT DEFAULT NULL,
                    
                    single_submission INTEGER NOT NULL DEFAULT 1,
                    allow_edit INTEGER NOT NULL DEFAULT 0,
                    success_message TEXT DEFAULT 'Your registration has been submitted successfully!',
                    thumbnail_url TEXT DEFAULT NULL,
                    image_url TEXT DEFAULT NULL,
                    footer_text TEXT DEFAULT NULL,
                    created_by TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS registration_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    registration_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    field_type TEXT NOT NULL,
                    required INTEGER NOT NULL DEFAULT 1,
                    placeholder TEXT DEFAULT '',
                    options TEXT DEFAULT '[]',
                    min_length INTEGER DEFAULT NULL,
                    max_length INTEGER DEFAULT NULL,
                    min_value REAL DEFAULT NULL,
                    max_value REAL DEFAULT NULL,
                    position INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(registration_id) REFERENCES registration_configs(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS registration_submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    registration_id INTEGER NOT NULL,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    submitted_at TEXT NOT NULL,
                    reviewed_at TEXT DEFAULT NULL,
                    reviewed_by TEXT DEFAULT NULL,
                    rejection_reason TEXT DEFAULT NULL,
                    staff_message_id TEXT DEFAULT NULL,
                    staff_channel_id TEXT DEFAULT NULL,
                    FOREIGN KEY(registration_id) REFERENCES registration_configs(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS registration_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    submission_id INTEGER NOT NULL,
                    question_id INTEGER NOT NULL,
                    question_text TEXT NOT NULL,
                    field_type TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    FOREIGN KEY(submission_id) REFERENCES registration_submissions(id) ON DELETE CASCADE
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS registration_sessions (
                    session_id TEXT PRIMARY KEY,
                    registration_id INTEGER NOT NULL,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    current_step INTEGER NOT NULL DEFAULT 0,
                    answers_json TEXT NOT NULL DEFAULT '{}',
                    expires_at REAL NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS registration_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    registration_id INTEGER DEFAULT NULL,
                    submission_id INTEGER DEFAULT NULL,
                    event_type TEXT NOT NULL,
                    actor_id TEXT DEFAULT NULL,
                    target_user_id TEXT DEFAULT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------
    def log_event(self, guild_id: str, event_type: str, details: str,
                  registration_id: Optional[int] = None, submission_id: Optional[int] = None,
                  actor_id: Optional[str] = None, target_user_id: Optional[str] = None) -> None:
        now = discord.utils.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO registration_logs (
                    guild_id, registration_id, submission_id, event_type, actor_id, target_user_id, details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(guild_id), registration_id, submission_id, event_type, actor_id, target_user_id, details, now))
            conn.commit()

    def get_logs(self, guild_id: str, limit: int = 50) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("""
                SELECT * FROM registration_logs WHERE guild_id = ? ORDER BY id DESC LIMIT ?
            """, (str(guild_id), limit)).fetchall()

    # -----------------------------------------------------------------------
    # Form Configurations
    # -----------------------------------------------------------------------
    def create_form(self, guild_id: str, name: str, description: str = "", created_by: Optional[str] = None) -> int:
        now = discord.utils.utcnow().isoformat()
        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO registration_configs (
                    guild_id, name, description, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (str(guild_id), name.strip(), description.strip(), created_by, now, now))
            conn.commit()
            new_id = cur.lastrowid
        self.log_event(str(guild_id), "form_created", f"Created form #{new_id} '{name}'", registration_id=new_id, actor_id=created_by)
        return new_id

    def get_form(self, form_id: int) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM registration_configs WHERE id = ?", (form_id,)).fetchone()

    def get_guild_forms(self, guild_id: str) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM registration_configs WHERE guild_id = ? ORDER BY id ASC", (str(guild_id),)).fetchall()

    def update_form(self, form_id: int, **kwargs) -> bool:
        allowed = {
            "name", "description", "channel_id", "panel_message_id", "button_label", "button_emoji",
            "button_style", "enabled", "auto_role_enabled", "add_role_ids", "remove_role_enabled",
            "remove_role_ids", "conditional_roles", "change_nickname_enabled", "nickname_question_id",
            "nickname_format", "approval_mode", "review_channel_id", "log_channel_id",
            "single_submission", "allow_edit", "success_message", "thumbnail_url", "image_url", "footer_text"
        }
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return False
        updates.append("updated_at = ?")
        params.append(discord.utils.utcnow().isoformat())
        params.append(form_id)

        with self._conn() as conn:
            conn.execute(f"UPDATE registration_configs SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        return True

    def delete_form(self, form_id: int) -> bool:
        form = self.get_form(form_id)
        if not form:
            return False
        with self._conn() as conn:
            conn.execute("DELETE FROM registration_configs WHERE id = ?", (form_id,))
            conn.commit()
        self.log_event(form["guild_id"], "form_deleted", f"Deleted form #{form_id} '{form['name']}'", registration_id=form_id)
        return True

    # -----------------------------------------------------------------------
    # Questions
    # -----------------------------------------------------------------------
    def add_question(self, registration_id: int, question: str, field_type: str,
                     required: bool = True, placeholder: str = "", options: List[str] = None,
                     min_length: Optional[int] = None, max_length: Optional[int] = None,
                     min_value: Optional[float] = None, max_value: Optional[float] = None,
                     position: Optional[int] = None) -> int:
        options_json = json.dumps(options or [])
        now = discord.utils.utcnow().isoformat()
        with self._conn() as conn:
            if position is None:
                max_pos = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) as p FROM registration_questions WHERE registration_id = ?",
                    (registration_id,)
                ).fetchone()["p"]
                position = max_pos + 1

            cur = conn.execute("""
                INSERT INTO registration_questions (
                    registration_id, question, field_type, required, placeholder, options,
                    min_length, max_length, min_value, max_value, position, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (registration_id, question.strip(), field_type, 1 if required else 0,
                  placeholder.strip(), options_json, min_length, max_length, min_value, max_value, position, now))
            conn.commit()
            return cur.lastrowid

    def get_questions(self, registration_id: int) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("""
                SELECT * FROM registration_questions WHERE registration_id = ? ORDER BY position ASC, id ASC
            """, (registration_id,)).fetchall()

    def get_question(self, question_id: int) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM registration_questions WHERE id = ?", (question_id,)).fetchone()

    def update_question(self, question_id: int, **kwargs) -> bool:
        allowed = {"question", "field_type", "required", "placeholder", "options", "min_length", "max_length", "min_value", "max_value", "position"}
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return False
        params.append(question_id)
        with self._conn() as conn:
            conn.execute(f"UPDATE registration_questions SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        return True

    def delete_question(self, question_id: int) -> bool:
        with self._conn() as conn:
            conn.execute("DELETE FROM registration_questions WHERE id = ?", (question_id,))
            conn.commit()
        return True

    def reorder_questions(self, registration_id: int, ordered_ids: List[int]) -> None:
        with self._conn() as conn:
            for idx, qid in enumerate(ordered_ids):
                conn.execute("UPDATE registration_questions SET position = ? WHERE id = ? AND registration_id = ?", (idx, qid, registration_id))
            conn.commit()

    # -----------------------------------------------------------------------
    # Submissions & Answers
    # -----------------------------------------------------------------------
    def create_submission(self, registration_id: int, guild_id: str, user_id: str,
                          answers: Dict[int, str], status: str = "pending") -> int:
        now = discord.utils.utcnow().isoformat()
        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO registration_submissions (
                    registration_id, guild_id, user_id, status, submitted_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (registration_id, str(guild_id), str(user_id), status, now))
            submission_id = cur.lastrowid

            questions = {q["id"]: q for q in self.get_questions(registration_id)}
            for q_id, ans in answers.items():
                q_meta = questions.get(int(q_id))
                q_text = q_meta["question"] if q_meta else f"Question #{q_id}"
                f_type = q_meta["field_type"] if q_meta else "short_text"
                conn.execute("""
                    INSERT INTO registration_answers (
                        submission_id, question_id, question_text, field_type, answer
                    ) VALUES (?, ?, ?, ?, ?)
                """, (submission_id, q_id, q_text, f_type, str(ans)))
            conn.commit()

        self.log_event(str(guild_id), "submitted", f"User <@{user_id}> submitted application #{submission_id}",
                       registration_id=registration_id, submission_id=submission_id, target_user_id=str(user_id))
        return submission_id

    def get_submission(self, submission_id: int) -> Optional[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM registration_submissions WHERE id = ?", (submission_id,)).fetchone()

    def get_answers(self, submission_id: int) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM registration_answers WHERE submission_id = ? ORDER BY id ASC", (submission_id,)).fetchall()

    def get_submissions_by_user(self, guild_id: str, user_id: str, registration_id: Optional[int] = None) -> List[sqlite3.Row]:
        with self._conn() as conn:
            if registration_id:
                return conn.execute("""
                    SELECT * FROM registration_submissions 
                    WHERE guild_id = ? AND user_id = ? AND registration_id = ? 
                    ORDER BY id DESC
                """, (str(guild_id), str(user_id), registration_id)).fetchall()
            return conn.execute("""
                SELECT * FROM registration_submissions 
                WHERE guild_id = ? AND user_id = ? 
                ORDER BY id DESC
            """, (str(guild_id), str(user_id))).fetchall()

    def get_submissions(self, registration_id: int, status: Optional[str] = None, limit: int = 100) -> List[sqlite3.Row]:
        with self._conn() as conn:
            if status:
                return conn.execute("""
                    SELECT * FROM registration_submissions 
                    WHERE registration_id = ? AND status = ? 
                    ORDER BY id DESC LIMIT ?
                """, (registration_id, status, limit)).fetchall()
            return conn.execute("""
                SELECT * FROM registration_submissions 
                WHERE registration_id = ? 
                ORDER BY id DESC LIMIT ?
            """, (registration_id, limit)).fetchall()

    def update_submission_status(self, submission_id: int, status: str, reviewed_by: Optional[str] = None,
                                 rejection_reason: Optional[str] = None, staff_message_id: Optional[str] = None,
                                 staff_channel_id: Optional[str] = None) -> bool:
        now = discord.utils.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute("""
                UPDATE registration_submissions 
                SET status = ?, reviewed_at = ?, reviewed_by = ?, rejection_reason = ?,
                    staff_message_id = COALESCE(?, staff_message_id),
                    staff_channel_id = COALESCE(?, staff_channel_id)
                WHERE id = ?
            """, (status, now, reviewed_by, rejection_reason, staff_message_id, staff_channel_id, submission_id))
            conn.commit()
        return True

    # -----------------------------------------------------------------------
    # Active Multi-step Sessions
    # -----------------------------------------------------------------------
    def save_session(self, session_id: str, registration_id: int, guild_id: str, user_id: str,
                     current_step: int, answers: Dict[int, str], ttl_seconds: int = 1800) -> None:
        expires_at = time.time() + ttl_seconds
        answers_json = json.dumps(answers)
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO registration_sessions (
                    session_id, registration_id, guild_id, user_id, current_step, answers_json, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    current_step = excluded.current_step,
                    answers_json = excluded.answers_json,
                    expires_at = excluded.expires_at
            """, (session_id, registration_id, str(guild_id), str(user_id), current_step, answers_json, expires_at))
            conn.commit()

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM registration_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not row:
                return None
            if row["expires_at"] < time.time():
                conn.execute("DELETE FROM registration_sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return None
            return {
                "session_id": row["session_id"],
                "registration_id": row["registration_id"],
                "guild_id": row["guild_id"],
                "user_id": row["user_id"],
                "current_step": row["current_step"],
                "answers": json.loads(row["answers_json"]),
                "expires_at": row["expires_at"]
            }

    def delete_session(self, session_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM registration_sessions WHERE session_id = ?", (session_id,))
            conn.commit()


# Single global database instance
db = RegistrationDatabase()


# ---------------------------------------------------------------------------
# Validation Engine
# ---------------------------------------------------------------------------

class ValidationEngine:
    URL_REGEX = re.compile(
        r'^(?:http|https)://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )

    @classmethod
    def validate_answer(cls, q: sqlite3.Row, raw_val: str) -> Tuple[bool, str, Any]:
        val = (raw_val or "").strip()
        required = bool(q["required"])
        field_type = q["field_type"]

        if not val:
            if required:
                return False, f"**{q['question']}** is required and cannot be left blank.", None
            return True, "", ""

        # Length validations
        if q["min_length"] is not None and len(val) < q["min_length"]:
            return False, f"**{q['question']}** must be at least {q['min_length']} characters (you provided {len(val)}).", None
        if q["max_length"] is not None and len(val) > q["max_length"]:
            return False, f"**{q['question']}** cannot exceed {q['max_length']} characters (you provided {len(val)}).", None

        # Number validation
        if field_type == "number":
            try:
                num = float(val) if "." in val else int(val)
            except ValueError:
                return False, f"**{q['question']}** must be a valid numeric number (e.g. 18).", None
            if q["min_value"] is not None and num < q["min_value"]:
                return False, f"**{q['question']}** cannot be less than {q['min_value']}.", None
            if q["max_value"] is not None and num > q["max_value"]:
                return False, f"**{q['question']}** cannot be greater than {q['max_value']}.", None
            return True, "", str(num)

        # Date validation
        if field_type == "date":
            parsed_date = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
                try:
                    parsed_date = datetime.datetime.strptime(val, fmt)
                    break
                except ValueError:
                    pass
            if not parsed_date:
                return False, f"**{q['question']}** must be a valid date formatted as `YYYY-MM-DD` (e.g. 2000-01-15).", None
            return True, "", parsed_date.strftime("%Y-%m-%d")

        # URL validation
        if field_type == "url":
            if not cls.URL_REGEX.match(val):
                return False, f"**{q['question']}** must be a valid website URL starting with `http://` or `https://`.", None
            return True, "", val

        # Yes / No validation
        if field_type == "yes_no":
            lower = val.lower()
            if lower in ("yes", "y", "true", "1"):
                return True, "", "Yes"
            elif lower in ("no", "n", "false", "0"):
                return True, "", "No"
            return False, f"**{q['question']}** must be either 'Yes' or 'No'.", None

        # Select / Dropdown validation
        if field_type in ("single_select", "multiple_select"):
            try:
                configured_opts = json.loads(q["options"] or "[]")
            except Exception:
                configured_opts = []
            if configured_opts:
                if field_type == "single_select":
                    if val not in configured_opts:
                        return False, f"Invalid choice for **{q['question']}**. Must be one of: {', '.join(configured_opts)}", None
                elif field_type == "multiple_select":
                    selected = [s.strip() for s in val.split(",") if s.strip()]
                    invalid = [s for s in selected if s not in configured_opts]
                    if invalid:
                        return False, f"Invalid options selected for **{q['question']}**: {', '.join(invalid)}.", None
            return True, "", val

        return True, "", val


# ---------------------------------------------------------------------------
# Post-Registration Automation Engine
# ---------------------------------------------------------------------------

async def execute_post_registration_actions(bot: commands.Bot, guild: discord.Guild,
                                           member: discord.Member, config: sqlite3.Row,
                                           answers: Dict[int, str]) -> List[str]:
    """
    Executes post-registration actions:
      1. Multi-role assignment (add_role_ids)
      2. Multi-role removal (remove_role_ids)
      3. Conditional role assignments based on choices
      4. Server Nickname / Name change from selected question answer
    """
    logs = []
    bot_member = guild.me

    can_manage_roles = bot_member.guild_permissions.manage_roles
    can_manage_nick = bot_member.guild_permissions.manage_nicknames

    # 1. Nickname Automation
    if config["change_nickname_enabled"] and config["nickname_question_id"] and can_manage_nick:
        q_id = int(config["nickname_question_id"])
        target_val = str(answers.get(q_id, answers.get(str(q_id), ""))).strip()
        if target_val:
            fmt = config["nickname_format"] or "{name}"
            new_nick = fmt.replace("{name}", target_val)[:32]
            if member.top_role >= bot_member.top_role and guild.owner_id != bot.user.id:
                logs.append(f"⚠️ Cannot change nickname for {member.mention} (Target role higher or equal to bot role).")
            elif member.id == guild.owner_id:
                logs.append(f"⚠️ Cannot change nickname for server owner {member.mention}.")
            else:
                try:
                    await member.edit(nick=new_nick, reason=f"{BOT_NAME} Registration approval: {config['name']}")
                    logs.append(f"🏷️ Updated nickname for {member.mention} to `{new_nick}`")
                    db.log_event(str(guild.id), "nickname_updated", f"Updated nickname of {member} to '{new_nick}'",
                                 registration_id=config["id"], target_user_id=str(member.id))
                except Exception as e:
                    logs.append(f"❌ Nickname change failed for {member.mention}: {e}")

    # 2. Add Roles
    if config["auto_role_enabled"] and can_manage_roles:
        try:
            add_ids = json.loads(config["add_role_ids"] or "[]")
        except Exception:
            add_ids = []
        
        roles_to_add = []
        for rid in add_ids:
            try:
                role = guild.get_role(int(rid))
                if role and role < bot_member.top_role:
                    roles_to_add.append(role)
            except Exception:
                pass

        # 3. Conditional Roles
        try:
            cond_map = json.loads(config["conditional_roles"] or "{}")
        except Exception:
            cond_map = {}

        for q_id, ans in answers.items():
            key = f"{q_id}:{ans}"
            if key in cond_map:
                try:
                    c_role = guild.get_role(int(cond_map[key]))
                    if c_role and c_role < bot_member.top_role and c_role not in roles_to_add:
                        roles_to_add.append(c_role)
                except Exception:
                    pass

        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason=f"{BOT_NAME} Registration approval: {config['name']}")
                role_names = ", ".join(r.name for r in roles_to_add)
                logs.append(f"🛡️ Granted roles: **{role_names}** to {member.mention}")
                db.log_event(str(guild.id), "roles_updated", f"Added roles [{role_names}] to {member}",
                             registration_id=config["id"], target_user_id=str(member.id))
            except Exception as e:
                logs.append(f"❌ Role assignment failed: {e}")

    # 4. Remove Roles
    if config["remove_role_enabled"] and can_manage_roles:
        try:
            rem_ids = json.loads(config["remove_role_ids"] or "[]")
        except Exception:
            rem_ids = []

        roles_to_remove = []
        for rid in rem_ids:
            try:
                role = guild.get_role(int(rid))
                if role and role in member.roles and role < bot_member.top_role:
                    roles_to_remove.append(role)
            except Exception:
                pass

        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=f"{BOT_NAME} Registration approval: {config['name']}")
                role_names = ", ".join(r.name for r in roles_to_remove)
                logs.append(f"🗑️ Removed roles: **{role_names}** from {member.mention}")
                db.log_event(str(guild.id), "roles_updated", f"Removed roles [{role_names}] from {member}",
                             registration_id=config["id"], target_user_id=str(member.id))
            except Exception as e:
                logs.append(f"❌ Role removal failed: {e}")

    # Send logs to log_channel if configured
    if config["log_channel_id"]:
        try:
            log_chan = guild.get_channel(int(config["log_channel_id"]))
            if log_chan and logs:
                embed = discord.Embed(
                    title=f"⚡ {BOT_NAME} Registration Automations Executed",
                    description="\n".join(logs),
                    color=C.SUCCESS,
                    timestamp=discord.utils.utcnow()
                )
                embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
                embed.set_footer(text=f"Form: {config['name']} • User ID: {member.id}")
                await log_chan.send(embed=embed)
        except Exception:
            pass

    return logs


# ---------------------------------------------------------------------------
# Persistent Registration Panel View
# ---------------------------------------------------------------------------

class RegistrationPublicView(discord.ui.View):
    """
    Persistent view registered on published channel panels.
    Button custom_id format: 'jade:reg:start:<form_id>'
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Register", style=discord.ButtonStyle.primary, custom_id="jade:reg:start:default", emoji="📝")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        custom_id = interaction.data.get("custom_id", "")
        parts = custom_id.split(":")
        if len(parts) >= 4:
            try:
                form_id = int(parts[3])
                await handle_start_registration(interaction, form_id)
                return
            except ValueError:
                pass
        await interaction.response.send_message(embed=embed_error("Error", "Invalid registration form identifier."), ephemeral=True)


def build_panel_view(config: sqlite3.Row) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    style = BUTTON_STYLES.get(config["button_style"], discord.ButtonStyle.primary)
    custom_id = f"jade:reg:start:{config['id']}"
    emoji = config["button_emoji"] if config["button_emoji"] else "📝"
    button = discord.ui.Button(
        label=config["button_label"] or "Register",
        style=style,
        emoji=emoji,
        custom_id=custom_id
    )
    view.add_item(button)
    return view


# ---------------------------------------------------------------------------
# Persistent Staff Review View
# ---------------------------------------------------------------------------

class RegistrationStaffReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅", custom_id="jade:reg:appr:default")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_staff_action(interaction, "approve")

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌", custom_id="jade:reg:rejt:default")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_staff_action(interaction, "reject")

    @discord.ui.button(label="View Full Registration", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="jade:reg:view:default")
    async def view_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await handle_staff_action(interaction, "view")


async def handle_staff_action(interaction: discord.Interaction, action: str) -> None:
    custom_id = interaction.data.get("custom_id", "")
    parts = custom_id.split(":")
    if len(parts) < 4:
        await interaction.response.send_message(embed=embed_error("Error", "Invalid submission ID."), ephemeral=True)
        return
    try:
        sub_id = int(parts[3])
    except ValueError:
        await interaction.response.send_message(embed=embed_error("Error", "Malformed submission ID."), ephemeral=True)
        return

    if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(embed=embed_error("Permission Denied", "Only server staff with Manage Server permissions can review registrations."), ephemeral=True)
        return

    sub = db.get_submission(sub_id)
    if not sub:
        await interaction.response.send_message(embed=embed_error("Not Found", "This submission no longer exists."), ephemeral=True)
        return

    config = db.get_form(sub["registration_id"])
    guild = interaction.guild
    member = guild.get_member(int(sub["user_id"])) if guild else None

    if action == "view":
        answers = db.get_answers(sub_id)
        embed = discord.Embed(
            title=f"📋 Full Registration Details — #{sub_id}",
            description=f"**Applicant:** <@{sub['user_id']}> ({sub['user_id']})\n**Form:** {config['name'] if config else 'Unknown'}\n**Status:** `{sub['status'].upper()}`\n**Submitted:** {fmt_ts(datetime.datetime.fromisoformat(sub['submitted_at']))}",
            color=C.BRAND
        )
        for ans in answers:
            val = ans["answer"] if ans["answer"] else "*No answer provided*"
            embed.add_field(name=f"❓ {ans['question_text']}", value=val[:1024], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if sub["status"] != "pending":
        await interaction.response.send_message(embed=embed_warning("Already Processed", f"This application has already been marked as **{sub['status'].upper()}** by <@{sub['reviewed_by']}>."), ephemeral=True)
        return

    if action == "approve":
        await interaction.response.defer(ephemeral=True)
        db.update_submission_status(sub_id, "approved", reviewed_by=str(interaction.user.id))
        
        answers_dict = {a["question_id"]: a["answer"] for a in db.get_answers(sub_id)}
        action_logs = []
        if member and config:
            action_logs = await execute_post_registration_actions(interaction.client, guild, member, config, answers_dict)

        if member:
            try:
                dm_embed = discord.Embed(
                    title=f"🎉 Registration Approved — {guild.name}",
                    description=f"Your registration for **{config['name']}** has been accepted by our staff team!\n\nWelcome aboard.",
                    color=C.SUCCESS
                )
                await member.send(embed=dm_embed)
            except Exception:
                pass

        try:
            orig_embed = interaction.message.embeds[0]
            orig_embed.color = C.SUCCESS
            orig_embed.set_field_at(
                0,
                name="Status",
                value=f"✅ **Approved** by {interaction.user.mention} ({fmt_rel(discord.utils.utcnow())})",
                inline=True
            )
            disabled_view = discord.ui.View()
            view_full_btn = discord.ui.Button(label="View Full Registration", style=discord.ButtonStyle.secondary, emoji="📋", custom_id=f"jade:reg:view:{sub_id}")
            disabled_view.add_item(view_full_btn)
            await interaction.message.edit(embed=orig_embed, view=disabled_view)
        except Exception:
            pass

        log_summary = ("\n" + "\n".join(action_logs)) if action_logs else ""
        db.log_event(str(guild.id), "approved", f"Staff {interaction.user} approved submission #{sub_id} for <@{sub['user_id']}>{log_summary}",
                     registration_id=sub["registration_id"], submission_id=sub_id, actor_id=str(interaction.user.id), target_user_id=sub["user_id"])

        await interaction.followup.send(embed=embed_success("Approved", f"Submission #{sub_id} for <@{sub['user_id']}> has been approved successfully.{log_summary}"), ephemeral=True)

    elif action == "reject":
        class RejectionModal(discord.ui.Modal, title=f"Reject Registration #{sub_id}"):
            reason = discord.ui.TextInput(
                label="Rejection Reason",
                style=discord.TextStyle.paragraph,
                placeholder="Explain why this application is being rejected...",
                required=False,
                max_length=500
            )

            async def on_submit(self, modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(ephemeral=True)
                rej_reason = self.reason.value.strip() or "No specific reason provided."
                db.update_submission_status(sub_id, "rejected", reviewed_by=str(modal_interaction.user.id), rejection_reason=rej_reason)

                if member:
                    try:
                        dm_embed = discord.Embed(
                            title=f"❌ Registration Update — {guild.name}",
                            description=f"Your registration for **{config['name']}** was not approved.\n\n**Reason Provided:**\n> {rej_reason}",
                            color=C.DANGER
                        )
                        await member.send(embed=dm_embed)
                    except Exception:
                        pass

                try:
                    orig_embed = interaction.message.embeds[0]
                    orig_embed.color = C.DANGER
                    orig_embed.set_field_at(
                        0,
                        name="Status",
                        value=f"❌ **Rejected** by {modal_interaction.user.mention} ({fmt_rel(discord.utils.utcnow())})\n**Reason:** {rej_reason}",
                        inline=False
                    )
                    disabled_view = discord.ui.View()
                    view_full_btn = discord.ui.Button(label="View Full Registration", style=discord.ButtonStyle.secondary, emoji="📋", custom_id=f"jade:reg:view:{sub_id}")
                    disabled_view.add_item(view_full_btn)
                    await interaction.message.edit(embed=orig_embed, view=disabled_view)
                except Exception:
                    pass

                db.log_event(str(guild.id), "rejected", f"Staff {modal_interaction.user} rejected submission #{sub_id} for <@{sub['user_id']}>. Reason: {rej_reason}",
                             registration_id=sub["registration_id"], submission_id=sub_id, actor_id=str(modal_interaction.user.id), target_user_id=sub["user_id"])

                await modal_interaction.followup.send(embed=embed_warning("Registration Rejected", f"Submission #{sub_id} was rejected.\n**Reason:** {rej_reason}"), ephemeral=True)

        await interaction.response.send_modal(RejectionModal())


# ---------------------------------------------------------------------------
# Multi-Step Dynamic Registration Runner
# ---------------------------------------------------------------------------

TEXT_BASED_TYPES = {"short_text", "paragraph", "number", "date", "url"}
COMPONENT_BASED_TYPES = {"yes_no", "single_select", "multiple_select", "user_select", "role_select", "channel_select"}

def partition_questions(questions: List[sqlite3.Row]) -> List[List[sqlite3.Row]]:
    steps: List[List[sqlite3.Row]] = []
    current_text_batch: List[sqlite3.Row] = []

    for q in questions:
        f_type = q["field_type"]
        if f_type in TEXT_BASED_TYPES:
            current_text_batch.append(q)
            if len(current_text_batch) == 5:
                steps.append(current_text_batch)
                current_text_batch = []
        else:
            if current_text_batch:
                steps.append(current_text_batch)
                current_text_batch = []
            steps.append([q])

    if current_text_batch:
        steps.append(current_text_batch)

    return steps if steps else [[]]


async def handle_start_registration(interaction: discord.Interaction, form_id: int) -> None:
    config = db.get_form(form_id)
    if not config or not config["enabled"]:
        await interaction.response.send_message(embed=embed_error("Registration Unavailable", "This registration form is currently disabled or has been removed."), ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    user_id = str(interaction.user.id)

    if config["single_submission"]:
        existing = db.get_submissions_by_user(guild_id, user_id, form_id)
        active = [s for s in existing if s["status"] in ("pending", "approved")]
        if active:
            st = active[0]["status"].upper()
            await interaction.response.send_message(
                embed=embed_warning("Already Registered", f"You already have an active registration for **{config['name']}** (Status: `{st}`).\nSingle submissions only are permitted for this form."),
                ephemeral=True
            )
            return

    questions = db.get_questions(form_id)
    if not questions:
        await interaction.response.send_message(embed=embed_warning("No Questions", "This registration form has not configured any questions yet. Please contact staff."), ephemeral=True)
        return

    session_id = str(uuid.uuid4())
    steps = partition_questions(questions)
    first_step = steps[0]

    if first_step and all(q["field_type"] in TEXT_BASED_TYPES for q in first_step):
        db.save_session(session_id, form_id, guild_id, user_id, current_step=0, answers={})
        modal = DynamicChunkModal(session_id, form_id, 0, len(steps), first_step)
        await interaction.response.send_modal(modal)
    else:
        db.save_session(session_id, form_id, guild_id, user_id, current_step=0, answers={})
        await send_step_interactive_message(interaction, session_id, form_id, 0, steps)


class DynamicChunkModal(discord.ui.Modal):
    def __init__(self, session_id: str, form_id: int, step_idx: int, total_steps: int, questions: List[sqlite3.Row]):
        title = f"Registration — Step {step_idx + 1}/{total_steps}"[:45]
        super().__init__(title=title)
        self.session_id = session_id
        self.form_id = form_id
        self.step_idx = step_idx
        self.total_steps = total_steps
        self.questions = questions
        self.inputs: Dict[int, discord.ui.TextInput] = {}

        for q in questions:
            style = discord.TextStyle.paragraph if q["field_type"] == "paragraph" else discord.TextStyle.short
            txt_in = discord.ui.TextInput(
                label=q["question"][:45],
                style=style,
                placeholder=q["placeholder"][:100] if q["placeholder"] else None,
                required=bool(q["required"]),
                min_length=q["min_length"] if q["min_length"] else None,
                max_length=q["max_length"] if q["max_length"] else 4000
            )
            self.inputs[q["id"]] = txt_in
            self.add_item(txt_in)

    async def on_submit(self, interaction: discord.Interaction):
        session = db.get_session(self.session_id)
        if not session:
            await interaction.response.send_message(embed=embed_error("Session Expired", "Your registration session timed out. Please click Register again."), ephemeral=True)
            return

        answers = session["answers"]
        for q in self.questions:
            val = self.inputs[q["id"]].value.strip()
            valid, err_msg, clean_val = ValidationEngine.validate_answer(q, val)
            if not valid:
                await interaction.response.send_message(embed=embed_error("Validation Error", err_msg), ephemeral=True)
                return
            answers[str(q["id"])] = clean_val

        next_step = self.step_idx + 1
        db.save_session(self.session_id, self.form_id, session["guild_id"], session["user_id"], next_step, answers)

        all_questions = db.get_questions(self.form_id)
        steps = partition_questions(all_questions)

        if next_step >= len(steps):
            await show_review_confirmation(interaction, self.session_id, self.form_id)
        else:
            await send_step_interactive_message(interaction, self.session_id, self.form_id, next_step, steps)


async def send_step_interactive_message(interaction: discord.Interaction, session_id: str,
                                       form_id: int, step_idx: int, steps: List[List[sqlite3.Row]]) -> None:
    step_questions = steps[step_idx]
    config = db.get_form(form_id)
    total_steps = len(steps)

    embed = discord.Embed(
        title=f"📝 {config['name']} — Part {step_idx + 1}/{total_steps}",
        description="Please answer the questions for this section below.",
        color=C.BRAND
    )

    view = StepInteractiveView(session_id, form_id, step_idx, steps)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    else:
        if interaction.type == discord.InteractionType.component:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class StepInteractiveView(discord.ui.View):
    def __init__(self, session_id: str, form_id: int, step_idx: int, steps: List[List[sqlite3.Row]]):
        super().__init__(timeout=600)
        self.session_id = session_id
        self.form_id = form_id
        self.step_idx = step_idx
        self.steps = steps
        self.temp_answers: Dict[str, str] = {}

        current_questions = steps[step_idx]

        if current_questions and all(q["field_type"] in TEXT_BASED_TYPES for q in current_questions):
            open_modal_btn = discord.ui.Button(label=f"Fill Text Fields (Part {step_idx + 1})", style=discord.ButtonStyle.primary, emoji="✍️")
            async def open_modal_cb(btn_inter: discord.Interaction):
                modal = DynamicChunkModal(session_id, form_id, step_idx, len(steps), current_questions)
                await btn_inter.response.send_modal(modal)
            open_modal_btn.callback = open_modal_cb
            self.add_item(open_modal_btn)
            return

        for q in current_questions:
            f_type = q["field_type"]
            q_id = str(q["id"])

            if f_type == "yes_no":
                yes_btn = discord.ui.Button(label="Yes", style=discord.ButtonStyle.success, emoji="✅")
                no_btn = discord.ui.Button(label="No", style=discord.ButtonStyle.danger, emoji="❌")

                def bind_yes_no(target_id: str):
                    async def on_yes(btn_inter: discord.Interaction):
                        self.temp_answers[target_id] = "Yes"
                        await self.advance(btn_inter)
                    async def on_no(btn_inter: discord.Interaction):
                        self.temp_answers[target_id] = "No"
                        await self.advance(btn_inter)
                    return on_yes, on_no

                cb_y, cb_n = bind_yes_no(q_id)
                yes_btn.callback = cb_y
                no_btn.callback = cb_n
                self.add_item(yes_btn)
                self.add_item(no_btn)

            elif f_type in ("single_select", "multiple_select"):
                try:
                    opts = json.loads(q["options"] or "[]")
                except Exception:
                    opts = []
                if not opts:
                    opts = ["Default"]

                chunk_size = 25
                opt_chunks = [opts[i:i + chunk_size] for i in range(0, len(opts), chunk_size)]

                for c_idx, chunk in enumerate(opt_chunks):
                    select_options = [discord.SelectOption(label=opt[:100], value=opt[:100]) for opt in chunk]
                    max_vals = len(select_options) if f_type == "multiple_select" else 1
                    label_suffix = f" (Part {c_idx+1})" if len(opt_chunks) > 1 else ""
                    placeholder = f"{q['question']}{label_suffix}"[:100]

                    select_menu = discord.ui.Select(
                        placeholder=placeholder,
                        min_values=1 if (q["required"] and len(opt_chunks) == 1) else 0,
                        max_values=max_vals,
                        options=select_options
                    )
                    def bind_select(target_id: str, s_menu: discord.ui.Select):
                        async def select_cb(sel_inter: discord.Interaction):
                            self.temp_answers[target_id] = ", ".join(s_menu.values)
                            await self.advance(sel_inter)
                        return select_cb
                    select_menu.callback = bind_select(q_id, select_menu)
                    self.add_item(select_menu)

            elif f_type == "user_select":
                user_select = discord.ui.UserSelect(placeholder=q["question"][:100], min_values=1 if q["required"] else 0, max_values=1)
                def bind_user(target_id: str):
                    async def user_cb(u_inter: discord.Interaction):
                        selected = user_select.values[0] if user_select.values else None
                        self.temp_answers[target_id] = f"<@{selected.id}>" if selected else ""
                        await self.advance(u_inter)
                    return user_cb
                user_select.callback = bind_user(q_id)
                self.add_item(user_select)

            elif f_type == "role_select":
                role_select = discord.ui.RoleSelect(placeholder=q["question"][:100], min_values=1 if q["required"] else 0, max_values=1)
                def bind_role(target_id: str):
                    async def role_cb(r_inter: discord.Interaction):
                        selected = role_select.values[0] if role_select.values else None
                        self.temp_answers[target_id] = f"<@&{selected.id}>" if selected else ""
                        await self.advance(r_inter)
                    return role_cb
                role_select.callback = bind_role(q_id)
                self.add_item(role_select)

            elif f_type == "channel_select":
                chan_select = discord.ui.ChannelSelect(placeholder=q["question"][:100], min_values=1 if q["required"] else 0, max_values=1)
                def bind_chan(target_id: str):
                    async def chan_cb(c_inter: discord.Interaction):
                        selected = chan_select.values[0] if chan_select.values else None
                        self.temp_answers[target_id] = f"<#{selected.id}>" if selected else ""
                        await self.advance(c_inter)
                    return chan_cb
                chan_select.callback = bind_chan(q_id)
                self.add_item(chan_select)

    async def advance(self, interaction: discord.Interaction):
        session = db.get_session(self.session_id)
        if not session:
            await interaction.response.send_message(embed=embed_error("Session Expired", "Session timed out."), ephemeral=True)
            return
        answers = session["answers"]
        answers.update(self.temp_answers)

        next_step = self.step_idx + 1
        db.save_session(self.session_id, self.form_id, session["guild_id"], session["user_id"], next_step, answers)

        if next_step >= len(self.steps):
            await show_review_confirmation(interaction, self.session_id, self.form_id)
        else:
            await send_step_interactive_message(interaction, self.session_id, self.form_id, next_step, self.steps)


# ---------------------------------------------------------------------------
# Final Review & Submission Workflow
# ---------------------------------------------------------------------------

async def show_review_confirmation(interaction: discord.Interaction, session_id: str, form_id: int) -> None:
    session = db.get_session(session_id)
    if not session:
        await interaction.response.send_message(embed=embed_error("Session Expired", "Registration session expired."), ephemeral=True)
        return

    config = db.get_form(form_id)
    questions = db.get_questions(form_id)
    answers = session["answers"]

    embed = discord.Embed(
        title=f"📋 Review Your Registration — {config['name']}",
        description="Please review your answers before submitting.\nClick **Submit Registration** below to finalize.",
        color=C.BRAND
    )

    for q in questions:
        q_id = str(q["id"])
        ans = answers.get(q_id, "*Not provided*")
        embed.add_field(name=f"❓ {q['question']}", value=str(ans)[:1024] or "*Empty*", inline=False)

    view = ReviewConfirmationView(session_id, form_id)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    else:
        if interaction.type == discord.InteractionType.component:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ReviewConfirmationView(discord.ui.View):
    def __init__(self, session_id: str, form_id: int):
        super().__init__(timeout=600)
        self.session_id = session_id
        self.form_id = form_id

    @discord.ui.button(label="Submit Registration", style=discord.ButtonStyle.success, emoji="✅")
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        session = db.get_session(self.session_id)
        if not session:
            await interaction.followup.send(embed=embed_error("Session Expired", "Your session timed out. Please start over."), ephemeral=True)
            return

        config = db.get_form(self.form_id)
        guild = interaction.guild
        member = interaction.user
        answers = session["answers"]
        approval_mode = config["approval_mode"]

        if config["single_submission"]:
            existing = db.get_submissions_by_user(str(guild.id), str(member.id), self.form_id)
            if any(s["status"] in ("pending", "approved") for s in existing):
                await interaction.followup.send(embed=embed_warning("Already Submitted", "You already have a submitted application."), ephemeral=True)
                db.delete_session(self.session_id)
                return

        initial_status = "approved" if approval_mode == "automatic" else "pending"
        sub_id = db.create_submission(self.form_id, str(guild.id), str(member.id), answers, status=initial_status)
        db.delete_session(self.session_id)

        action_logs = []
        if initial_status == "approved":
            db.update_submission_status(sub_id, "approved", reviewed_by="Automatic System")
            action_logs = await execute_post_registration_actions(interaction.client, guild, member, config, answers)

            succ_msg = config["success_message"] or "Your registration has been submitted and approved!"
            embed = discord.Embed(title="✅ Registration Complete", description=succ_msg, color=C.SUCCESS)
            if action_logs:
                embed.add_field(name="Automations", value="\n".join(action_logs), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Staff Review workflow
        review_chan_id = config["review_channel_id"]
        staff_channel = guild.get_channel(int(review_chan_id)) if review_chan_id else None

        if staff_channel:
            review_embed = discord.Embed(
                title=f"📥 New Registration Application — #{sub_id}",
                description=f"**Applicant:** {member.mention} (`{member.id}`)\n**Registration:** {config['name']}\n**Mode:** `Staff Review`",
                color=C.WARNING,
                timestamp=discord.utils.utcnow()
            )
            review_embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            review_embed.add_field(name="Status", value="🟡 **Pending Review**", inline=True)
            review_embed.add_field(name="Submitted", value=fmt_ts(discord.utils.utcnow()), inline=True)

            all_questions = db.get_questions(self.form_id)
            for q in all_questions:
                ans_str = answers.get(str(q["id"]), "*No answer provided*")
                review_embed.add_field(name=f"❓ {q['question']}", value=str(ans_str)[:1024], inline=False)

            review_view = discord.ui.View(timeout=None)
            review_view.add_item(discord.ui.Button(label="Approve", style=discord.ButtonStyle.success, emoji="✅", custom_id=f"jade:reg:appr:{sub_id}"))
            review_view.add_item(discord.ui.Button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌", custom_id=f"jade:reg:rejt:{sub_id}"))
            review_view.add_item(discord.ui.Button(label="View Full Registration", style=discord.ButtonStyle.secondary, emoji="📋", custom_id=f"jade:reg:view:{sub_id}"))

            staff_msg = await staff_channel.send(embed=review_embed, view=review_view)
            db.update_submission_status(sub_id, "pending", staff_message_id=str(staff_msg.id), staff_channel_id=str(staff_channel.id))

        succ_msg = config["success_message"] or "Your registration has been received and is currently under review by our staff team."
        await interaction.followup.send(embed=embed_success("Registration Submitted", succ_msg), ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        db.delete_session(self.session_id)
        await interaction.response.send_message(embed=embed_info("Cancelled", "Registration process has been cancelled."), ephemeral=True)


# ---------------------------------------------------------------------------
# Admin Discord Command Interface (/registration)
# ---------------------------------------------------------------------------

class RegistrationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = db

    async def cog_load(self) -> None:
        self.bot.add_view(RegistrationPublicView())
        self.bot.add_view(RegistrationStaffReviewView())
        try:
            with self.db._conn() as conn:
                forms = conn.execute("SELECT * FROM registration_configs").fetchall()
                for f in forms:
                    self.bot.add_view(build_panel_view(f))
            print(f"📝 [Registration] Registered {len(forms)} persistent panel views")
        except Exception as e:
            print(f"[Registration] Warning registering form views: {e}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """
        Universal fallback handler for registration button clicks:
          • 'jade:reg:start:<form_id>'
          • 'jade:reg:appr:<sub_id>'
          • 'jade:reg:rejt:<sub_id>'
          • 'jade:reg:view:<sub_id>'
        Ensures buttons always respond immediately even if published after bot start.
        """
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id:
            return

        if custom_id.startswith("jade:reg:start:") or custom_id.startswith("registration:start:"):
            try:
                parts = custom_id.split(":")
                form_id = int(parts[-1])
                await handle_start_registration(interaction, form_id)
            except discord.InteractionResponded:
                pass
            except Exception as e:
                print(f"[Registration] Error in start handler: {e}")
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(embed=embed_error("Error", f"Failed to start registration: {e}"), ephemeral=True)
                except Exception:
                    pass

        elif custom_id.startswith("jade:reg:appr:") or custom_id.startswith("registration:appr:"):
            try:
                await handle_staff_action(interaction, "approve")
            except discord.InteractionResponded:
                pass
            except Exception as e:
                print(f"[Registration] Error in approve handler: {e}")

        elif custom_id.startswith("jade:reg:rejt:") or custom_id.startswith("registration:rejt:"):
            try:
                await handle_staff_action(interaction, "reject")
            except discord.InteractionResponded:
                pass
            except Exception as e:
                print(f"[Registration] Error in reject handler: {e}")

        elif custom_id.startswith("jade:reg:view:") or custom_id.startswith("registration:view:"):
            try:
                await handle_staff_action(interaction, "view")
            except discord.InteractionResponded:
                pass
            except Exception as e:
                print(f"[Registration] Error in view handler: {e}")

    reg_group = app_commands.Group(name="registration", description=f"Configure and manage {BOT_NAME} registration forms")

    @reg_group.command(name="create", description="Create a new registration form and open the interactive builder")
    @app_commands.describe(name="Name of the registration form (e.g. Server Registration, Police Application)")
    @app_commands.default_permissions(manage_guild=True)
    async def reg_create(self, interaction: discord.Interaction, name: str):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(embed=embed_error("Permission Denied", "You need Manage Server permissions to configure registration."), ephemeral=True)
            return

        form_id = self.db.create_form(str(interaction.guild_id), name=name, created_by=str(interaction.user.id))
        embed, view = self.build_admin_builder_panel(form_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @reg_group.command(name="panel", description="Publish or re-publish a registration form panel to a channel")
    @app_commands.describe(
        form_id="ID of the registration form",
        channel="Channel where the registration panel should be sent"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def reg_panel(self, interaction: discord.Interaction, form_id: int, channel: discord.TextChannel):
        config = self.db.get_form(form_id)
        if not config or config["guild_id"] != str(interaction.guild_id):
            await interaction.response.send_message(embed=embed_error("Not Found", f"Form #{form_id} does not exist."), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📝 {config['name']}",
            description=config["description"] or "Welcome to our registration system.\nClick the button below to begin your registration.\nYour submission will be processed by our team.",
            color=C.BRAND
        )
        if config["thumbnail_url"]:
            embed.set_thumbnail(url=config["thumbnail_url"])
        if config["image_url"]:
            embed.set_image(url=config["image_url"])
        embed.set_footer(text=config["footer_text"] or f"{BOT_NAME} Dynamic Registration System")

        view = build_panel_view(config)
        msg = await channel.send(embed=embed, view=view)

        self.db.update_form(form_id, channel_id=str(channel.id), panel_message_id=str(msg.id))
        self.bot.add_view(view)

        await interaction.response.send_message(
            embed=embed_success("Panel Published", f"Registration panel for **{config['name']}** published to {channel.mention}!\n[Jump to Message]({msg.jump_url})"),
            ephemeral=True
        )

    @reg_group.command(name="questions", description="Add, edit, or reorder questions for a registration form")
    @app_commands.describe(form_id="ID of the registration form")
    @app_commands.default_permissions(manage_guild=True)
    async def reg_questions(self, interaction: discord.Interaction, form_id: int):
        config = self.db.get_form(form_id)
        if not config or config["guild_id"] != str(interaction.guild_id):
            await interaction.response.send_message(embed=embed_error("Not Found", f"Form #{form_id} does not exist."), ephemeral=True)
            return

        embed, view = self.build_questions_panel(form_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @reg_group.command(name="config", description="Configure automation, roles, approval mode, and channels for a form")
    @app_commands.describe(form_id="ID of the registration form")
    @app_commands.default_permissions(manage_guild=True)
    async def reg_config(self, interaction: discord.Interaction, form_id: int):
        config = self.db.get_form(form_id)
        if not config or config["guild_id"] != str(interaction.guild_id):
            await interaction.response.send_message(embed=embed_error("Not Found", f"Form #{form_id} does not exist."), ephemeral=True)
            return

        embed, view = self.build_config_panel(form_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @reg_group.command(name="logs", description="View recent registration audit and activity logs")
    @app_commands.describe(limit="Number of log entries to retrieve (max 50)")
    @app_commands.default_permissions(manage_guild=True)
    async def reg_logs(self, interaction: discord.Interaction, limit: Optional[int] = 20):
        logs = self.db.get_logs(str(interaction.guild_id), limit=min(limit or 20, 50))
        if not logs:
            await interaction.response.send_message(embed=embed_info("Registration Logs", "No registration logs recorded yet."), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📜 {BOT_NAME} Registration Audit Logs",
            description=f"Showing last {len(logs)} activity events:",
            color=C.BRAND
        )
        for log in logs[:15]:
            ts = fmt_ts(datetime.datetime.fromisoformat(log["created_at"]))
            embed.add_field(
                name=f"`{log['event_type'].upper()}` • {ts}",
                value=log["details"][:1024],
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reg_group.command(name="submissions", description="View and manage recent applications for a form")
    @app_commands.describe(
        form_id="ID of the registration form",
        status="Filter by status (pending, approved, rejected)"
    )
    @app_commands.choices(status=[
        app_commands.Choice(name="🟡 Pending", value="pending"),
        app_commands.Choice(name="✅ Approved", value="approved"),
        app_commands.Choice(name="❌ Rejected", value="rejected"),
        app_commands.Choice(name="All Submissions", value="all")
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def reg_submissions(self, interaction: discord.Interaction, form_id: int, status: Optional[str] = "all"):
        config = self.db.get_form(form_id)
        if not config or config["guild_id"] != str(interaction.guild_id):
            await interaction.response.send_message(embed=embed_error("Not Found", f"Form #{form_id} does not exist."), ephemeral=True)
            return

        filter_status = None if status == "all" else status
        subs = self.db.get_submissions(form_id, status=filter_status, limit=25)

        if not subs:
            await interaction.response.send_message(embed=embed_info("Submissions", f"No submissions found for **{config['name']}** (Filter: `{status}`)."), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📊 Submissions for {config['name']} ({len(subs)} found)",
            color=C.BRAND
        )
        for sub in subs[:10]:
            icon = "🟡" if sub["status"] == "pending" else ("✅" if sub["status"] == "approved" else "❌")
            ts = fmt_ts(datetime.datetime.fromisoformat(sub["submitted_at"]))
            embed.add_field(
                name=f"{icon} #{sub['id']} — <@{sub['user_id']}>",
                value=f"**Status:** `{sub['status'].upper()}` • **Submitted:** {ts}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reg_group.command(name="delete", description="Permanently delete a registration form")
    @app_commands.describe(form_id="ID of the form to delete")
    @app_commands.default_permissions(manage_guild=True)
    async def reg_delete(self, interaction: discord.Interaction, form_id: int):
        config = self.db.get_form(form_id)
        if not config or config["guild_id"] != str(interaction.guild_id):
            await interaction.response.send_message(embed=embed_error("Not Found", f"Form #{form_id} does not exist."), ephemeral=True)
            return

        self.db.delete_form(form_id)
        await interaction.response.send_message(embed=embed_success("Form Deleted", f"Registration form **{config['name']}** (#{form_id}) and all associated submissions have been removed."), ephemeral=True)

    # -----------------------------------------------------------------------
    # Member Commands
    # -----------------------------------------------------------------------
    @reg_group.command(name="status", description="Check the status of your registration applications")
    async def reg_status(self, interaction: discord.Interaction):
        subs = self.db.get_submissions_by_user(str(interaction.guild_id), str(interaction.user.id))
        if not subs:
            await interaction.response.send_message(embed=embed_info("No Registrations", "You do not have any submitted registrations in this server."), ephemeral=True)
            return

        embed = discord.Embed(title="📝 Your Registration Status", color=C.BRAND)
        for sub in subs[:5]:
            config = self.db.get_form(sub["registration_id"])
            form_name = config["name"] if config else f"Form #{sub['registration_id']}"
            icon = "🟡" if sub["status"] == "pending" else ("✅" if sub["status"] == "approved" else "❌")
            ts = fmt_ts(datetime.datetime.fromisoformat(sub["submitted_at"]))
            val = f"**Status:** {icon} `{sub['status'].upper()}`\n**Submitted:** {ts}"
            if sub["rejection_reason"]:
                val += f"\n**Reason:** {sub['rejection_reason']}"
            embed.add_field(name=f"#{sub['id']} — {form_name}", value=val, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reg_group.command(name="cancel", description="Cancel your pending registration application")
    @app_commands.describe(submission_id="The ID of the submission to cancel")
    async def reg_cancel(self, interaction: discord.Interaction, submission_id: int):
        sub = self.db.get_submission(submission_id)
        if not sub or sub["guild_id"] != str(interaction.guild_id) or sub["user_id"] != str(interaction.user.id):
            await interaction.response.send_message(embed=embed_error("Not Found", "Application not found or does not belong to you."), ephemeral=True)
            return

        if sub["status"] != "pending":
            await interaction.response.send_message(embed=embed_warning("Cannot Cancel", f"You cannot cancel an application that is already marked as `{sub['status'].upper()}`."), ephemeral=True)
            return

        self.db.update_submission_status(submission_id, "cancelled")
        self.db.log_event(str(interaction.guild_id), "cancelled", f"User {interaction.user} cancelled application #{submission_id}",
                          registration_id=sub["registration_id"], submission_id=submission_id, target_user_id=str(interaction.user.id))
        await interaction.response.send_message(embed=embed_success("Cancelled", f"Application #{submission_id} has been cancelled."), ephemeral=True)

    # -----------------------------------------------------------------------
    # Helper Panel Builders
    # -----------------------------------------------------------------------
    def build_admin_builder_panel(self, form_id: int) -> Tuple[discord.Embed, discord.ui.View]:
        config = self.db.get_form(form_id)
        questions = self.db.get_questions(form_id)

        embed = discord.Embed(
            title=f"🛠️ Registration Form Builder — {config['name']}",
            description="Configure your registration form, add questions, set automations, and publish to Discord.",
            color=C.BRAND
        )
        embed.add_field(name="Form ID", value=f"`#{config['id']}`", inline=True)
        embed.add_field(name="Status", value="🟢 Enabled" if config["enabled"] else "🔴 Disabled", inline=True)
        embed.add_field(name="Questions", value=f"📝 {len(questions)} configured", inline=True)

        mode_label = "⚡ Automatic Approval" if config["approval_mode"] == "automatic" else "🛡️ Staff Review"
        embed.add_field(name="Approval Mode", value=mode_label, inline=True)

        chan_txt = f"<#{config['channel_id']}>" if config["channel_id"] else "*Not set*"
        embed.add_field(name="Target Channel", value=chan_txt, inline=True)

        log_txt = f"<#{config['log_channel_id']}>" if config["log_channel_id"] else "*Not set*"
        embed.add_field(name="Log Channel", value=log_txt, inline=True)

        view = AdminBuilderView(self, form_id)
        return embed, view

    def build_questions_panel(self, form_id: int) -> Tuple[discord.Embed, discord.ui.View]:
        config = self.db.get_form(form_id)
        questions = self.db.get_questions(form_id)

        embed = discord.Embed(
            title=f"📋 Manage Questions — {config['name']}",
            description=f"Total Questions: **{len(questions)}**\nUse the buttons below to add or remove questions.",
            color=C.BRAND
        )

        if not questions:
            embed.description += "\n\n*No questions added yet. Click 'Add Question' below to begin.*"
        else:
            for idx, q in enumerate(questions):
                req_str = "Required" if q["required"] else "Optional"
                t_label = FIELD_TYPES.get(q["field_type"], q["field_type"])
                embed.add_field(
                    name=f"{idx + 1}. {q['question']}",
                    value=f"**Type:** `{t_label}` • **Rule:** `{req_str}` (ID: `#{q['id']}`)",
                    inline=False
                )

        view = AdminQuestionsView(self, form_id)
        return embed, view

    def build_config_panel(self, form_id: int) -> Tuple[discord.Embed, discord.ui.View]:
        config = self.db.get_form(form_id)
        embed = discord.Embed(
            title=f"⚙️ Settings & Automations — {config['name']}",
            description="Manage auto-roles, nickname change rules, approval workflow, and review channels.",
            color=C.BRAND
        )

        try:
            add_ids = json.loads(config["add_role_ids"] or "[]")
            add_txt = ", ".join(f"<@&{r}>" for r in add_ids) if add_ids else "*None*"
        except Exception:
            add_txt = "*None*"

        try:
            rem_ids = json.loads(config["remove_role_ids"] or "[]")
            rem_txt = ", ".join(f"<@&{r}>" for r in rem_ids) if rem_ids else "*None*"
        except Exception:
            rem_txt = "*None*"

        embed.add_field(name="🛡️ Add Roles Upon Approval", value=add_txt, inline=False)
        embed.add_field(name="🗑️ Remove Roles Upon Approval", value=rem_txt, inline=False)

        nick_enabled = "🟢 Enabled" if config["change_nickname_enabled"] else "🔴 Disabled"
        nick_qid = f"Question #{config['nickname_question_id']}" if config["nickname_question_id"] else "*Not set*"
        nick_fmt = config["nickname_format"] or "{name}"
        embed.add_field(name="🏷️ Nickname Automation", value=f"Status: {nick_enabled}\nSource: {nick_qid}\nFormat: `{nick_fmt}`", inline=False)

        rev_chan = f"<#{config['review_channel_id']}>" if config["review_channel_id"] else "*Not set*"
        log_chan = f"<#{config['log_channel_id']}>" if config["log_channel_id"] else "*Not set*"
        embed.add_field(name="Review Channel", value=rev_chan, inline=True)
        embed.add_field(name="Log Channel", value=log_chan, inline=True)
        embed.add_field(name="Approval Mode", value=f"`{config['approval_mode'].upper()}`", inline=True)

        view = AdminConfigView(self, form_id)
        return embed, view


# ---------------------------------------------------------------------------
# Admin UI Interactive Views
# ---------------------------------------------------------------------------

class AdminBuilderView(discord.ui.View):
    def __init__(self, cog: RegistrationCog, form_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.form_id = form_id

    @discord.ui.button(label="Add Question", style=discord.ButtonStyle.primary, emoji="➕")
    async def add_q_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddQuestionModal(self.cog, self.form_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Manage Questions", style=discord.ButtonStyle.secondary, emoji="📋")
    async def manage_q_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed, view = self.cog.build_questions_panel(self.form_id)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Settings & Roles", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def config_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed, view = self.cog.build_config_panel(self.form_id)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Toggle Enable", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = self.cog.db.get_form(self.form_id)
        new_state = 0 if config["enabled"] else 1
        self.cog.db.update_form(self.form_id, enabled=new_state)
        embed, view = self.cog.build_admin_builder_panel(self.form_id)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="❌")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=embed_info("Builder Closed", "Registration builder closed."), view=None)


class AddQuestionModal(discord.ui.Modal, title="Add Question to Form"):
    question_text = discord.ui.TextInput(label="Question", placeholder="e.g. What is your real name / age / department?", required=True, max_length=150)
    type_code = discord.ui.TextInput(
        label="Type (text/paragraph/number/yes_no/select)",
        placeholder="short_text | paragraph | number | yes_no | single_select | date | url",
        default="short_text",
        required=True
    )
    choices_str = discord.ui.TextInput(
        label="Choices (Comma-separated for select types)",
        placeholder="Police, EMS, Mechanic, Civilian",
        required=False
    )
    is_required = discord.ui.TextInput(label="Required? (yes / no)", default="yes", required=True, max_length=5)

    def __init__(self, cog: RegistrationCog, form_id: int):
        super().__init__()
        self.cog = cog
        self.form_id = form_id

    async def on_submit(self, interaction: discord.Interaction):
        q_text = self.question_text.value.strip()
        raw_type = self.type_code.value.strip().lower()

        field_type = "short_text"
        for k in FIELD_TYPES.keys():
            if raw_type in (k, k.replace("_", " "), k.replace("_", "")):
                field_type = k
                break
        if "select" in raw_type and field_type == "short_text":
            field_type = "single_select"
        elif "number" in raw_type:
            field_type = "number"
        elif "paragraph" in raw_type or "long" in raw_type:
            field_type = "paragraph"
        elif "yes" in raw_type:
            field_type = "yes_no"

        req = self.is_required.value.strip().lower() in ("yes", "y", "true", "1")
        choices = [c.strip() for c in self.choices_str.value.split(",") if c.strip()]

        self.cog.db.add_question(self.form_id, question=q_text, field_type=field_type, required=req, options=choices)
        embed, view = self.cog.build_questions_panel(self.form_id)
        await interaction.response.edit_message(embed=embed, view=view)


class AdminQuestionsView(discord.ui.View):
    def __init__(self, cog: RegistrationCog, form_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.form_id = form_id

    @discord.ui.button(label="Add Question", style=discord.ButtonStyle.primary, emoji="➕")
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddQuestionModal(self.cog, self.form_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove Last Question", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def del_last_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        questions = self.cog.db.get_questions(self.form_id)
        if questions:
            self.cog.db.delete_question(questions[-1]["id"])
        embed, view = self.cog.build_questions_panel(self.form_id)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Back to Builder", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed, view = self.cog.build_admin_builder_panel(self.form_id)
        await interaction.response.edit_message(embed=embed, view=view)


class AdminConfigView(discord.ui.View):
    def __init__(self, cog: RegistrationCog, form_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.form_id = form_id

    @discord.ui.button(label="Toggle Approval Mode", style=discord.ButtonStyle.primary, emoji="⚖️")
    async def toggle_approval(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = self.cog.db.get_form(self.form_id)
        new_mode = "staff_review" if config["approval_mode"] == "automatic" else "automatic"
        self.cog.db.update_form(self.form_id, approval_mode=new_mode)
        embed, view = self.cog.build_config_panel(self.form_id)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Set Channels & Nickname", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def edit_channels_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        class ConfigModal(discord.ui.Modal, title="Configure Registration"):
            rev_chan = discord.ui.TextInput(label="Staff Review Channel ID", required=False, placeholder="Paste channel ID")
            log_chan = discord.ui.TextInput(label="Log Channel ID", required=False, placeholder="Paste channel ID")
            auto_roles = discord.ui.TextInput(label="Role IDs to Add (Comma-separated)", required=False, placeholder="Role ID 1, Role ID 2")
            rem_roles = discord.ui.TextInput(label="Role IDs to Remove (Comma-separated)", required=False, placeholder="Role ID 1, Role ID 2")
            nick_qid = discord.ui.TextInput(label="Nickname Source Question ID (Optional)", required=False, placeholder="e.g. 1")

            def __init__(self, parent_view: AdminConfigView):
                super().__init__()
                self.pv = parent_view

            async def on_submit(self, modal_interaction: discord.Interaction):
                upd = {}
                if self.rev_chan.value.strip():
                    upd["review_channel_id"] = self.rev_chan.value.strip()
                if self.log_chan.value.strip():
                    upd["log_channel_id"] = self.log_chan.value.strip()
                if self.auto_roles.value.strip():
                    r_ids = [r.strip() for r in self.auto_roles.value.split(",") if r.strip()]
                    upd["add_role_ids"] = json.dumps(r_ids)
                    upd["auto_role_enabled"] = 1
                if self.rem_roles.value.strip():
                    r_ids = [r.strip() for r in self.rem_roles.value.split(",") if r.strip()]
                    upd["remove_role_ids"] = json.dumps(r_ids)
                    upd["remove_role_enabled"] = 1
                if self.nick_qid.value.strip():
                    try:
                        upd["nickname_question_id"] = int(self.nick_qid.value.strip())
                        upd["change_nickname_enabled"] = 1
                    except ValueError:
                        pass

                if upd:
                    self.pv.cog.db.update_form(self.pv.form_id, **upd)
                embed, view = self.pv.cog.build_config_panel(self.pv.form_id)
                await modal_interaction.response.edit_message(embed=embed, view=view)

        await interaction.response.send_modal(ConfigModal(self))

    @discord.ui.button(label="Back to Builder", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed, view = self.cog.build_admin_builder_panel(self.form_id)
        await interaction.response.edit_message(embed=embed, view=view)


# ---------------------------------------------------------------------------
# Setup Hook
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot):
    cog = RegistrationCog(bot)
    await bot.add_cog(cog)
    print(f"📝 {BOT_NAME} Dynamic Registration System loaded!")
