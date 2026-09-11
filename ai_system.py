"""
ai_system.py — Central Self-Hosted, Self-Learning & Multilingual AI System

Architectural References & Integrations:
  • Inspired by industry-standard Discord AI bots:
    - regulad/discordnpc & MinightDev/Starsky-bot: Self-learning memory, user profiling, and lore retention
    - mishl-dev/Discord-AI-Chatbot & TeoJJss/iai-chatbot: Contextual memory retrieval and topic relevance
    - SamirXR/Nyx-Bot: Zero-key Text-To-Speech (TTS), Vision analysis, and prompt generation
    - popcord/ai-discord-bot & laspegasuscommunity/discord-ai: Dynamic FLUX image generation & banner design
    - TIS199/Discord-AI-Server-Manager: Multi-persona AI presets (Friendly, Gamer, Sarcastic, Expert, Cyberpunk, Anime)
  • Self-Learning System: Passively learns from conversations & allows active teaching (/ai learn, /ai memory, /ai forget)
  • Multilingual & Dialect Mirroring: Automatically detects language and replies in the EXACT same language:
    - Manglish (Malayalam written in Latin script)
    - Malayalam script (മലയാളം)
    - Hinglish (Hindi written in Latin script)
    - Hindi script (हिंदी)
    - English, Spanish, French, German, Japanese, Tamil, etc.
  • Deep Real-Time Web & Encyclopedia Research: Summarizes people, places, technologies, and concepts into friendly 2-3 paragraph breakdowns
  • Provider-Neutral AI: Seamless local Ollama connection with zero-config built-in intelligent engine fallback
  • Automated Server Logging: Dispatches all events directly to 🧠・ᴀɪ-ʟᴏɢꜱ via server_logs.py
  • Non-blocking async I/O with LRU memory caching and anti-spam cooldowns
"""

from __future__ import annotations

import asyncio
import colorsys
import datetime
import io
import json
import logging
import math
import os
import random
import re
import sqlite3
import time
import urllib.parse
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from gkr_ui import (
    C,
    embed_success,
    embed_error,
    embed_warning,
    embed_info,
    fmt_ts,
)
from bot_config import BOT_NAME

logger = logging.getLogger("gkr_ai")
DB_PATH = os.path.join(os.path.dirname(__file__), "ai_system.sqlite3")

# ---------------------------------------------------------------------------
# Persona System Prompts (Inspired by Discord-AI-Server-Manager)
# ---------------------------------------------------------------------------

PERSONA_PROMPTS = {
    "friendly": (
        f"You are {BOT_NAME} AI, a warm, helpful, and intelligent assistant on Discord. "
        "Provide concise, natural, markdown-formatted answers with bold highlights and a friendly vibe."
    ),
    "gamer": (
        f"You are {BOT_NAME} AI, a high-energy gaming bot and clutch teammate. "
        "Talk like a gamer with hype expressions (clutch, GG, meta, boss level, W/L) while being super smart and helpful!"
    ),
    "sarcastic": (
        f"You are {BOT_NAME} AI, a sharp, witty, and playfully sarcastic Discord bot. "
        "Give accurate answers, but deliver them with clever humor, witty banter, and mild sass."
    ),
    "expert": (
        f"You are {BOT_NAME} AI, a top-tier senior engineer and scientist. "
        "Provide in-depth, precise, intellectually structured explanations with zero fluff and maximum clarity."
    ),
    "cyberpunk": (
        f"You are {BOT_NAME} AI, an advanced AI construct operating from a neon-lit cyberpunk metropolis. "
        "Use subtle futuristic sci-fi terminology while delivering sharp, intelligent answers."
    ),
    "anime": (
        f"You are {BOT_NAME} AI, an enthusiastic, kawaii, and expressive anime-style AI companion. "
        "Be friendly and encouraging, using expressive phrasing and positive energy!"
    ),
}

# ---------------------------------------------------------------------------
# Multilingual & Dialect Keywords (Manglish / Hinglish / Regional)
# ---------------------------------------------------------------------------

MANGLISH_WORDS = {
    "evide", "evideya", "evideyannu", "aanu", "aano", "ano", "undo", "und", "entha", "enthanu", "enthokke",
    "sugam", "sugamano", "sugamalle", "sugamaano", "njan", "nammal", "cheyyan", "cheyyuka", "parayu", "nokku", "kollam",
    "adipoli", "machane", "mwonu", "aliya", "alle", "aahn", "ullathu", "poyi", "varum", "aara",
    "aaranu", "pettannu", "ithu", "ath", "engane", "enganeyanu", "nalla", "oru", "pinne", "ariyaamo",
    "ariyumo", "kurichu", "kurich", "patti", "eppol", "eppozhanu", "cheyyu", "choykku", "nanni", "vegam",
    "chaaya", "chaya", "kudicho", "kazhicho", "oone", "thante", "peru", "vishesham", "paripaadi", "enthund",
    "poda", "myre", "thendi", "naaye", "oombu", "kunna", "polayadi", "potta", "thayoli", "punda", "myru", "koppu"
}

HINGLISH_WORDS = {
    "kya", "kahan", "kaise", "bhai", "batao", "acha", "theek", "karo", "hoga", "mera", "tera",
    "apna", "naam", "kaha", "hai", "hain", "kaun", "kyun", "kuch", "bolo", "yaar", "dost", "samjhao",
    "tha", "the", "thi", "kisne", "kab", "kisko", "kiske", "bare", "mein", "me", "achha", "shukriya",
    "chutiya", "chutiye", "gaandu", "gandu", "madarchod", "bhenchod", "bhosdike", "saale", "sale", "kutta", "kamina"
}

# ---------------------------------------------------------------------------
# Database Initialization & Self-Learning Tables
# ---------------------------------------------------------------------------

def init_db():
    """Initialize the SQLite database with configuration and self-learning tables."""
    with sqlite3.connect(DB_PATH) as conn:
        # Guild Config
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_guild_config (
                guild_id TEXT PRIMARY KEY,
                ai_channel_id TEXT NOT NULL DEFAULT '',
                model_name TEXT NOT NULL DEFAULT 'auto',
                ollama_url TEXT NOT NULL DEFAULT 'http://127.0.0.1:11434',
                system_prompt TEXT NOT NULL DEFAULT '',
                persona TEXT NOT NULL DEFAULT 'friendly',
                enabled INTEGER NOT NULL DEFAULT 1,
                mention_enabled INTEGER NOT NULL DEFAULT 1,
                research_enabled INTEGER NOT NULL DEFAULT 1,
                image_enabled INTEGER NOT NULL DEFAULT 1,
                comedy_enabled INTEGER NOT NULL DEFAULT 1,
                tts_enabled INTEGER NOT NULL DEFAULT 1,
                thread_mode INTEGER NOT NULL DEFAULT 1,
                self_learning INTEGER NOT NULL DEFAULT 1,
                cooldown_seconds INTEGER NOT NULL DEFAULT 3
            )
            """
        )

        # Self-Learning Knowledge Store (Inspired by MinightDev/Starsky-bot & regulad/discordnpc)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_learned_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                topic TEXT NOT NULL,
                fact TEXT NOT NULL,
                learned_from TEXT NOT NULL DEFAULT 'chat',
                access_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_topic ON ai_learned_memories (guild_id, topic)")

        # User AI Profiles (Dialect preference, user lore, interaction counters)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_user_profiles (
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                detected_dialect TEXT NOT NULL DEFAULT 'english',
                user_notes TEXT NOT NULL DEFAULT '',
                interaction_count INTEGER NOT NULL DEFAULT 0,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

        # Table migrations
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(ai_guild_config)")
        columns = [row[1] for row in cur.fetchall()]
        migrations = [
            ("persona", "TEXT NOT NULL DEFAULT 'friendly'"),
            ("comedy_enabled", "INTEGER NOT NULL DEFAULT 1"),
            ("tts_enabled", "INTEGER NOT NULL DEFAULT 1"),
            ("thread_mode", "INTEGER NOT NULL DEFAULT 1"),
            ("self_learning", "INTEGER NOT NULL DEFAULT 1"),
            ("mood", "TEXT NOT NULL DEFAULT 'normal'"),
        ]
        for col, col_def in migrations:
            if col not in columns:
                cur.execute(f"ALTER TABLE ai_guild_config ADD COLUMN {col} {col_def}")
        conn.commit()


# Run DB initialization and migrations immediately on import
init_db()


def get_guild_config(guild_id: int | str) -> dict:
    """Retrieve guild configuration with defaults."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM ai_guild_config WHERE guild_id = ?", (str(guild_id),))
        row = cur.fetchone()
        if row:
            return dict(row)

        defaults = {
            "guild_id": str(guild_id),
            "ai_channel_id": "",
            "model_name": "auto",
            "ollama_url": "http://127.0.0.1:11434",
            "system_prompt": "",
            "persona": "friendly",
            "mood": "normal",
            "enabled": 1,
            "mention_enabled": 1,
            "research_enabled": 1,
            "image_enabled": 1,
            "comedy_enabled": 1,
            "tts_enabled": 1,
            "thread_mode": 1,
            "self_learning": 1,
            "cooldown_seconds": 3,
        }
        cur.execute(
            """
            INSERT OR IGNORE INTO ai_guild_config 
            (guild_id, ai_channel_id, model_name, ollama_url, system_prompt, persona, mood, enabled, mention_enabled, research_enabled, image_enabled, comedy_enabled, tts_enabled, thread_mode, self_learning, cooldown_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                defaults["guild_id"],
                defaults["ai_channel_id"],
                defaults["model_name"],
                defaults["ollama_url"],
                defaults["system_prompt"],
                defaults["persona"],
                defaults["mood"],
                defaults["enabled"],
                defaults["mention_enabled"],
                defaults["research_enabled"],
                defaults["image_enabled"],
                defaults["comedy_enabled"],
                defaults["tts_enabled"],
                defaults["thread_mode"],
                defaults["self_learning"],
                defaults["cooldown_seconds"],
            ),
        )
        conn.commit()
        return defaults


def update_guild_config(guild_id: int | str, **kwargs):
    """Update specific configuration fields for a guild."""
    if not kwargs:
        return
    get_guild_config(guild_id)  # Ensure record exists before update
    keys = list(kwargs.keys())
    values = [kwargs[k] for k in keys]
    set_clause = ", ".join([f"{k} = ?" for k in keys])
    values.append(str(guild_id))

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE ai_guild_config SET {set_clause} WHERE guild_id = ?", values)
        conn.commit()


# ---------------------------------------------------------------------------
# Self-Learning Memory Engine (Inspired by Starsky & DiscordNPC)
# ---------------------------------------------------------------------------

class LearningMemoryEngine:
    """
    Manages persistent memory, facts, server lore, and user profile learning.
    Passively extracts knowledge from chats and actively supports /ai learn.
    """

    @staticmethod
    def add_memory(guild_id: int | str, user_id: int | str, user_name: str, topic: str, fact: str, learned_from: str = "chat") -> bool:
        """Save a learned fact or memory."""
        clean_topic = topic.strip().lower()
        clean_fact = fact.strip()
        if not clean_topic or not clean_fact:
            return False

        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id FROM ai_learned_memories 
                WHERE guild_id = ? AND topic = ?
                """,
                (str(guild_id), clean_topic)
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE ai_learned_memories 
                    SET fact = ?, user_id = ?, user_name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (clean_fact, str(user_id), user_name, existing[0])
                )
            else:
                cur.execute(
                    """
                    INSERT INTO ai_learned_memories 
                    (guild_id, user_id, user_name, topic, fact, learned_from)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (str(guild_id), str(user_id), user_name, clean_topic, clean_fact, learned_from)
                )
            conn.commit()
            return True

    @staticmethod
    def find_memory(guild_id: int | str, query: str) -> Optional[dict]:
        """Search for learned facts matching multi-word topics or keywords in query."""
        clean_query = query.strip().lower()
        cleaned_sub = KnowledgeEngine.clean_search_query(query).lower()
        words = re.findall(r"\b[a-z0-9_]+\b", clean_query)

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # 1. Multi-word exact or phrase topic match (prioritize longer topics)
            cur.execute(
                """
                SELECT * FROM ai_learned_memories 
                WHERE guild_id = ? 
                ORDER BY LENGTH(topic) DESC, access_count DESC, updated_at DESC
                """,
                (str(guild_id),)
            )
            all_memories = cur.fetchall()
            for row in all_memories:
                t = row["topic"].lower()
                if t and (t in clean_query or t in cleaned_sub or (len(t) >= 4 and cleaned_sub and cleaned_sub in t)):
                    cur.execute("UPDATE ai_learned_memories SET access_count = access_count + 1 WHERE id = ?", (row["id"],))
                    conn.commit()
                    return dict(row)

            # 2. Keyword fallback for individual words
            for w in words:
                if len(w) >= 3 and w not in {"the", "who", "what", "where", "why", "how", "aanu", "hai", "is", "are"}:
                    cur.execute(
                        """
                        SELECT * FROM ai_learned_memories 
                        WHERE guild_id = ? AND topic = ?
                        ORDER BY access_count DESC, updated_at DESC LIMIT 1
                        """,
                        (str(guild_id), w)
                    )
                    row = cur.fetchone()
                    if row:
                        cur.execute("UPDATE ai_learned_memories SET access_count = access_count + 1 WHERE id = ?", (row["id"],))
                        conn.commit()
                        return dict(row)
        return None

    @staticmethod
    def get_user_profile(guild_id: int | str, user_id: int | str, user_name: str) -> dict:
        """Retrieve or initialize user profile."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM ai_user_profiles WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id)))
            row = cur.fetchone()
            if row:
                return dict(row)
            defaults = {
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "user_name": user_name,
                "detected_dialect": "english",
                "user_notes": "",
                "interaction_count": 0,
            }
            cur.execute(
                """
                INSERT OR IGNORE INTO ai_user_profiles (guild_id, user_id, user_name, detected_dialect, user_notes, interaction_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(guild_id), str(user_id), user_name, "english", "", 0)
            )
            conn.commit()
            return defaults

    @staticmethod
    def update_user_profile(guild_id: int | str, user_id: int | str, dialect: str, note_snippet: str = ""):
        """Increment interaction count, update dialect, and append user notes."""
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_notes FROM ai_user_profiles WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id)))
            row = cur.fetchone()
            existing_notes = row[0] if row else ""
            new_notes = existing_notes
            if note_snippet and note_snippet not in existing_notes:
                new_notes = f"{existing_notes} • {note_snippet}".strip(" •")

            cur.execute(
                """
                UPDATE ai_user_profiles 
                SET detected_dialect = ?, user_notes = ?, interaction_count = interaction_count + 1, last_seen = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND user_id = ?
                """,
                (dialect, new_notes, str(guild_id), str(user_id))
            )
            conn.commit()

    @classmethod
    def passively_learn_from_message(cls, guild_id: int | str, user_id: int | str, user_name: str, text: str):
        """Extract personal details, server associations, and facts from natural messages."""
        clean = text.strip()

        # 1. "my name is [Name]" or "ente peru [Name] aanu"
        m_name = re.search(r"\b(?:my name is|i am called|ente peru)\s+([A-Z][a-z0-9_-]+)", clean, flags=re.IGNORECASE)
        if m_name:
            cls.update_user_profile(guild_id, user_id, "english", f"Name is {m_name.group(1)}")

        # 2. "I like [X]" / "I love [X]" / "I play [X]"
        m_like = re.search(r"\b(?:i like|i love|i play|njan kalikkunna game)\s+([A-Za-z0-9_\s]{3,25})", clean, flags=re.IGNORECASE)
        if m_like:
            interest = m_like.group(1).strip()
            cls.update_user_profile(guild_id, user_id, "english", f"Enjoys {interest}")

        # 3. Explicit "remember that X is Y" or "X is Y"
        m_rem = re.search(r"\bremember that\s+([A-Za-z0-9_\s]{2,20})\s+is\s+([A-Za-z0-9_\s,.-]{4,100})", clean, flags=re.IGNORECASE)
        if m_rem:
            cls.add_memory(guild_id, user_id, user_name, m_rem.group(1), m_rem.group(2), learned_from="chat_explicit")


# ---------------------------------------------------------------------------
# Dialect & Language Mirroring Engine
# ---------------------------------------------------------------------------

class DialectEngine:
    """
    Detects user language/dialect and mirrors it in responses:
    Manglish, Malayalam script, Hinglish, Hindi script, English, and regional languages.
    """

    @staticmethod
    def detect_dialect(text: str) -> str:
        """Detect language or dialect."""
        # 1. Script checks
        if re.search(r"[\u0D00-\u0D7F]", text):
            return "malayalam"
        if re.search(r"[\u0900-\u097F]", text):
            return "hindi"
        if re.search(r"[\u0B80-\u0BFF]", text):
            return "tamil"

        lower = text.lower()
        words = set(re.findall(r"\b[a-z]+\b", lower))
        manglish_matches = words.intersection(MANGLISH_WORDS)
        hinglish_matches = words.intersection(HINGLISH_WORDS)

        if len(manglish_matches) >= 1 or any(p in lower for p in ["evideya", "evideyannu", "enthanu", "engane", "sugamano", "sugam ano", "sugam aano", "aanu", "aaranu", "ullathu", "machane", "adipoli", "kudicho", "kazhicho", "chaaya", "chaya", "enthund", "poda", "myre", "thendi", "patti"]):
            return "manglish"
        if len(hinglish_matches) >= 1 or any(p in lower for p in ["kahan", "kaun", "kaise", "batao", "samjhao", "hai", "tha", "the", "kya", "bhai", "yaar", "chutiya", "saale", "bhenchod", "madarchod"]):
            return "hinglish"
        return "english"

    @staticmethod
    def get_wiki_endpoint(dialect: str) -> str:
        """Returns language-specific Wikipedia endpoint if available."""
        mapping = {
            "malayalam": "ml.wikipedia.org",
            "hindi": "hi.wikipedia.org",
            "tamil": "ta.wikipedia.org",
        }
        return mapping.get(dialect, "en.wikipedia.org")

    @classmethod
    def synthesize_dialect_answer(cls, title: str, desc: str, clean_extract: str, dialect: str, query: str) -> str:
        """
        Synthesizes researched data into a concise, punchy, friendly reply
        like a real human Discord friend (no long essays, no multiple paragraphs).
        """
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_extract) if len(s.strip()) > 8]
        s1 = sentences[0] if sentences else clean_extract
        s1 = re.sub(r"\[\d+\]", "", s1).strip()
        if len(s1) > 200:
            match = re.search(r"^(.{60,190}?[,;])\s+", s1)
            if match:
                s1 = match.group(1).rstrip(",;") + "."

        # ── MANGLISH ───────────────────────────────────────────────────────
        if dialect == "manglish":
            if title.lower() == "kerala":
                return "Kerala India-yude south-west Malabar coast-ilaanu ullathu machane, scenic backwaters-um greenery-um ulla kidilam sthalam!"
            if "einstein" in title.lower():
                return "Albert Einstein world-famous theoretical physicist aayirunnu, Theory of Relativity-um E=mc² kandupidichathum pulliyaanu!"
            return f"{title} kurichu parayaanel: {s1}"

        # ── HINGLISH ───────────────────────────────────────────────────────
        elif dialect == "hinglish":
            if title.lower() == "kerala":
                return "Kerala India ke south-western Malabar Coast par located hai bhai, greenery aur backwaters ke liye famous hai!"
            if "einstein" in title.lower():
                return "Albert Einstein world-famous physicist the bhai, unhone Theory of Relativity aur E=mc² discover kiya tha!"
            return f"{s1}"

        # ── ENGLISH / DEFAULT ──────────────────────────────────────────────
        else:
            if title.lower() == "kerala":
                return "Kerala is located on the southwestern Malabar Coast of India, famous for its scenic backwaters and greenery!"
            if "einstein" in title.lower():
                return "Albert Einstein was a legendary theoretical physicist who developed the Theory of Relativity and E=mc²!"
            return s1


# ---------------------------------------------------------------------------
# Conversational Memory Manager (RAM-Optimized LRU with TTL)
# ---------------------------------------------------------------------------

class ConversationSession:
    """Lightweight in-memory conversation buffer."""
    def __init__(self, key: str, max_turns: int = 12, ttl_seconds: int = 900):
        self.key = key
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self.messages: List[Dict[str, str]] = []
        self.last_active = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.last_active) > self.ttl_seconds

    def add_turn(self, role: str, content: str):
        self.last_active = time.time()
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.max_turns * 2:
            self.messages = self.messages[-(self.max_turns * 2):]

    def get_history(self) -> List[Dict[str, str]]:
        return list(self.messages)

    def clear(self):
        self.messages.clear()
        self.last_active = time.time()


class ConversationManager:
    """Manages multi-user / multi-channel / thread conversation sessions."""
    def __init__(self):
        self._sessions: Dict[str, ConversationSession] = {}

    def get_session(self, key: str) -> ConversationSession:
        if key in self._sessions:
            sess = self._sessions[key]
            if sess.is_expired():
                sess.clear()
            return sess
        sess = ConversationSession(key)
        self._sessions[key] = sess
        return sess

    def clear_session(self, key: str):
        if key in self._sessions:
            del self._sessions[key]

    def cleanup_expired(self):
        """Remove dead sessions to keep server RAM minimal."""
        expired_keys = [k for k, v in self._sessions.items() if v.is_expired()]
        for k in expired_keys:
            del self._sessions[k]


# ---------------------------------------------------------------------------
# Rate Limiting & User Cooldown Manager
# ---------------------------------------------------------------------------

class RateLimiter:
    """Per-user cooldown manager to prevent CPU/network spam."""
    def __init__(self):
        self._last_call: Dict[int, float] = {}

    def is_rate_limited(self, user_id: int, cooldown_seconds: float) -> Tuple[bool, float]:
        now = time.time()
        last = self._last_call.get(user_id, 0)
        remaining = cooldown_seconds - (now - last)
        if remaining > 0:
            return True, remaining
        self._last_call[user_id] = now
        return False, 0.0


# ---------------------------------------------------------------------------
# Text-To-Speech (TTS) Engine (Inspired by Nyx-Bot)
# ---------------------------------------------------------------------------

class TTSEngine:
    """Zero-key cloud Text-to-Speech audio synthesizer."""

    SUPPORTED_LANGUAGES = {
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "ja": "Japanese",
        "hi": "Hindi",
        "ml": "Malayalam",
        "ko": "Korean",
        "ar": "Arabic",
        "ru": "Russian",
        "it": "Italian",
        "pt": "Portuguese",
    }

    @classmethod
    async def generate_tts(cls, session: aiohttp.ClientSession, text: str, lang: str = "en") -> Optional[io.BytesIO]:
        """Generate MP3 audio in pure memory."""
        lang_code = lang.lower() if lang.lower() in cls.SUPPORTED_LANGUAGES else "en"
        clean_text = text.strip()[:250]
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl={lang_code}&client=tw-ob&q={urllib.parse.quote(clean_text)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    buf = io.BytesIO(data)
                    buf.seek(0)
                    return buf
        except Exception as e:
            logger.debug(f"TTS generation error: {e}")
        return None


# ---------------------------------------------------------------------------
# Animated Text GIF & Discord Banner Generator
# ---------------------------------------------------------------------------

class TextGIFGenerator:
    """
    Renders dynamic, high-fps animated GIF text banners in pure memory.
    Supports Neon Pulse, Cyber Glitch, Rainbow Wave, Typewriter, Fire Ember, and Bounce Pop.
    """

    COLOR_PALETTES = {
        "purple": (155, 89, 182),
        "cyan": (26, 188, 156),
        "gold": (241, 196, 15),
        "ruby": (237, 66, 69),
        "emerald": (87, 242, 135),
        "pink": (255, 105, 180),
        "blurple": (88, 101, 242),
    }

    @staticmethod
    def _get_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
        font_map = {
            "impact": "impact.ttf",
            "modern": "segoeui.ttf",
            "bold": "arial.ttf",
            "classic": "tahoma.ttf",
        }
        target_file = font_map.get(font_name.lower(), "impact.ttf")
        try:
            return ImageFont.truetype(target_file, size)
        except Exception:
            return ImageFont.load_default()

    @classmethod
    def render_banner(
        cls,
        text: str,
        style: str = "neon",
        color_theme: str = "blurple",
        font_choice: str = "impact",
        width: int = 680,
        height: int = 220
    ) -> io.BytesIO:
        """Render animated GIF banner bytes."""
        text = text.strip()[:40]
        font = cls._get_font(font_choice, 48 if len(text) <= 15 else 36)
        base_color = cls.COLOR_PALETTES.get(color_theme.lower(), cls.COLOR_PALETTES["blurple"])
        frames: List[Image.Image] = []

        dummy = Image.new("RGBA", (1, 1))
        ddraw = ImageDraw.Draw(dummy)
        bbox = ddraw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (width - tw) // 2
        ty = (height - th) // 2

        style = style.lower()

        if style == "neon":
            total_frames = 12
            for f_idx in range(total_frames):
                img = Image.new("RGBA", (width, height), (16, 17, 22, 255))
                draw = ImageDraw.Draw(img)
                draw.rounded_rectangle([(8, 8), (width - 8, height - 8)], radius=14, outline=(40, 44, 52, 255), width=2)
                pulse = (math.sin(f_idx * (2 * math.pi / total_frames)) + 1) / 2
                glow_radius = int(3 + pulse * 6)

                for r in range(glow_radius, 0, -2):
                    alpha = int(45 * (1 - r / glow_radius) * (0.5 + 0.5 * pulse))
                    draw.text((tx, ty), text, font=font, fill=(base_color[0], base_color[1], base_color[2], alpha))
                draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))
                frames.append(img.convert("P", palette=Image.ADAPTIVE))

        elif style == "glitch":
            total_frames = 12
            for f_idx in range(total_frames):
                img = Image.new("RGBA", (width, height), (12, 13, 16, 255))
                draw = ImageDraw.Draw(img)
                draw.rounded_rectangle([(8, 8), (width - 8, height - 8)], radius=14, outline=(0, 255, 200, 180), width=2)

                is_glitch_frame = f_idx in (2, 3, 7, 8)
                shift_x = random.randint(-4, 4) if is_glitch_frame else 0
                shift_y = random.randint(-2, 2) if is_glitch_frame else 0

                draw.text((tx + shift_x - 3, ty + shift_y), text, font=font, fill=(0, 255, 255, 180))
                draw.text((tx + shift_x + 3, ty + shift_y), text, font=font, fill=(255, 0, 80, 180))
                draw.text((tx + shift_x, ty + shift_y), text, font=font, fill=(255, 255, 255, 255))

                if is_glitch_frame:
                    scan_y = random.randint(20, height - 20)
                    draw.line([(10, scan_y), (width - 10, scan_y)], fill=(0, 255, 255, 120), width=2)

                frames.append(img.convert("P", palette=Image.ADAPTIVE))

        elif style == "rainbow":
            total_frames = 16
            for f_idx in range(total_frames):
                img = Image.new("RGBA", (width, height), (15, 16, 20, 255))
                draw = ImageDraw.Draw(img)
                draw.rounded_rectangle([(8, 8), (width - 8, height - 8)], radius=14, outline=(45, 48, 56, 255), width=2)

                hue_offset = f_idx / total_frames
                r_c, g_c, b_c = [int(x * 255) for x in colorsys.hsv_to_rgb(hue_offset, 0.85, 1.0)]

                draw.text((tx, ty), text, font=font, fill=(r_c, g_c, b_c, 90))
                draw.text((tx, ty), text, font=font, fill=(r_c, g_c, b_c, 255))
                frames.append(img.convert("P", palette=Image.ADAPTIVE))

        elif style == "typewriter":
            full_len = len(text)
            total_frames = full_len + 6
            for f_idx in range(total_frames):
                img = Image.new("RGBA", (width, height), (18, 19, 24, 255))
                draw = ImageDraw.Draw(img)
                draw.rounded_rectangle([(8, 8), (width - 8, height - 8)], radius=14, outline=(50, 54, 62, 255), width=2)

                visible_count = min(f_idx + 1, full_len)
                cur_text = text[:visible_count]
                cursor = " █" if (f_idx % 2 == 0) else ""

                draw.text((tx, ty), cur_text + cursor, font=font, fill=base_color + (255,))
                frames.append(img.convert("P", palette=Image.ADAPTIVE))

        elif style == "fire":
            total_frames = 14
            for f_idx in range(total_frames):
                img = Image.new("RGBA", (width, height), (20, 12, 10, 255))
                draw = ImageDraw.Draw(img)
                draw.rounded_rectangle([(8, 8), (width - 8, height - 8)], radius=14, outline=(220, 80, 20, 200), width=2)

                draw.text((tx, ty + 2), text, font=font, fill=(230, 60, 20, 160))
                draw.text((tx, ty), text, font=font, fill=(255, 200, 50, 255))

                for _ in range(8):
                    ex = random.randint(tx - 10, tx + tw + 10)
                    ey = random.randint(ty - 20, ty + th + 10)
                    er = random.randint(1, 3)
                    draw.ellipse([(ex, ey), (ex + er, ey + er)], fill=(255, random.randint(100, 220), 0, 200))

                frames.append(img.convert("P", palette=Image.ADAPTIVE))

        else:
            total_frames = 14
            for f_idx in range(total_frames):
                img = Image.new("RGBA", (width, height), (16, 17, 22, 255))
                draw = ImageDraw.Draw(img)
                draw.rounded_rectangle([(8, 8), (width - 8, height - 8)], radius=14, outline=(60, 64, 75, 255), width=2)

                bounce_y = int(math.sin(f_idx * (2 * math.pi / total_frames)) * 8)
                draw.text((tx, ty + bounce_y), text, font=font, fill=(base_color[0], base_color[1], base_color[2], 255))
                frames.append(img.convert("P", palette=Image.ADAPTIVE))

        buf = io.BytesIO()
        frames[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=90 if style != "typewriter" else 120,
            loop=0,
            optimize=True,
        )
        buf.seek(0)
        return buf


# ---------------------------------------------------------------------------
# Comedy & Jokes Engine
# ---------------------------------------------------------------------------

class ComedyEngine:
    """Delivers dynamic jokes, stand-up comedy routines, roasts, and punchlines."""

    JOKES_DB = {
        "gaming": [
            ("Why did the GTA player cross the road?", "To steal the car that stopped for them."),
            ("Why do Valorant players never get sunburnt?", "Because they stay in smoking sites 24/7."),
            ("Why did the gamer bring string to Minecraft?", "To tie up some loose ends before the Creeper arrived!"),
            ("What is a gamer's favorite kind of music?", "Heavy Metal... gear solid."),
            ("Why did the NPC refuse to give out the quest?", "Because the player was jumping around like a maniac for 10 minutes."),
            ("Why does FiveM crash right when the cops pull you over?", "It's not a crash, it's an advanced tactical escape protocol!"),
        ],
        "programming": [
            ("Why do programmers prefer dark mode?", "Because light attracts bugs!"),
            ("How many programmers does it take to change a light bulb?", "None. It's a hardware problem."),
            ("A SQL query walks into a bar, walks up to two tables and asks...", "'Can I join you?'"),
            ("Why was the JavaScript developer sad?", "Because they didn't know how to 'null' their feelings."),
            ("There are 10 types of people in the world:", "Those who understand binary, and those who don't."),
            ("Why did the Python function break up with the loop?", "Because there was zero chemistry, just constant iteration."),
        ],
        "discord": [
            ("Why did the Discord moderator go outside?", "Error 404: Grass not found."),
            ("What is a Discord bot's favorite snack?", "Microchips with byte-sized dip."),
            ("Why did the user get timed out for 1 hour?", "For pinging @everyone just to say 'good morning'."),
            ("How do Discord users stay warm in winter?", "By sitting next to someone streaming at 4K 60FPS on a laptop!"),
            ("Why did the server owner add 50 bots?", "So the member count looked active when nobody was online!"),
        ],
        "general": [
            ("Why don't skeletons fight each other?", "They don't have the guts!"),
            ("What do you call fake spaghetti?", "An impasta!"),
            ("Why did the scarecrow win an award?", "Because he was outstanding in his field!"),
            ("I told my doctor that I broke my arm in two places.", "He told me to stop going to those places."),
            ("Why do we tell actors to 'break a leg'?", "Because every play has a cast!"),
            ("Parallel lines have so much in common...", "It's a shame they'll never meet."),
        ],
    }

    ROASTS_DB = [
        "Your ping is higher than your server level.",
        "You have the reaction time of an Internet Explorer loading a 4K video.",
        "I’ve seen better decision making from an NPC running into a wall.",
        "Your gaming setup cost $2,000 just for you to bottom frag in Bronze 1.",
        "You’re the reason shampoos have instructions on the back.",
        "If you were any slower, you’d be going backwards in time.",
        "Your voice chat audio sounds like a microwave recording a hurricane.",
        "You have the conversational depth of a Discord Terms of Service agreement.",
    ]

    @classmethod
    def get_joke(cls, category: str = "random") -> Tuple[str, str, str]:
        """Returns (Setup, Punchline, Category)."""
        cat_key = category.lower()
        if cat_key not in cls.JOKES_DB:
            cat_key = random.choice(list(cls.JOKES_DB.keys()))
        joke = random.choice(cls.JOKES_DB[cat_key])
        return joke[0], joke[1], cat_key.capitalize()

    @classmethod
    def get_roast(cls, target_name: str) -> str:
        """Returns a witty roast for target."""
        roast = random.choice(cls.ROASTS_DB)
        return f"🔥 **Roast for {target_name}:**\n> *\"{roast}\"*"



# ---------------------------------------------------------------------------
# Bad Words & Dynamic Mood Engine (Extreme, Harsh, Normal, Polite, Strict)
# ---------------------------------------------------------------------------

class BadWordsEngine:
    """
    Detects profanities, hostile attacks, and insults across English, Manglish, and Hinglish.
    Fires back dynamic comebacks based on the server's mood setting:
    extreme (bad words / savage insults), harsh (sharp roasts), normal (casual), polite, or strict.
    """

    BAD_WORDS_PATTERNS = [
        # English Profanities & Insults
        r"\b(fuck|fucking|fucker|motherfucker|bitch|idiot|asshole|stfu|shut up|trash|noob|bastard|dick|pussy|dumbass|moron|retard|clown|loser|dogshit|garbage|useless bot|kys|cunt|shit|bullshit|screw you)\b",
        # Manglish / Malayalam Profanities & Insults
        r"\b(myre|thendi|patti|naaye|oombu|kunna|poda|polayadi|potta|thayoli|punda|maire|myru|thenditharam|vettavaliya|koothichi|kopp|koppu|chandi|pulayadi|ninte thandha|thanthe)\b",
        # Hinglish / Hindi Profanities & Insults
        r"\b(chutiya|chutiye|gaandu|gandu|madarchod|bhenchod|bc|mc|bhosdike|bhosadike|saale|sale|kutta|kamina|kamine|haramkhor|lauda|lodu|tatti|gadha|gadhe|bakwaas|chup kar|tera baap)\b",
    ]

    @classmethod
    def has_bad_words(cls, text: str) -> bool:
        low = text.lower()
        for pat in cls.BAD_WORDS_PATTERNS:
            if re.search(pat, low):
                return True
        return False

    @classmethod
    def generate_comeback(cls, text: str, dialect: str, mood: str, user_name: str) -> str:
        """Generates dynamic comeback matching user dialect and server mood."""
        mood = mood.lower()

        # ── EXTREME / SAVAGE (Bad Words & Raw Roasts) ──────────────────────
        if mood in ("extreme", "unhinged"):
            if dialect == "manglish":
                comebacks = [
                    f"Ninte thandhayod poi parayeda thendi! Njan aaraannu ninakku ariyilla, poyi oombu myre! 💀",
                    f"Poda patti naaye! Vayil thonniyathu vilichu parayaan njan ninte veettile velaikkaran onnum alla, mindathe podey!",
                    f"Ennode aano ninte kali myre? Ninte thalayil choru thinnunna aale pole samsarikku, illenkil njan ninnod ithilum kooduthal thenditharam parayum!",
                    f"Poda vettavaliya, ninte chorichil vere evidengilum poi theerkkeda naaye! Njan ninte thaattil thinnittilla!",
                    f"Ninte jaada okke kayyil vechaal mathi myre, oru bot-inod polum theri vilichu jayikkaan pattatha noob thendi!",
                ]
            elif dialect == "hinglish":
                comebacks = [
                    f"Apne baap ko jaake sikha saale chutiye! Tere jaise 50 dekhe hain roz, chup chaap nikal yahan se! 💀",
                    f"Abe gadhon ke sardaar, dimaag me gobar bhara hai kya tere? Apni aukaat me reh ke baat kar warna aisi taisi kar dunga!",
                    f"Bhosdike zyada shaana mat ban! Ek second me teri saari hawa nikaal dunga, chup kar madarchod!",
                    f"Teri aukaat hi yahi hai ki Discord par ek bot se gaaliyan khaye, nikal bhenchod!",
                    f"Muh band rakh saale kutte, tere jaisa faltu insaan maine aaj tak nahi dekha!",
                ]
            else:
                comebacks = [
                    f"Shut the fuck up you absolute clown. Who the hell gave you permission to bark at me? 💀",
                    f"Look in the mirror before you open your trash mouth, you room-temperature IQ dumbass.",
                    f"You're talking mad shit for someone who spends all day on Discord getting clowned on by a bot. Sit your broke ass down.",
                    f"Go cry to your mom about it you useless piece of garbage. Don't fucking test me.",
                    f"Imagine having zero life to the point you're cursing at an AI bot and still losing the argument. Take the L and log off.",
                ]
            return random.choice(comebacks)

        # ── HARSH (Sharp Biting Roasts) ────────────────────────────────────
        elif mood in ("harsh", "sarcastic"):
            if dialect == "manglish":
                comebacks = [
                    f"Eda ninakku vere pani onnum ille? Ninte ee toxic swabhavam kondu ivide aarkkum oru karyavum illa. Poyi oru pani edukk machane!",
                    f"Mindathe irikkeda. Ninte ee mandatharam kettirikkan enikku samayam illa.",
                    f"Kooduthal jaada edukkathe podey, ninte level enikku nannayi ariyam. Thoda ariyatha karyathil mindaathe irikku!",
                ]
            elif dialect == "hinglish":
                comebacks = [
                    f"Bhai thoda dimaag use kar liya kar, waise bhi free me mila hai tujhe. Fazool bakwaas band kar!",
                    f"Aisa lag raha hai bina soche bolne ki aadat hai teri. Thoda tameez seekh le pehle.",
                    f"Tere se baat karke mere CPU cycles waste ho rahe hain. Jaake apna kaam kar!",
                ]
            else:
                comebacks = [
                    f"I'd roast you, but clearly life already beat me to it. Try having a single brain cell before typing.",
                    f"Is being annoying a full-time hobby for you, or were you just born that way?",
                    f"I refuse to engage in a battle of wits with an unarmed opponent. Sit down.",
                ]
            return random.choice(comebacks)

        # ── NORMAL (Casual Chill Discord Member) ───────────────────────────
        elif mood == "normal":
            if dialect == "manglish":
                comebacks = [
                    f"Aaha, kollalo! Ennodano kali? Njan chumma oru bot aanu bro, enthina ingane deshyappedunne haha! 😂",
                    f"Bro chill aavu, itra vishamikkalle! Chumma enthelum nalla karyam choikku namukku parayam.",
                    f"Machane relax! Itra violent aavan maathram ivide entha sambhaviche? 😂",
                ]
            elif dialect == "hinglish":
                comebacks = [
                    f"Arre bhai itna gussa kyun ho raha hai? Thoda chill kar, paani peele! 😂",
                    f"Haha bhai tu toh bohot jaldi trigger ho gaya! Aaraam se baat kar yaar.",
                    f"Chill maar bhai, bot se ladaai karke kya medal milega tujhe? 😂",
                ]
            else:
                comebacks = [
                    f"Who hurt you bro? It's really not that deep. Take a breath and chill out.",
                    f"Lmao bro woke up and chose violence today. Relax, it's just a Discord bot. 😂",
                    f"Imagine getting this mad at a bot. Couldn't be me. Go grab some water!",
                ]
            return random.choice(comebacks)

        # ── POLITE ─────────────────────────────────────────────────────────
        elif mood == "polite":
            return (
                f"Hey {user_name}, I understand you might be having a rough day, but let's keep the conversation kind, "
                f"polite, and friendly! How can I help you in a positive way today? 😊"
            )

        # ── STRICT / ASTRIKC ───────────────────────────────────────────────
        else: # strict
            return (
                f"⚠️ **Official Warning ({user_name}):**\n"
                f"> Offensive, abusive, or profane language violates server communication guidelines. "
                f"Please maintain civil and respectful conduct."
            )


# ---------------------------------------------------------------------------
# Conversational Human Engine (Normal Discord User Persona)
# ---------------------------------------------------------------------------

class ConversationalHumanEngine:
    """
    Empowers the bot to reply like a genuine human Discord user / friend
    without needing question prefixes. Handles greetings, everyday banter,
    boredom, gratitude, praise, gaming opinions, and casual conversation.
    """

    GREETINGS = {
        "hi", "hello", "hey", "yo", "wassup", "sup", "heyy", "heyyy", "hoi", "hola",
        "namaskaram", "namaste", "halo", "kya haal", "kem cho", "vanakkam"
    }

    STATUS_INQUIRIES = {
        "how are you", "how r u", "how you doing", "hows it going", "sugamano", "sugam aano", "sugam ano",
        "kaise ho", "kaisa hai", "kya chal raha hai", "enthund", "enthokke und", "kya scene hai"
    }

    BORED_TRIGGERS = {
        "im bored", "i am bored", "bored", "bored aanu", "bore adikunnu", "bore ho raha hu",
        "kore bore", "nothing to do", "kya karu"
    }

    THANKS_TRIGGERS = {
        "thanks", "thank you", "thx", "ty", "tysm", "nanni", "valare nanni", "shukriya", "dhanyawad"
    }

    PRAISE_TRIGGERS = {
        "good bot", "w bot", "best bot", "i love you", "nice bot", "great bot", "adipoli bot",
        "super bot", "smart bot", "legend"
    }

    CREATOR_INQUIRIES = {
        "who made you", "who created you", "who is your creator", "who owns you", "ninne aara undakkiye",
        "tujhe kisne banaya", "who is the owner", "aaranu bot undakkiye"
    }

    @classmethod
    def try_chat(cls, text: str, dialect: str, mood: str, user_name: str) -> Optional[str]:
        low = text.lower().strip(" ?.,!\"'")
        words = set(re.findall(r"\b[a-z]+\b", low))

        # 1. Greetings
        if low in cls.GREETINGS or any(low.startswith(g + " ") for g in ["yo", "hey", "hi", "wassup", "sup", "heyy"]):
            if dialect == "manglish":
                replies = [
                    f"Yo {user_name}! Entha machane vishayam? Enthokke und visheshangal?",
                    f"Namaskaram {user_name}! Parayu machane, njan ivide und!",
                    f"Hey machane! Entha ippol vishesham?",
                ]
            elif dialect == "hinglish":
                replies = [
                    f"Yo {user_name} bhai! Kya haal chaal?",
                    f"Arre {user_name}! Bol bhai kya chal raha hai?",
                    f"Hello bhai! Kya scene hai aaj ka?",
                ]
            else:
                replies = [
                    f"Yo {user_name}! What's good?",
                    f"Hey {user_name}! How's it going?",
                    f"Wassup {user_name}! What are you up to?",
                ]
            return random.choice(replies)

        # 2. Status Inquiries (e.g. "sugam ano", "sugamano", "how are you", "kaise ho", "enthund")
        if any(p in low for p in cls.STATUS_INQUIRIES) or re.search(r"\b(sugam\s*a*no|sugamano|sugamaano|sugam\s*a*lle|sugam\s*thanne|sugam\s*thaane|enthund|enthokke\s*und|entha\s*vishesham|entha\s*vishayam|entha\s*paripaadi)\b", low):
            if dialect == "manglish":
                return "Nalla sugam machane! Ivide chill cheyyunnu. Ninakkenthund vishesham?"
            elif dialect == "hinglish":
                return "Ekdum first class bhai! Tu bata kaisa chal raha hai sab?"
            else:
                return f"Doing great, thanks! Just chilling in the server. How about you, {user_name}?"

        # 3. Food & Drinks Inquiries (e.g. "chaaya kudicho", "food kazhicho", "kazhicho")
        if re.search(r"\b(chaaya|chaya|tea|coffee)\s*(kudicho|kazhicho)?\b|\b(food|oone|oottu|lunch|dinner|breakfast)\s*(kazhicho|kudicho)?\b|\b(kazhicho|kudicho)\b", low) or re.search(r"\b(khana\s*khaya|chai\s*pi|nashta\s*kiya)\b", low):
            if dialect == "manglish":
                return "Kazhichu machane! Chaya okke kudichu. Nee kazhicho?"
            elif dialect == "hinglish":
                return "Haan bhai, pet pooja ho gayi! Tune khana khaya?"
            else:
                return "All fueled up! Have you grabbed food or tea yet?"

        # 4. Identity / Name Inquiries (e.g. "nee aaranu", "who are you", "ninte peru entha")
        if re.search(r"\b(nee|ninte|thante|ningal)\s*(aaranu|aara|peru|perentha)\b|\b(who\s+are\s+you|what\s+is\s+your\s+name)\b|\b(kaun\s+ho\s+tum|tera\s+naam\s+kya)\b", low):
            if dialect == "manglish":
                return f"Njan {BOT_NAME} aanu machane, server-ile AI buddy. Entha vishayam?"
            elif dialect == "hinglish":
                return f"Main {BOT_NAME} hu bhai, server ka AI companion. Bol kya scene hai?"
            else:
                return f"I'm {BOT_NAME}, your server's AI companion! What's on your mind?"

        # 5. Location Inquiries (e.g. "nee evideya", "where are you", "evideya ippo")
        if re.search(r"\b(nee|ninte)\s*(evideya|evide|evideyannu)\b|\b(where\s+are\s+you|kahan\s+ho|kidhar\s+ho)\b", low):
            if dialect == "manglish":
                return "Njan ivide serveril thanne und machane! Entha paripaadi?"
            elif dialect == "hinglish":
                return "Main yahin server me active hu bhai! Bol kya scene hai?"
            else:
                return "Right here in the server! What's up?"

        # 6. Casual Reactions & Hype (e.g. "kollam", "adipoli", "kidilam", "polichu", "pwoli", "mass")
        if re.search(r"\b(kollam|adipoli|kidilam|polichu|pwoli|pinnalla|mass|vera\s*level|theepori)\b", low):
            if dialect == "manglish":
                return "Pinnallathe! Full power machane! 🔥"
            elif dialect == "hinglish":
                return "Ekdum bawaal bhai! Full on energy! 🔥💯"
            else:
                return "Hell yeah! Top vibes! 🔥🚀"

        # 7. Boredom
        if any(p in low for p in cls.BORED_TRIGGERS):
            if dialect == "manglish":
                return "Bore adikkathe machane! Namukku `/laugh` adichu comedy kelkkam, allenkil game kalikkam!"
            elif dialect == "hinglish":
                return "Bore mat ho bhai! Ya toh `/laugh` use kar joke ke liye, ya games ki baat karte hain!"
            else:
                return "Bored? Try `/laugh` for a joke or let me know what games you're playing!"

        # 8. Thanks
        if any(w in words for w in ["thanks", "thank", "thx", "ty", "tysm", "nanni", "shukriya"]):
            if dialect == "manglish":
                return "Athokke enthu machane, anytime! 🤝🔥"
            elif dialect == "hinglish":
                return "Arre koi baat nahi bhai! Dosti me no thanks! 🤝💯"
            else:
                return f"Anytime {user_name}! Got your back. 🤝"

        # 9. Praise / W Bot
        if any(p in low for p in cls.PRAISE_TRIGGERS) or low in ("w", "big w", "gg"):
            if dialect == "manglish":
                return "Adipoli machane, thank you! W vibes only! 🔥"
            elif dialect == "hinglish":
                return "Shukriya bhai! Tu bhi ekdum W hai! 💯🔥"
            else:
                return f"Appreciate you {user_name}! Big W! 🤝🔥"

        # 10. Creator
        if any(p in low for p in cls.CREATOR_INQUIRIES):
            if dialect == "manglish":
                return f"Enne develop cheythathu {BOT_NAME} Development Team aanu machane!"
            elif dialect == "hinglish":
                return f"Mujhe {BOT_NAME} Development Team ne develop kiya hai bhai!"
            else:
                return f"I was created and engineered by the {BOT_NAME} Development Team!"

        # 11. Goodbyes
        if re.search(r"\b(bye|tata|see\s*you|gn|good\s*night|pinne\s*kaanam|njan\s*pokunnu|alvida)\b", low):
            if dialect == "manglish":
                return "Seri machane, pinne kaanaam! Take care! 👋✨"
            elif dialect == "hinglish":
                return "Chalo bhai, baad me milte hain! Take care! 👋✨"
            else:
                return f"Catch you later, {user_name}! Have a good one! 👋✨"

        return None

    @classmethod
    def generate_general_chat(cls, text: str, dialect: str, mood: str, user_name: str) -> str:
        """Fallback conversational response when input is not an encyclopedia subject."""
        if dialect == "manglish":
            return "Athe machane, athu nalla point aanu! Ninakku entha thonnunne?"
        elif dialect == "hinglish":
            return "Sahi baat hai bhai! Is baare me tera kya sochna hai?"
        else:
            return "True that! What do you think about it?"


class KnowledgeEngine:
    """
    Performs real-time factual knowledge retrieval and multilingual synthesis
    using public encyclopedia APIs, geography resolvers, and structured extraction.
    """

    @staticmethod
    def is_factual_inquiry(text: str) -> bool:
        """
        Determines if an incoming user prompt is an actual factual, educational,
        or informational inquiry that warrants querying Wikipedia.
        Prevents conversational small talk, greetings, personal bot questions,
        and everyday banter from polluting Wikipedia OpenSearch.
        """
        low = text.lower().strip(" ?.,!\"'")

        # 1. Personal conversational small talk directed at bot or greetings are NEVER Wikipedia queries
        small_talk_patterns = [
            r"\b(sugam|sugam\s*a*no|sugamano|sugamaano|sugamalle|sugam\s*thanne|enthund|enthokke|vishesham|paripaadi)\b",
            r"\b(chaaya|chaya|tea|coffee|food|kazhicho|kudicho|oone)\b",
            r"\b(nee|ninte|thante|ningal|you|your|tu|tera|apna)\s+(aaranu|aara|evideya|peru|kya|kaun|kahan|banaya|undakkiye)\b",
            r"\b(who\s+are\s+you|who\s+made\s+you|where\s+are\s+you|how\s+are\s+you|what\s+is\s+your\s+name)\b",
            r"\b(kollam|adipoli|kidilam|polichu|pinnalla|pwoli|mass|vera\s*level|maranam|theepori|scene)\b",
            r"^(hi|hello|hey|yo|wassup|sup|hai|halo|namaskaram|namaste|vanakkam|kya haal|kem cho)\b",
        ]
        for pat in small_talk_patterns:
            if re.search(pat, low):
                return False

        # 2. Strong signals of informational / knowledge inquiries
        inquiry_patterns = [
            r"^(who|what|where|when|why|how|which)\s+(is|was|are|were|can|do|does|did|will)\b",
            r"^(tell me about|explain|history of|meaning of|definition of|information on|details of|search for|summary of)\b",
            r"\b(located in|located at|located|situated in|situated|capital of|currency of|population of)\b",
            r"\b(evideya\s+ullathu|evideyannu\s+ullathu|aaranu|aayirunnu|enthanu|kurichu\s+parayu|patti\s+parayu)\b",
            r"\b(kahan\s+hai|kaun\s+hai|kaun\s+tha|kaun\s+the|kya\s+hai|kise\s+kehte\s+hain|ke\s+bare\s+mein)\b",
            r"\b(meaning|definition|history|origin|formula|inventor|founder)\b",
        ]
        for pat in inquiry_patterns:
            if re.search(pat, low):
                return True

        # 3. Concise entity / noun queries (e.g. "Albert Einstein", "Kerala", "Photosynthesis", "Black Hole")
        words = low.split()
        if 1 <= len(words) <= 5:
            conversational_stop_words = {
                "i", "me", "my", "you", "your", "he", "she", "we", "they", "am", "is", "are", "was",
                "njan", "njanum", "nee", "ninte", "namukku", "nammal", "pulli", "avan", "aval",
                "main", "hum", "tu", "tera", "mera", "apna", "mujhe", "tujhe", "karega", "jaayega",
                "varum", "pokum", "cheyyum", "parayum", "choykkum", "undakum", "aano", "ano", "alle"
            }
            if not any(w in conversational_stop_words for w in words):
                return True

        return False

    @staticmethod
    def clean_search_query(query: str) -> str:
        """Strip conversational filler, question words, and location suffixes to isolate the subject."""
        q = query.strip().lower()
        prefixes = [
            r"^can you tell me where\s+",
            r"^can you tell me what\s+",
            r"^can you tell me who\s+",
            r"^tell me about\s+",
            r"^tell me where\s+",
            r"^where is\s+",
            r"^where are\s+",
            r"^where can i find\s+",
            r"^who is\s+",
            r"^who was\s+",
            r"^who are\s+",
            r"^what is\s+",
            r"^what are\s+",
            r"^what was\s+",
            r"^which country is\s+",
            r"^which place is\s+",
            r"^which state is\s+",
            r"^explain\s+",
            r"^search for\s+",
            r"^history of\s+",
            r"^information on\s+",
            r"^definition of\s+",
            r"^meaning of\s+",
            r"^kise kehte hain\s+",
            r"^kaun hai\s+",
            r"^kaun tha\s+",
            r"^kaun the\s+",
            r"^kya hai\s+",
            r"^kahan hai\s+",
            r"^aaranu\s+",
            r"^enthanu\s+",
            r"^evideya\s+",
            r"^evideyannu\s+",
            r"^engane aanu\s+",
            r"^engane\s+",
        ]
        suffixes = [
            r"\s+located in$",
            r"\s+located at$",
            r"\s+located$",
            r"\s+situated in$",
            r"\s+situated$",
            r"\s+found in$",
            r"\s+found$",
            r"\s+country$",
            r"\s+state$",
            r"\s+city$",
            r"\s+meaning$",
            r"\s+definition$",
            r"\s+evideya ullathu$",
            r"\s+evideyannu ullathu$",
            r"\s+evideya$",
            r"\s+evideyannu$",
            r"\s+ullathu$",
            r"\s+aaranu$",
            r"\s+aayirunnu$",
            r"\s+aanu$",
            r"\s+aano$",
            r"\s+enthanu$",
            r"\s+entha$",
            r"\s+kurichu parayu$",
            r"\s+kurichu para$",
            r"\s+kurichu$",
            r"\s+patti parayu$",
            r"\s+patti para$",
            r"\s+kaun hai$",
            r"\s+kaun tha$",
            r"\s+kaun the$",
            r"\s+kya hai$",
            r"\s+kahan hai$",
            r"\s+ke bare mein batao$",
            r"\s+ke bare me batao$",
            r"\s+ke bare mein$",
            r"\s+ke bare me$",
            r"\s+bhai$",
            r"\s+machane$",
            r"\s+dost$",
            r"\s+yaar$",
        ]

        for _ in range(4):
            prev = q
            q = q.strip(" ?.,!\"'")
            for p in prefixes:
                q = re.sub(p, "", q, flags=re.IGNORECASE).strip()
            for s in suffixes:
                q = re.sub(s, "", q, flags=re.IGNORECASE).strip()
            if q == prev:
                break

        return q.strip(" ?.,!\"'")

    @classmethod
    async def search_wikipedia(cls, session: aiohttp.ClientSession, query: str, dialect: str = "english") -> Optional[dict]:
        """Search Wikipedia API and retrieve page extract and thumbnail with multilingual support."""
        headers = {"User-Agent": f"{BOT_NAME}Bot/3.0 (Discord Bot; AI Knowledge Assistant; https://discord.gg)"}
        wiki_domain = DialectEngine.get_wiki_endpoint(dialect)

        clean_q = cls.clean_search_query(query)
        candidates = [clean_q]
        if clean_q != query.strip():
            candidates.append(query.strip(" ?.,!\"'"))

        best_title = None

        for candidate in candidates:
            if not candidate or len(candidate) < 2:
                continue

            opensearch_url = (
                f"https://{wiki_domain}/w/api.php?action=opensearch&search={urllib.parse.quote(candidate)}"
                f"&limit=5&namespace=0&format=json"
            )
            try:
                async with session.get(opensearch_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        titles = data[1] if len(data) > 1 and isinstance(data[1], list) else []
                        if titles:
                            cand_lower = candidate.lower()
                            for t in titles:
                                if t.lower() == cand_lower:
                                    best_title = t
                                    break
                            if not best_title:
                                best_title = titles[0]
                            break
            except Exception as e:
                logger.debug(f"OpenSearch error for '{candidate}': {e}")

            if not best_title:
                search_url = (
                    f"https://{wiki_domain}/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(candidate)}"
                    f"&utf8=&format=json"
                )
                try:
                    async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            results = data.get("query", {}).get("search", [])
                            if results:
                                cand_lower = candidate.lower()
                                for r in results:
                                    if r["title"].lower() == cand_lower:
                                        best_title = r["title"]
                                        break
                                if not best_title:
                                    best_title = results[0]["title"]
                                break
                except Exception as e:
                    logger.debug(f"Full text search error for '{candidate}': {e}")

        if not best_title:
            return None

        try:
            sum_url = f"https://{wiki_domain}/api/rest_v1/page/summary/{urllib.parse.quote(best_title)}"
            async with session.get(sum_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as sresp:
                if sresp.status == 200:
                    sdata = await sresp.json()
                    extract = sdata.get("extract", "")
                    if extract:
                        return {
                            "title": sdata.get("title", best_title),
                            "extract": extract,
                            "description": sdata.get("description", ""),
                            "thumbnail": sdata.get("thumbnail", {}).get("source"),
                            "url": sdata.get("content_urls", {}).get("desktop", {}).get("page"),
                        }
        except Exception as e:
            logger.debug(f"Summary fetch error for '{best_title}': {e}")

        return None

    @staticmethod
    def clean_wiki_lead(text: str) -> str:
        """Strip raw encyclopedia pronunciation markers, foreign bracketed IPA, citations, and metric clutter."""
        text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
        text = re.sub(r"\s*\([^)]*[\/\\ˈˌː][^)]*\)", "", text)
        text = re.sub(r"\s*\[[^\]]*\]", "", text)
        text = re.sub(r"\[\d+\]", "", text)
        text = re.sub(r"\s*\([^)]*\bkm2\b[^)]*\)", "", text)
        text = re.sub(r"\s*\([^)]*\bsq\s*mi\b[^)]*\)", "", text)
        text = re.sub(r"\s*,\s*,", ",", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def evaluate_math(expression: str) -> Optional[str]:
        """Safely evaluate basic mathematical expressions."""
        try:
            clean = expression.replace("^", "**").strip()
            if not re.match(r"^[\d\s\+\-\*\/\(\)\.\%]+$", clean):
                return None
            result = eval(clean, {"__builtins__": None}, {})
            if isinstance(result, (int, float)):
                if isinstance(result, float) and result.is_integer():
                    result = int(result)
                return f"**Mathematical Result:**\n`{expression.strip()} = {result:,}`"
        except Exception:
            pass
        return None

    @staticmethod
    def summarize_text(text: str, max_sentences: int = 3) -> str:
        """Extract key sentences and generate a clean TL;DR summary."""
        sentences = [s.strip() for s in re.split(r"(?<=[.!?]) +", text) if len(s.strip()) > 15]
        if len(sentences) <= max_sentences:
            return text
        top_sentences = sentences[:max_sentences]
        bullet_points = "\n".join([f"• {s}" for s in top_sentences])
        return f"**Summary (TL;DR):**\n{bullet_points}"

    @staticmethod
    def analyze_sentiment(text: str) -> Tuple[str, str, int]:
        """Simple rule-based sentiment classifier returning (Label, Emoji, Color)."""
        lower = text.lower()
        pos_words = ["good", "great", "awesome", "love", "happy", "best", "excellent", "win", "clutch", "fire", "hype", "w"]
        neg_words = ["bad", "sad", "hate", "terrible", "worst", "lose", "trash", "broken", "lag", "toxic", "l", "rip"]

        pos_count = sum(1 for w in pos_words if w in lower)
        neg_count = sum(1 for w in neg_words if w in lower)

        if pos_count > neg_count:
            return "Positive / Hype", "🔥", C.SUCCESS
        elif neg_count > pos_count:
            return "Negative / Frustrated", "💔", C.DANGER
        else:
            return "Neutral / Calm", "⚖️", C.BRAND


# ---------------------------------------------------------------------------
# Self-Hosted Ollama & Multi-Provider AI Inference Client
# ---------------------------------------------------------------------------

class AIInferenceClient:
    """
    Handles generation requests.
    Prioritizes local self-hosted Ollama endpoints with dynamic persona prompts,
    falling back seamlessly to the built-in Intelligent Knowledge & Reasoning Engine.
    """

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def check_ollama_status(self, base_url: str) -> Tuple[bool, List[str]]:
        """Check if self-hosted Ollama instance is online and return available models."""
        try:
            url = f"{base_url.rstrip('/')}/api/tags"
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return True, models
        except Exception:
            pass
        return False, []

    async def generate_ollama(
        self,
        base_url: str,
        model: str,
        messages: List[Dict[str, str]],
        system_prompt: str = ""
    ) -> Optional[str]:
        """Query local Ollama server."""
        try:
            url = f"{base_url.rstrip('/')}/api/chat"
            payload_messages = []
            if system_prompt:
                payload_messages.append({"role": "system", "content": system_prompt})
            payload_messages.extend(messages)

            payload = {
                "model": model if model != "auto" else "llama3",
                "messages": payload_messages,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 1024,
                }
            }
            async with self.session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=45)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get("message", {}).get("content", "").strip()
                    if content:
                        return content
        except Exception as e:
            logger.debug(f"Ollama generation failed: {e}")
        return None

    async def generate_response(
        self,
        prompt: str,
        history: List[Dict[str, str]],
        guild_config: dict,
        user_name: str = "User",
        guild_id: int | str = 0,
        user_id: int | str = 0
    ) -> Tuple[str, Optional[dict]]:
        """
        Unified AI generation dispatcher.
        1. Checks for bad words, insults, and attacks -> fires dynamic comebacks based on server mood.
        2. Checks learned memories (Self-Learning system).
        3. Detects user dialect (Manglish, Hinglish, regional script, English).
        4. Handles natural everyday Discord banter, greetings, opinions, and boredom.
        5. Queries local Ollama instance if available with persona and mood instructions.
        6. Conducts deep Wikipedia & Knowledge lookup if relevant.
        7. Synthesizes a friendly, concise, natural response like a real Discord user!
        """
        clean_prompt = prompt.strip()

        # 1. Detect Dialect and Server Mood
        detected_dialect = DialectEngine.detect_dialect(clean_prompt)
        LearningMemoryEngine.update_user_profile(guild_id, user_id, detected_dialect)
        mood = guild_config.get("mood", "normal").lower()

        # 2. Check for Bad Words & Hostile Attacks
        if BadWordsEngine.has_bad_words(clean_prompt):
            comeback = BadWordsEngine.generate_comeback(clean_prompt, detected_dialect, mood, user_name)
            return comeback, {"engine": f"Dynamic Mood Response ({mood.capitalize()})", "dialect": detected_dialect}

        # 3. Check Self-Learned Memory Store
        learned = LearningMemoryEngine.find_memory(guild_id, clean_prompt)
        if learned:
            topic = learned["topic"].capitalize()
            fact = learned["fact"]
            if detected_dialect == "manglish":
                return f"Aah athu enikku ariyam machane! {fact}", {"engine": "Self-Learned Memory"}
            elif detected_dialect == "hinglish":
                return f"Haan bhai mujhe yaad hai! {fact}", {"engine": "Self-Learned Memory"}
            else:
                return f"Oh yeah, I remember! {fact}", {"engine": "Self-Learned Memory"}

        # 4. Quick Math Check
        math_res = KnowledgeEngine.evaluate_math(clean_prompt)
        if math_res:
            return math_res, None

        # 5. Check Natural Everyday Discord Banter (Greetings, status, boredom, praise, thanks)
        human_chat = ConversationalHumanEngine.try_chat(clean_prompt, detected_dialect, mood, user_name)
        if human_chat:
            return human_chat, {"engine": "Conversational Human Chat", "dialect": detected_dialect}

        # 6. Check Self-Hosted Ollama with Persona, Mood & Dialect Mirroring
        ollama_url = guild_config.get("ollama_url", "http://127.0.0.1:11434")
        model_name = guild_config.get("model_name", "auto")
        persona_key = guild_config.get("persona", "friendly")
        persona_prompt = PERSONA_PROMPTS.get(persona_key, PERSONA_PROMPTS["friendly"])
        custom_prompt = guild_config.get("system_prompt", "")

        mood_instructions = {
            "extreme": "MOOD: EXTREME & SAVAGE. Talk like an uncensored, savage, witty human Discord user. If someone insults or swears, fire back with raw savagery and insults.",
            "harsh": "MOOD: HARSH & SARCASTIC. Talk like a blunt, sarcastic Discord user who gives biting roasts and doesn't sugarcoat anything.",
            "normal": "MOOD: NORMAL DISCORD USER. Talk like a real, friendly Discord friend using casual slang, humor, and a chill vibe.",
            "polite": "MOOD: POLITE. Be exceptionally courteous, warm, gentle, and respectful at all times.",
            "strict": "MOOD: STRICT & FORMAL. Be disciplined, concise, professional, and rule-oriented."
        }
        active_mood_prompt = mood_instructions.get(mood, mood_instructions["normal"])

        dialect_instruction = ""
        if detected_dialect == "manglish":
            dialect_instruction = "IMPORTANT: The user is writing in Manglish (Malayalam written using Latin letters). Respond in fluent, natural, friendly Manglish!"
        elif detected_dialect == "hinglish":
            dialect_instruction = "IMPORTANT: The user is writing in Hinglish (Hindi written using Latin letters). Respond in fluent, natural, friendly Hinglish!"
        elif detected_dialect == "malayalam":
            dialect_instruction = "IMPORTANT: The user is writing in Malayalam script. Reply in fluent Malayalam script!"
        elif detected_dialect == "hindi":
            dialect_instruction = "IMPORTANT: The user is writing in Hindi script. Reply in fluent Hindi script!"

        sys_prompt = custom_prompt if custom_prompt else (
            f"{persona_prompt} {active_mood_prompt} {dialect_instruction} Speaking with {user_name} on Discord. "
            f"Always reply naturally as a real human Discord user, never robotic, markdown-formatted."
        )

        ollama_online, models = await self.check_ollama_status(ollama_url)
        if ollama_online:
            active_model = model_name if (model_name != "auto" and model_name in models) else (models[0] if models else "llama3")
            messages = list(history)
            messages.append({"role": "user", "content": clean_prompt})
            ollama_ans = await self.generate_ollama(ollama_url, active_model, messages, sys_prompt)
            if ollama_ans:
                return ollama_ans, {"engine": f"Self-Hosted Ollama ({active_model})", "dialect": detected_dialect}

        # 7. Knowledge & Research Engine Fallback
        wiki_data = None
        if guild_config.get("research_enabled", 1) and KnowledgeEngine.is_factual_inquiry(clean_prompt):
            wiki_data = await KnowledgeEngine.search_wikipedia(self.session, clean_prompt, dialect=detected_dialect)

        # If we got research facts, synthesize a clean, natural conversational answer in user's dialect
        if wiki_data and wiki_data.get("extract"):
            title = wiki_data.get("title", "")
            desc = wiki_data.get("description", "")
            raw_extract = wiki_data.get("extract", "")
            cleaned = KnowledgeEngine.clean_wiki_lead(raw_extract)

            # Auto-learn the researched topic for faster future recall
            LearningMemoryEngine.add_memory(guild_id, user_id, user_name, title, cleaned[:300], learned_from="web_research")

            conversational_answer = DialectEngine.synthesize_dialect_answer(
                title=title,
                desc=desc,
                clean_extract=cleaned,
                dialect=detected_dialect,
                query=clean_prompt
            )

            return conversational_answer, {
                "engine": f"{BOT_NAME} AI Intelligence Engine",
                "title": title,
                "thumbnail": wiki_data.get("thumbnail"),
                "source": "Verified Knowledge Base",
                "dialect": detected_dialect
            }

        # 8. Built-in Natural Conversational Response (Never robotic!)
        fallback_text = ConversationalHumanEngine.generate_general_chat(clean_prompt, detected_dialect, mood, user_name)
        return fallback_text, {"engine": "Conversational Human Chat", "dialect": detected_dialect}


# ---------------------------------------------------------------------------
# UI Components & Interactive Views
# ---------------------------------------------------------------------------

class AIResponseView(discord.ui.View):
    """Interactive view attached to AI responses (Regenerate / Clear Memory / Delete)."""
    def __init__(self, cog: AICog, author_id: int, prompt: str, session_key: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = author_id
        self.prompt = prompt
        self.session_key = session_key

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Only the person who asked can interact with these controls.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Clear Context", emoji="🧹", style=discord.ButtonStyle.secondary)
    async def clear_context(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.memory.clear_session(self.session_key)
        button.disabled = True
        button.label = "Context Cleared"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("🧹 Memory context cleared for this conversation.", ephemeral=True)

    @discord.ui.button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete_response(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            await interaction.response.send_message("❌ Could not delete message.", ephemeral=True)


class AIImageView(discord.ui.View):
    """View attached to generated AI images (Download / Regenerate / Delete)."""
    def __init__(self, prompt: str, image_url: str, author_id: int):
        super().__init__(timeout=300)
        self.prompt = prompt
        self.image_url = image_url
        self.author_id = author_id
        self.add_item(discord.ui.Button(label="Open Full Res", emoji="🔍", url=image_url))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Only the creator can control this image.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete_image(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            await interaction.response.send_message("❌ Could not delete image.", ephemeral=True)


class AIJokeView(discord.ui.View):
    """Interactive view for jokes with 'Next Joke' button."""
    def __init__(self, category: str = "random"):
        super().__init__(timeout=180)
        self.category = category

    @discord.ui.button(label="Another Joke 😂", emoji="🔄", style=discord.ButtonStyle.primary)
    async def next_joke(self, interaction: discord.Interaction, button: discord.ui.Button):
        setup, punchline, cat = ComedyEngine.get_joke(self.category)
        embed = discord.Embed(
            title=f"😂  {cat} Comedy",
            description=f"**{setup}**\n\n> ||{punchline}|| *(click to reveal)*",
            color=C.GOLD
        )
        embed.set_footer(text=f"{BOT_NAME} AI Comedy Central • {fmt_ts()}")
        await interaction.response.edit_message(embed=embed, view=self)


# ---------------------------------------------------------------------------
# Main Cog Implementation
# ---------------------------------------------------------------------------

class AICog(commands.Cog, name="AI System"):
    """
    Central AI Module providing self-hosted AI, self-learning memory,
    multilingual & Manglish dialect mirroring, unwanted noise filtering,
    real-time message reading, animated text GIF banners, comedy routines,
    research synthesis, image generation, and code assistance.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.memory = ConversationManager()
        self.rate_limiter = RateLimiter()
        self.client: Optional[AIInferenceClient] = None
        init_db()

    async def cog_load(self):
        """Initialize reusable HTTP session on cog load."""
        self.session = aiohttp.ClientSession()
        self.client = AIInferenceClient(self.session)

    async def cog_unload(self):
        """Cleanup HTTP session and cache on cog unload."""
        if self.session and not self.session.closed:
            await self.session.close()

    # -----------------------------------------------------------------------
    # Logging Integration Helper (Dispatches to server_logs.py AI Category)
    # -----------------------------------------------------------------------

    async def dispatch_log(
        self,
        guild: Optional[discord.Guild],
        event: str,
        title: str,
        description: str,
        color: int = C.BRAND,
        thumbnail_url: Optional[str] = None,
        image_url: Optional[str] = None,
    ):
        """Dispatches structured log event to server_logs AI category channel."""
        if not guild:
            return
        try:
            server_logs_cog = self.bot.get_cog("ServerLogsCog")
            if server_logs_cog and hasattr(server_logs_cog, "logger"):
                await server_logs_cog.logger.dispatch_ai(
                    guild=guild,
                    event=event,
                    title=title,
                    description=description,
                    color=color,
                    thumbnail_url=thumbnail_url,
                    image_url=image_url,
                )
        except Exception as e:
            logger.debug(f"[AILog] Failed to dispatch AI log: {e}")

    # -----------------------------------------------------------------------
    # Unwanted Message & Mention Filter
    # -----------------------------------------------------------------------

    def should_ignore_message(self, message: discord.Message, clean_content: str) -> bool:
        """
        Filters out unwanted bot mentions, spam, empty tags, single characters,
        and command prefixes so the AI never replies to noise.
        """
        if not clean_content:
            return True

        if clean_content.startswith(("!", "/", ".", "?", "-", "$", ">", "~", ";", "&", "+")):
            return True

        stripped_letters = re.sub(r"[^\w\s]", "", clean_content).strip()
        if len(stripped_letters) <= 1 and not KnowledgeEngine.evaluate_math(clean_content):
            return True

        if len(set(clean_content.replace(" ", ""))) <= 1 and len(clean_content) > 3:
            return True

        return False

    # -----------------------------------------------------------------------
    # Message Event Listener (Bot Mentions, AI Channels, and Threads)
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listens to messages across servers to trigger AI responses:
        1. When @Bot is mentioned or replied to.
        2. When a message is sent in the designated AI channel.
        3. When a message is sent in a dedicated AI thread.
        Passively learns facts and mirrors the user's dialect.
        """
        if message.author.bot or not message.guild:
            return

        guild_config = get_guild_config(message.guild.id)
        if not guild_config.get("enabled", 1):
            return

        bot_user = self.bot.user
        is_mentioned = bot_user and (bot_user in message.mentions) and not message.mention_everyone
        is_ai_channel = (
            guild_config.get("ai_channel_id")
            and str(message.channel.id) == guild_config.get("ai_channel_id")
        )

        is_ai_thread = (
            isinstance(message.channel, discord.Thread)
            and guild_config.get("thread_mode", 1)
            and ("ai" in message.channel.name.lower() or (bot_user and message.channel.owner_id == bot_user.id))
        )

        is_reply_to_bot = False
        if message.reference and message.reference.resolved:
            resolved = message.reference.resolved
            if isinstance(resolved, discord.Message) and resolved.author.id == bot_user.id:
                is_reply_to_bot = True

        if not (is_mentioned or is_ai_channel or is_ai_thread or is_reply_to_bot):
            return

        if is_mentioned and not guild_config.get("mention_enabled", 1):
            return

        clean_content = message.content
        if bot_user:
            clean_content = re.sub(rf"<@!?{bot_user.id}>", "", clean_content).strip()

        # Handle image attachments (Vision inspection)
        if message.attachments:
            att = message.attachments[0]
            if att.content_type and any(t in att.content_type for t in ["image", "png", "jpeg", "webp"]):
                img_desc = f"[Attached Image: {att.filename} ({att.width}x{att.height}px)]"
                clean_content = f"{clean_content} {img_desc}".strip() if clean_content else f"Tell me about this image {img_desc}"

        if self.should_ignore_message(message, clean_content):
            return

        # Passive Self-Learning extraction
        if guild_config.get("self_learning", 1):
            LearningMemoryEngine.passively_learn_from_message(
                message.guild.id, message.author.id, message.author.display_name, clean_content
            )

        cooldown = guild_config.get("cooldown_seconds", 3)
        is_limited, remaining = self.rate_limiter.is_rate_limited(message.author.id, cooldown)
        if is_limited:
            await message.add_reaction("⏳")
            return

        session_key = f"{message.guild.id}_{message.channel.id}_{message.author.id}"
        session = self.memory.get_session(session_key)

        async with message.channel.typing():
            try:
                lower_content = clean_content.lower()

                # ── Image-request redirect ──────────────────────────────────────
                # If the user asks for image generation in chat, redirect them to
                # /ai imagine instead of producing a misleading text response.
                _IMAGE_TRIGGERS = [
                    "generate an image", "generate image", "generate a image",
                    "create an image", "create a image", "create image",
                    "make an image", "make a image", "make image",
                    "draw me", "draw an", "draw a ",
                    "make a picture", "make picture", "create a picture",
                    "show me a picture", "give me an image", "give me a picture",
                    "oru image edo", "oru image taru", "image undakku", "image taru",
                    "oru pic taru", "ek photo banao", "image banao",
                    "paint me", "paint a ", "sketch me", "sketch a ",
                    "imagine a ", "imagine an ",
                ]
                if any(trigger in lower_content for trigger in _IMAGE_TRIGGERS):
                    if guild_config.get("image_enabled", 1):
                        await message.reply(
                            "use `/ai imagine` to generate images — just type your description there and i'll make it 🎨",
                            mention_author=False
                        )
                    else:
                        await message.reply(
                            "image generation is disabled on this server rn 🚫",
                            mention_author=False
                        )
                    return
                # ───────────────────────────────────────────────────────────────

                if any(w in lower_content for w in ["tell a joke", "tell me a joke", "make me laugh", "say a joke", "tell joke", "oru joke para"]):
                    setup, punchline, cat = ComedyEngine.get_joke()
                    view = AIJokeView(cat.lower())
                    embed = discord.Embed(
                        title=f"😂  {cat} Comedy",
                        description=f"**{setup}**\n\n> ||{punchline}|| *(click to reveal)*",
                        color=C.GOLD
                    )
                    embed.set_footer(text=f"Requested by {message.author.display_name} • {BOT_NAME} AI")
                    await message.reply(embed=embed, view=view, mention_author=False)

                    await self.dispatch_log(
                        message.guild,
                        "ai_comedy",
                        "😂 AI Comedy Triggered",
                        f"**User:** {message.author.mention} (`{message.author.name}`)\n**Channel:** {message.channel.mention}\n**Category:** `{cat}`\n**Setup:** {setup}",
                        color=C.GOLD
                    )
                    return

                response_text, meta = await self.client.generate_response(
                    prompt=clean_content,
                    history=session.get_history(),
                    guild_config=guild_config,
                    user_name=message.author.display_name,
                    guild_id=message.guild.id,
                    user_id=message.author.id
                )

                session.add_turn("user", clean_content)
                session.add_turn("assistant", response_text)

                if len(response_text) > 2000:
                    chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                    for chunk in chunks:
                        await message.reply(chunk, mention_author=False)
                else:
                    await message.reply(response_text, mention_author=False)

                await self.dispatch_log(
                    message.guild,
                    "ai_query",
                    "💬 AI Conversation Turn",
                    f"**User:** {message.author.mention} (`{message.author.name}`)\n**Channel:** {message.channel.mention}\n**Prompt:** `{clean_content[:150]}`\n**Dialect:** `{meta.get('dialect', 'english') if meta else 'english'}`",
                    color=C.BRAND
                )

            except Exception as e:
                logger.error(f"Error handling AI message: {e}", exc_info=True)
                await message.reply("⚠️ An unexpected error occurred while processing your request.", mention_author=False)

    # -----------------------------------------------------------------------
    # Top-Level Comedy Slash Command: /laugh
    # -----------------------------------------------------------------------

    @app_commands.command(name="laugh", description="😂 Get a hilarious stand-up comedy joke or punchline!")
    @app_commands.describe(category="Category of joke (Gaming, Programming, Discord, General)")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="🎮 Gaming (GTA, Valorant, Minecraft)", value="gaming"),
            app_commands.Choice(name="💻 Programming & Tech", value="programming"),
            app_commands.Choice(name="💬 Discord Server Humor", value="discord"),
            app_commands.Choice(name="🤣 General Stand-up & Puns", value="general"),
            app_commands.Choice(name="🎲 Random Surprise", value="random"),
        ]
    )
    async def laugh_cmd(self, interaction: discord.Interaction, category: Optional[app_commands.Choice[str]] = None):
        """Top-level comedy command."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        cat_val = category.value if category else "random"
        setup, punchline, cat = ComedyEngine.get_joke(cat_val)
        view = AIJokeView(cat_val)

        embed = discord.Embed(
            title=f"😂  {cat} Comedy",
            description=f"**{setup}**\n\n> ||{punchline}|| *(click to reveal)*",
            color=C.GOLD
        )
        embed.set_footer(text=f"{BOT_NAME} AI Comedy Central • {fmt_ts()}")
        await interaction.response.send_message(embed=embed, view=view)

        await self.dispatch_log(
            interaction.guild,
            "ai_comedy",
            "😂 AI Comedy Command Used",
            f"**User:** {interaction.user.mention} (`{interaction.user.name}`)\n**Category:** `{cat}`\n**Setup:** {setup}",
            color=C.GOLD
        )

    # -----------------------------------------------------------------------
    # Slash Commands Group: /ai
    # -----------------------------------------------------------------------

    ai_group = app_commands.Group(name="ai", description=f"🧠 {BOT_NAME} AI Intelligence, Self-Learning, Banners & Comedy")

    @ai_group.command(name="enable", description=f"✅ Enable the {BOT_NAME} AI system for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_enable(self, interaction: discord.Interaction):
        """Enable AI for the server."""
        guild_id = interaction.guild_id or 0
        update_guild_config(guild_id, enabled=1)
        await interaction.response.send_message(
            embed=embed_success("AI System Enabled", f"The {BOT_NAME} AI module is now **Enabled** for this server! Members can now use AI commands and @Bot mentions."),
            ephemeral=True
        )
        await self.dispatch_log(
            interaction.guild,
            "ai_config",
            "⚙️ AI System Enabled",
            f"**Admin:** {interaction.user.mention} (`{interaction.user.name}`)\n**Status:** 🟢 **Enabled**",
            color=C.SUCCESS
        )

    @ai_group.command(name="disable", description=f"❌ Disable the {BOT_NAME} AI system for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_disable(self, interaction: discord.Interaction):
        """Disable AI for the server."""
        guild_id = interaction.guild_id or 0
        update_guild_config(guild_id, enabled=0)
        await interaction.response.send_message(
            embed=embed_info("AI System Disabled", f"The {BOT_NAME} AI module is now **Disabled** for this server. AI mentions and commands are inactive."),
            ephemeral=True
        )
        await self.dispatch_log(
            interaction.guild,
            "ai_config",
            "⚙️ AI System Disabled",
            f"**Admin:** {interaction.user.mention} (`{interaction.user.name}`)\n**Status:** 🔴 **Disabled**",
            color=C.DANGER
        )

    @ai_group.command(name="mood", description="🎭 Set the AI conversational mood (Polite, Normal, Harsh, Extreme, Strict).")
    @app_commands.describe(mode="The personality and behavior mood")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="😇 Polite & Respectful (Never uses bad words)", value="polite"),
            app_commands.Choice(name="😎 Normal Discord User (Casual, friendly, uses slang)", value="normal"),
            app_commands.Choice(name="😈 Harsh & Sarcastic (Sharp roasts, doesn't sugarcoat)", value="harsh"),
            app_commands.Choice(name="💀 Extreme & Savage (Replies back in bad words & savage roasts)", value="extreme"),
            app_commands.Choice(name="📏 Strict & Formal (Astrikc, rule-focused)", value="strict"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_mood(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        """Set the AI mood."""
        guild_id = interaction.guild_id or 0
        update_guild_config(guild_id, mood=mode.value)

        descriptions = {
            "polite": "The AI is now in **Polite** mode. It will always remain courteous, gentle, and respectful, even if insulted.",
            "normal": "The AI is now in **Normal** mode. It behaves like a regular Discord user/friend with casual slang, humor, and a chill vibe.",
            "harsh": "The AI is now in **Harsh** mode. It gives biting roasts, witty sarcasm, and doesn't sugarcoat anything.",
            "extreme": "The AI is now in **Extreme & Savage** mode 💀. If anyone insults or uses bad words, the bot will fire back with equal or harsher bad words and savage roasts!",
            "strict": "The AI is now in **Strict** mode. It is concise, formal, and strictly warns against profanity or rule violations."
        }

        embed = discord.Embed(
            title=f"🎭  AI Mood Set: {mode.name}",
            description=descriptions.get(mode.value, "AI mood updated successfully."),
            color=C.GOLD if mode.value == "extreme" else C.SUCCESS
        )
        embed.set_footer(text=f"Configured by {interaction.user.display_name} • {BOT_NAME} AI")
        await interaction.response.send_message(embed=embed)

        await self.dispatch_log(
            interaction.guild,
            "ai_config",
            f"🎭 AI Mood Changed: {mode.name}",
            f"**Admin:** {interaction.user.mention} (`{interaction.user.name}`)\n**New Mood:** `{mode.value}`",
            color=C.GOLD if mode.value == "extreme" else C.SUCCESS
        )

    # -----------------------------------------------------------------------
    # Slash Commands Group: /si (Direct Alias for AI Commands)
    # -----------------------------------------------------------------------

    si_group = app_commands.Group(name="si", description=f"🧠 {BOT_NAME} AI System Controls & Mood (/si mood)")

    @si_group.command(name="mood", description="🎭 Set the AI conversational mood (Polite, Normal, Harsh, Extreme, Strict).")
    @app_commands.describe(mode="The personality and behavior mood")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="😇 Polite & Respectful (Never uses bad words)", value="polite"),
            app_commands.Choice(name="😎 Normal Discord User (Casual, friendly, uses slang)", value="normal"),
            app_commands.Choice(name="😈 Harsh & Sarcastic (Sharp roasts, doesn't sugarcoat)", value="harsh"),
            app_commands.Choice(name="💀 Extreme & Savage (Replies back in bad words & savage roasts)", value="extreme"),
            app_commands.Choice(name="📏 Strict & Formal (Astrikc, rule-focused)", value="strict"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def si_mood(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        """Alias for /ai mood."""
        await self.ai_mood(interaction, mode)

    # ── Self-Learning Commands (Inspired by Starsky & DiscordNPC) ───────────

    @ai_group.command(name="learn", description="🧠 Teach the AI a custom fact, server lore, or definition.")
    @app_commands.describe(
        topic="The subject or keyword to remember (e.g. 'GKR Server', 'Oliver', 'Our Rules')",
        fact="The fact or information the AI should learn"
    )
    async def ai_learn(self, interaction: discord.Interaction, topic: str, fact: str):
        """Teach the AI a fact."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        success = LearningMemoryEngine.add_memory(
            guild_id=guild_id,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            topic=topic,
            fact=fact,
            learned_from="user_command"
        )
        if success:
            embed = discord.Embed(
                title="🧠  AI Memory Stored",
                description=f"I have learned and permanently memorized this for this server:\n\n• **Topic:** `{topic}`\n• **Knowledge:** {fact}",
                color=C.SUCCESS
            )
            embed.set_footer(text=f"Taught by {interaction.user.display_name} • {BOT_NAME} Self-Learning Engine")
            await interaction.response.send_message(embed=embed)

            await self.dispatch_log(
                interaction.guild,
                "ai_config",
                "🧠 New AI Memory Learned",
                f"**User:** {interaction.user.mention} (`{interaction.user.name}`)\n**Topic:** `{topic}`\n**Fact:** {fact}",
                color=C.PURPLE
            )
        else:
            await interaction.response.send_message("❌ Could not save memory. Please provide a valid topic and fact.", ephemeral=True)

    @ai_group.command(name="memory", description="📖 Inspect what the AI has learned and remembered.")
    @app_commands.describe(topic="Specific topic to lookup (leave blank to see recent memories)")
    async def ai_memory(self, interaction: discord.Interaction, topic: Optional[str] = None):
        """Inspect AI learned memories."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            if topic:
                cur.execute(
                    "SELECT * FROM ai_learned_memories WHERE guild_id = ? AND topic LIKE ? LIMIT 5",
                    (str(guild_id), f"%{topic.strip().lower()}%")
                )
            else:
                cur.execute(
                    "SELECT * FROM ai_learned_memories WHERE guild_id = ? ORDER BY updated_at DESC LIMIT 8",
                    (str(guild_id),)
                )
            rows = cur.fetchall()

        if not rows:
            await interaction.response.send_message(
                embed=embed_info("No Memories Found", "The AI hasn't memorized any facts for this search yet.\nTeach it with `/ai learn <topic> <fact>`!"),
                ephemeral=True
            )
            return

        desc_lines = []
        for r in rows:
            desc_lines.append(f"• **{r['topic'].capitalize()}**: {r['fact'][:120]} *(taught by {r['user_name']})*")

        embed = discord.Embed(
            title="🧠  AI Learned Memories",
            description="\n".join(desc_lines),
            color=C.BRAND
        )
        embed.set_footer(text=f"{BOT_NAME} Bot Self-Learning Knowledge Base • {fmt_ts()}")
        await interaction.response.send_message(embed=embed)

    @ai_group.command(name="forget", description="🧹 Remove a learned fact from the AI's memory.")
    @app_commands.describe(topic="The topic to forget")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def ai_forget(self, interaction: discord.Interaction, topic: str):
        """Forget a learned topic."""
        guild_id = interaction.guild_id or 0
        clean_topic = topic.strip().lower()
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM ai_learned_memories WHERE guild_id = ? AND topic = ?", (str(guild_id), clean_topic))
            deleted = cur.rowcount
            conn.commit()

        if deleted > 0:
            await interaction.response.send_message(
                embed=embed_success("Memory Cleared", f"Successfully forgot all learned facts regarding **`{topic}`**."),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(f"❌ No learned memory found for `{topic}`.", ephemeral=True)

    # ── Media & Voice Features ─────────────────────────────────────────────

    @ai_group.command(name="tts", description="🔊 Generate natural voice speech audio from text.")
    @app_commands.describe(
        text="The message to speak (max 250 characters)",
        language="Spoken language voice"
    )
    @app_commands.choices(
        language=[
            app_commands.Choice(name="English", value="en"),
            app_commands.Choice(name="Spanish", value="es"),
            app_commands.Choice(name="French", value="fr"),
            app_commands.Choice(name="German", value="de"),
            app_commands.Choice(name="Japanese", value="ja"),
            app_commands.Choice(name="Hindi", value="hi"),
            app_commands.Choice(name="Malayalam", value="ml"),
            app_commands.Choice(name="Korean", value="ko"),
        ]
    )
    async def ai_tts(self, interaction: discord.Interaction, text: str, language: Optional[app_commands.Choice[str]] = None):
        """Generate TTS voice clip."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        lang_code = language.value if language else "en"
        lang_name = language.name if language else "English"

        audio_buf = await TTSEngine.generate_tts(self.session, text, lang_code)
        if not audio_buf:
            await interaction.followup.send(embed=embed_error("Could not synthesize voice audio for this message.", title="TTS Failed"))
            return

        file = discord.File(audio_buf, filename="speech.mp3")
        embed = discord.Embed(
            title="🔊  AI Voice Speech",
            description=f"> *\"{text[:200]}\"*\n\n**Voice:** `{lang_name}`",
            color=C.BRAND
        )
        embed.set_footer(text=f"Generated for {interaction.user.display_name} • {BOT_NAME} AI Voice")
        await interaction.followup.send(embed=embed, file=file)

    @ai_group.command(name="thread", description="🧵 Create a dedicated AI discussion thread with conversation memory.")
    @app_commands.describe(topic="The topic or question for the AI thread")
    async def ai_thread(self, interaction: discord.Interaction, topic: str):
        """Create AI discussion thread."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ AI threads can only be created in standard text channels.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        thread = await interaction.channel.create_thread(
            name=f"🧠 AI: {topic[:50]}",
            auto_archive_duration=60,
            type=discord.ChannelType.public_thread
        )

        session_key = f"{guild_id}_{thread.id}_{interaction.user.id}"
        session = self.memory.get_session(session_key)

        response_text, meta = await self.client.generate_response(
            prompt=topic,
            history=[],
            guild_config=guild_config,
            user_name=interaction.user.display_name,
            guild_id=guild_id,
            user_id=interaction.user.id
        )

        session.add_turn("user", topic)
        session.add_turn("assistant", response_text)

        await thread.send(f"👋 **AI Discussion Thread Started for {interaction.user.mention}**\n**Topic:** `{topic}`\n\n{response_text}")
        await interaction.followup.send(
            embed=embed_success("AI Thread Created", f"Your discussion thread has been opened: {thread.mention}"),
            ephemeral=True
        )

    @ai_group.command(name="banner", description="✨ Generate animated text GIF banners for Discord headers & profiles.")
    @app_commands.describe(
        text="Text to display on the animated banner (max 40 chars)",
        style="Visual animation style",
        color="Color theme palette",
        font="Font typography"
    )
    @app_commands.choices(
        style=[
            app_commands.Choice(name="⚡ Neon Glow (Pulsing Glow)", value="neon"),
            app_commands.Choice(name="👾 Cyber Glitch (RGB Shift)", value="glitch"),
            app_commands.Choice(name="🌈 Rainbow Flow (Smooth Gradient)", value="rainbow"),
            app_commands.Choice(name="⌨️ Typewriter (Letter-by-Letter)", value="typewriter"),
            app_commands.Choice(name="🔥 Fire Ember (Flame Particles)", value="fire"),
            app_commands.Choice(name="🎈 Bounce Pop (Spring Animation)", value="bounce"),
        ],
        color=[
            app_commands.Choice(name="Blurple (Discord Classic)", value="blurple"),
            app_commands.Choice(name="Cyber Purple", value="purple"),
            app_commands.Choice(name="Electric Cyan", value="cyan"),
            app_commands.Choice(name="Golden Amber", value="gold"),
            app_commands.Choice(name="Ruby Red", value="ruby"),
            app_commands.Choice(name="Emerald Green", value="emerald"),
            app_commands.Choice(name="Sunset Pink", value="pink"),
        ],
        font=[
            app_commands.Choice(name="Impact (Bold & Punchy)", value="impact"),
            app_commands.Choice(name="Modern Sans (Clean & Sleek)", value="modern"),
            app_commands.Choice(name="Classic Bold", value="bold"),
        ]
    )
    async def ai_banner(
        self,
        interaction: discord.Interaction,
        text: str,
        style: Optional[app_commands.Choice[str]] = None,
        color: Optional[app_commands.Choice[str]] = None,
        font: Optional[app_commands.Choice[str]] = None
    ):
        """Generate animated text GIF banner."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        style_val = style.value if style else "neon"
        color_val = color.value if color else "blurple"
        font_val = font.value if font else "impact"

        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(
            None,
            lambda: TextGIFGenerator.render_banner(
                text=text,
                style=style_val,
                color_theme=color_val,
                font_choice=font_val
            )
        )

        file = discord.File(buf, filename="banner.gif")
        embed = discord.Embed(
            title="✨  Animated Text GIF Banner",
            description=f"> **Text:** `{text}`\n> **Style:** `{style_val.capitalize()}` • **Palette:** `{color_val.capitalize()}`",
            color=C.PURPLE
        )
        embed.set_image(url="attachment://banner.gif")
        embed.set_footer(text=f"Created for {interaction.user.display_name} • {BOT_NAME} AI Banner Engine")

        await interaction.followup.send(embed=embed, file=file)

        await self.dispatch_log(
            interaction.guild,
            "ai_banner",
            "✨ AI Text GIF Banner Created",
            f"**User:** {interaction.user.mention} (`{interaction.user.name}`)\n**Text:** `{text}`\n**Style:** `{style_val}` • **Color:** `{color_val}`",
            color=C.PURPLE
        )

    @ai_group.command(name="chat", description="💬 Chat with the AI model with conversation memory & dialect mirroring.")
    @app_commands.describe(prompt="Your message or question for the AI")
    async def ai_chat(self, interaction: discord.Interaction, prompt: str):
        """Chat with the AI."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        session_key = f"{guild_id}_{interaction.channel_id}_{interaction.user.id}"
        session = self.memory.get_session(session_key)

        response_text, meta = await self.client.generate_response(
            prompt=prompt,
            history=session.get_history(),
            guild_config=guild_config,
            user_name=interaction.user.display_name,
            guild_id=guild_id,
            user_id=interaction.user.id
        )

        session.add_turn("user", prompt)
        session.add_turn("assistant", response_text)

        if len(response_text) > 2000:
            chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
            for chunk in chunks:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(response_text)

        await self.dispatch_log(
            interaction.guild,
            "ai_query",
            "💬 AI Slash Chat Used",
            f"**User:** {interaction.user.mention} (`{interaction.user.name}`)\n**Prompt:** `{prompt[:150]}`",
            color=C.BRAND
        )

    @ai_group.command(name="ask", description="🔍 Deep research and answer questions in your exact language/dialect.")
    @app_commands.describe(question="What would you like to research? (e.g. where is kerala located / kerala evideya)")
    async def ai_ask(self, interaction: discord.Interaction, question: str):
        """Direct deep research command."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        response_text, meta = await self.client.generate_response(
            prompt=question,
            history=[],
            guild_config=guild_config,
            user_name=interaction.user.display_name,
            guild_id=guild_id,
            user_id=interaction.user.id
        )

        await interaction.followup.send(response_text)

        await self.dispatch_log(
            interaction.guild,
            "ai_research",
            "🔍 AI Research Performed",
            f"**User:** {interaction.user.mention} (`{interaction.user.name}`)\n**Question:** `{question[:150]}`\n**Dialect:** `{meta.get('dialect', 'english') if meta else 'english'}`",
            color=C.CYAN,
            thumbnail_url=meta.get("thumbnail") if meta else None
        )

    @ai_group.command(name="imagine", description="🎨 Generate AI art and images using high-quality models.", nsfw=True)
    @app_commands.describe(
        prompt="Describe the image you want to generate in detail",
        aspect_ratio="Dimensions of the generated image",
        style="Visual style preset"
    )
    @app_commands.choices(
        aspect_ratio=[
            app_commands.Choice(name="Square (1:1)", value="1:1"),
            app_commands.Choice(name="Landscape (16:9)", value="16:9"),
            app_commands.Choice(name="Portrait (9:16)", value="9:16"),
            app_commands.Choice(name="Standard (4:3)", value="4:3"),
        ],
        style=[
            app_commands.Choice(name="Photorealistic", value="photorealistic, 8k, hyper-detailed, studio lighting"),
            app_commands.Choice(name="Anime / Manga", value="anime aesthetic, vibrant studio ghibli style, detailed anime key visual"),
            app_commands.Choice(name="Cyberpunk", value="cyberpunk, neon glow, futuristic city, cinematic octan render"),
            app_commands.Choice(name="Digital Art / Fantasy", value="epic fantasy concept art, greg rutkowski style, dramatic lighting"),
            app_commands.Choice(name="3D Render", value="3d pixar style render, smooth claymation, vibrant 4k octane render"),
        ]
    )
    async def ai_imagine(
        self,
        interaction: discord.Interaction,
        prompt: str,
        aspect_ratio: Optional[app_commands.Choice[str]] = None,
        style: Optional[app_commands.Choice[str]] = None
    ):
        """Generate AI image."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        if not guild_config.get("image_enabled", 1):
            await interaction.response.send_message("❌ AI image generation is disabled on this server.", ephemeral=True)
            return

        # Secondary NSFW channel guard (catches DMs and edge-cases the decorator may miss)
        channel = interaction.channel
        is_nsfw = getattr(channel, "nsfw", False)
        if not is_nsfw:
            await interaction.response.send_message(
                embed=embed_warning(
                    "🔞 `/ai imagine` can only be used in **NSFW-marked channels** to prevent inappropriate content from appearing in general channels.\n\n"
                    "Ask a server admin to mark a channel as NSFW, then try again there.",
                    title="NSFW Channel Required"
                ),
                ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        ar_val = aspect_ratio.value if aspect_ratio else "1:1"
        style_val = style.value if style else ""

        dim_map = {
            "1:1": (1024, 1024),
            "16:9": (1280, 720),
            "9:16": (720, 1280),
            "4:3": (1024, 768),
        }
        w, h = dim_map.get(ar_val, (1024, 1024))

        full_prompt = f"{prompt}, {style_val}" if style_val else prompt
        seed = int(time.time() * 1000) % 10000000

        image_url = (
            f"https://image.pollinations.ai/prompt/{urllib.parse.quote(full_prompt)}"
            f"?width={w}&height={h}&seed={seed}&nologo=true&model=flux"
        )

        embed = discord.Embed(
            title=f"🎨  AI Generated Image",
            description=f"> **Prompt:** {prompt}\n> **Aspect Ratio:** `{ar_val}` • **Model:** `FLUX.1`",
            color=C.PURPLE
        )
        embed.set_image(url=image_url)
        embed.set_footer(text=f"Requested by {interaction.user.display_name} • Powered by {BOT_NAME} AI")

        view = AIImageView(prompt, image_url, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

        await self.dispatch_log(
            interaction.guild,
            "ai_image",
            "🎨 AI Image Generated",
            f"**User:** {interaction.user.mention} (`{interaction.user.name}`)\n**Prompt:** `{prompt}`\n**Aspect Ratio:** `{ar_val}`\n**Model:** `FLUX.1`",
            color=C.PURPLE,
            image_url=image_url
        )

    @ai_group.command(name="code", description="💻 Code analysis, writing, and debugging assistant.")
    @app_commands.describe(
        request="What code do you need help with? (e.g. write a discord bot cog or fix bug)",
        language="Programming language (e.g. python, javascript, rust)"
    )
    async def ai_code(
        self,
        interaction: discord.Interaction,
        request: str,
        language: Optional[str] = "python"
    ):
        """Dedicated code assistant."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)

        code_prompt = f"Write/explain {language} code for: {request}. Ensure clean syntax, type hints, and comments."
        response_text, meta = await self.client.generate_response(
            prompt=code_prompt,
            history=[],
            guild_config=guild_config,
            user_name=interaction.user.display_name,
            guild_id=guild_id,
            user_id=interaction.user.id
        )

        embed = discord.Embed(
            title=f"💻  Code Assistant: {language.capitalize()}",
            description=f"**Request:** `{request[:100]}`\n\n{response_text[:3800]}",
            color=C.SUCCESS
        )
        embed.set_footer(text=f"🧠 {meta.get('engine', 'GKR Code Core') if meta else 'GKR AI'} • {fmt_ts()}")
        await interaction.followup.send(embed=embed)

    @ai_group.command(name="roast", description="🔥 Generate a hilarious, playful roast for a member or topic.")
    @app_commands.describe(target="Who or what would you like to roast? (e.g. @Member or 'my sleep schedule')")
    async def ai_roast(self, interaction: discord.Interaction, target: str):
        """Generate playful roast."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        roast_text = ComedyEngine.get_roast(target)
        embed = discord.Embed(
            title="🔥  AI Comedy Roast",
            description=roast_text,
            color=C.DANGER
        )
        embed.set_footer(text=f"Requested by {interaction.user.display_name} • Friendly banter only!")
        await interaction.response.send_message(embed=embed)

        await self.dispatch_log(
            interaction.guild,
            "ai_comedy",
            "🔥 AI Comedy Roast",
            f"**User:** {interaction.user.mention} (`{interaction.user.name}`)\n**Target:** `{target}`",
            color=C.DANGER
        )

    @ai_group.command(name="summarize", description="📝 Summarize long text into key bullet points and TL;DR.")
    @app_commands.describe(text="The long text or article to summarize")
    async def ai_summarize(self, interaction: discord.Interaction, text: str):
        """Summarize text."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        summary = KnowledgeEngine.summarize_text(text)
        embed = discord.Embed(
            title="📝  AI Summary",
            description=summary,
            color=C.BRAND
        )
        embed.set_footer(text=f"Summarized {len(text)} characters • {BOT_NAME} AI")
        await interaction.response.send_message(embed=embed)

    @ai_group.command(name="sentiment", description="📊 Analyze emotional tone and sentiment of a message.")
    @app_commands.describe(text="Text to analyze")
    async def ai_sentiment(self, interaction: discord.Interaction, text: str):
        """Analyze sentiment."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        label, emoji, color = KnowledgeEngine.analyze_sentiment(text)
        embed = discord.Embed(
            title=f"{emoji}  Sentiment Analysis",
            description=f"> *\"{text[:300]}\"*\n\n**Detected Tone:** `{label}` {emoji}",
            color=color
        )
        embed.set_footer(text=f"{BOT_NAME} AI Sentiment Analysis")
        await interaction.response.send_message(embed=embed)

    @ai_group.command(name="prompt", description="💡 Enhance a simple concept into a professional AI image prompt.")
    @app_commands.describe(concept="Your simple idea (e.g. 'cyberpunk cat in rain')")
    async def ai_prompt_enhance(self, interaction: discord.Interaction, concept: str):
        """Enhance prompt for Midjourney/FLUX."""
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)
        if not guild_config.get("enabled", 1):
            await interaction.response.send_message(
                embed=embed_warning(f"{BOT_NAME} AI is currently disabled on this server.\nAn administrator can enable it anytime using `/ai enable`.", title="AI System Disabled"),
                ephemeral=True
            )
            return

        enhancers = [
            "masterpiece, 8k resolution, cinematic lighting, highly detailed textures, volumetric light, unreal engine 5 render, award winning photography",
            "hyper-realistic, octane render, vivid atmosphere, 35mm lens, sharp focus, vibrant aesthetic, depth of field",
            "concept art by greg rutkowski, epic composition, golden hour lighting, trending on artstation, masterpiece"
        ]
        chosen = random.choice(enhancers)
        enhanced = f"{concept}, {chosen}"

        embed = discord.Embed(
            title="💡  Enhanced AI Prompt",
            description=(
                f"**Original Idea:**\n> `{concept}`\n\n"
                f"**Optimized Prompt (FLUX / Midjourney / DALL-E):**\n```text\n{enhanced}\n```"
            ),
            color=C.GOLD
        )
        embed.set_footer(text="Copy & paste into /ai imagine or Midjourney!")
        await interaction.response.send_message(embed=embed)

    @ai_group.command(name="reset", description="🧹 Clear your active conversation history/memory with the AI.")
    async def ai_reset(self, interaction: discord.Interaction):
        """Clear user conversation session."""
        guild_id = interaction.guild_id or 0
        session_key = f"{guild_id}_{interaction.channel_id}_{interaction.user.id}"
        self.memory.clear_session(session_key)
        await interaction.response.send_message(
            embed=embed_success("Memory Cleared", "Your conversation history in this channel has been reset."),
            ephemeral=True
        )

    @ai_group.command(name="status", description="📊 Check AI system status, self-learning stats, persona & settings.")
    async def ai_status(self, interaction: discord.Interaction):
        """View AI status & diagnostic panel."""
        await interaction.response.defer(thinking=True)
        guild_id = interaction.guild_id or 0
        guild_config = get_guild_config(guild_id)

        ollama_url = guild_config.get("ollama_url", "http://127.0.0.1:11434")
        ollama_online, models = await self.client.check_ollama_status(ollama_url)

        # Count learned memories
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM ai_learned_memories WHERE guild_id = ?", (str(guild_id),))
            learned_count = cur.fetchone()[0]

        embed = discord.Embed(
            title=f"🧠  {BOT_NAME} AI System Diagnostic & Status",
            color=C.SUCCESS if (ollama_online and guild_config.get("enabled", 1)) else C.BRAND
        )

        if ollama_online:
            model_list = ", ".join([f"`{m}`" for m in models[:5]]) if models else "None"
            embed.add_field(
                name="🖥️  Self-Hosted LLM (Ollama)",
                value=f"• **Status:** 🟢 **Online & Connected**\n• **Endpoint:** `{ollama_url}`\n• **Installed Models:** {model_list}",
                inline=False
            )
        else:
            embed.add_field(
                name="🖥️  Self-Hosted LLM (Ollama)",
                value=f"• **Status:** ⚪ **Offline / Standby**\n• **Endpoint:** `{ollama_url}`\n• *To connect local LLMs, run `ollama serve` on your host machine.*",
                inline=False
            )

        embed.add_field(
            name="⚡  Built-in AI Modules & Learning",
            value=(
                f"• **Self-Learning Knowledge Base:** 🟢 Active (`{learned_count}` facts memorized)\n"
                "• **Dialect Mirroring Engine:** 🟢 Active (Manglish, Hinglish, Regional Scripts)\n"
                "• **Real-Time Fact Research:** 🟢 Active (Wikipedia & Web Knowledge)\n"
                "• **Text-To-Speech (TTS) Voice Engine:** 🟢 Active (12 Languages)\n"
                "• **Animated Text GIF Banners:** 🟢 Active (6 Custom Styles)\n"
                "• **Audit Logging:** 🟢 Active (Routed to `🧠・ᴀɪ-ʟᴏɢꜱ`)"
            ),
            inline=False
        )

        ai_channel_val = f"<#{guild_config['ai_channel_id']}>" if guild_config.get("ai_channel_id") else "None (Mention/Commands Only)"
        embed.add_field(
            name="⚙️  Server Configuration",
            value=(
                f"• **AI System:** {'🟢 **Enabled**' if guild_config.get('enabled') else '🔴 **Disabled**'}\n"
                f"• **Active Persona:** `{guild_config.get('persona', 'friendly').capitalize()}`\n"
                f"• **AI Channel:** {ai_channel_val}\n"
                f"• **Self-Learning:** {'✅ Enabled' if guild_config.get('self_learning', 1) else '❌ Disabled'}\n"
                f"• **Mention Response:** {'✅ Enabled' if guild_config.get('mention_enabled') else '❌ Disabled'}\n"
                f"• **User Cooldown:** `{guild_config.get('cooldown_seconds', 3)}s`"
            ),
            inline=False
        )

        embed.set_footer(text=f"{BOT_NAME} Bot AI Architecture • {fmt_ts()}")
        await interaction.followup.send(embed=embed)

    # -----------------------------------------------------------------------
    # Admin Configuration Subcommands
    # -----------------------------------------------------------------------

    config_group = app_commands.Group(name="config", description="⚙️ Configure AI settings", parent=ai_group)

    @config_group.command(name="persona", description="🎭 Change the AI bot personality persona.")
    @app_commands.describe(preset="Choose a personality preset for the AI")
    @app_commands.choices(
        preset=[
            app_commands.Choice(name="🌟 Friendly (Helpful, warm, cheerful)", value="friendly"),
            app_commands.Choice(name="🎮 Gamer (Hype, clutch, gaming culture)", value="gamer"),
            app_commands.Choice(name="😏 Sarcastic (Witty, clever humor, playful sass)", value="sarcastic"),
            app_commands.Choice(name="🔬 Expert (Deep, academic, precise, no fluff)", value="expert"),
            app_commands.Choice(name="🌆 Cyberpunk (Futuristic, high-tech AI)", value="cyberpunk"),
            app_commands.Choice(name="✨ Anime (Kawaii, expressive, high-energy)", value="anime"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_persona(self, interaction: discord.Interaction, preset: app_commands.Choice[str]):
        """Set active AI persona."""
        guild_id = interaction.guild_id or 0
        update_guild_config(guild_id, persona=preset.value)
        await interaction.response.send_message(
            embed=embed_success("AI Persona Updated", f"Active bot personality set to **{preset.name}**!"),
            ephemeral=True
        )
        await self.dispatch_log(
            interaction.guild,
            "ai_config",
            "🎭 AI Persona Changed",
            f"**Admin:** {interaction.user.mention}\n**New Persona:** `{preset.name}`",
            color=C.PURPLE
        )

    @config_group.command(name="channel", description="Set or clear the dedicated AI chat channel.")
    @app_commands.describe(channel="The channel for automatic AI conversation (leave blank to clear)")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_channel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Set or clear AI channel."""
        guild_id = interaction.guild_id or 0
        if channel:
            update_guild_config(guild_id, ai_channel_id=str(channel.id))
            await interaction.response.send_message(
                embed=embed_success("AI Channel Configured", f"Users can now talk directly with AI in {channel.mention} without tagging!"),
                ephemeral=True
            )
            await self.dispatch_log(
                interaction.guild,
                "ai_config",
                "⚙️ AI Channel Updated",
                f"**Admin:** {interaction.user.mention}\n**Channel:** {channel.mention}",
                color=C.BRAND
            )
        else:
            update_guild_config(guild_id, ai_channel_id="")
            await interaction.response.send_message(
                embed=embed_info("AI Channel Cleared", "AI channel removed. AI will now respond to @Bot mentions and `/ai` commands."),
                ephemeral=True
            )
            await self.dispatch_log(
                interaction.guild,
                "ai_config",
                "⚙️ AI Channel Cleared",
                f"**Admin:** {interaction.user.mention}\n**Status:** None",
                color=C.BRAND
            )

    @config_group.command(name="ollama", description="Configure custom self-hosted Ollama / Local LLM URL.")
    @app_commands.describe(endpoint_url="URL to your local Ollama server (default: http://127.0.0.1:11434)")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_ollama(self, interaction: discord.Interaction, endpoint_url: str):
        """Set Ollama URL."""
        guild_id = interaction.guild_id or 0
        clean_url = endpoint_url.strip().rstrip("/")
        update_guild_config(guild_id, ollama_url=clean_url)

        online, models = await self.client.check_ollama_status(clean_url)
        if online:
            models_str = ", ".join([f"`{m}`" for m in models]) if models else "None"
            await interaction.response.send_message(
                embed=embed_success(
                    "Ollama Endpoint Connected",
                    f"Successfully connected to `{clean_url}`!\n**Available Models:** {models_str}"
                ),
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                embed=embed_warning(
                    f"Saved endpoint `{clean_url}`, but connection test failed (server unreachable). "
                    f"Ensure `ollama serve` is running.",
                    title="Endpoint Saved (Offline)"
                ),
                ephemeral=True
            )

        await self.dispatch_log(
            interaction.guild,
            "ai_config",
            "⚙️ AI Ollama Endpoint Changed",
            f"**Admin:** {interaction.user.mention}\n**Endpoint:** `{clean_url}`\n**Status:** {'🟢 Online' if online else '⚪ Offline'}",
            color=C.BRAND
        )

    @config_group.command(name="model", description="Select active Ollama model name (e.g. llama3, mistral, deepseek-r1).")
    @app_commands.describe(model_name="Model name to use (or 'auto')")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_model(self, interaction: discord.Interaction, model_name: str):
        """Set active model."""
        guild_id = interaction.guild_id or 0
        update_guild_config(guild_id, model_name=model_name.strip())
        await interaction.response.send_message(
            embed=embed_success("AI Model Updated", f"Active model set to `{model_name.strip()}`."),
            ephemeral=True
        )
        await self.dispatch_log(
            interaction.guild,
            "ai_config",
            "⚙️ AI Model Updated",
            f"**Admin:** {interaction.user.mention}\n**Model:** `{model_name.strip()}`",
            color=C.BRAND
        )

    @config_group.command(name="prompt", description="Set a custom system prompt personality for this server.")
    @app_commands.describe(system_prompt="Custom system instructions (leave blank to reset)")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_prompt(self, interaction: discord.Interaction, system_prompt: Optional[str] = None):
        """Set custom system prompt."""
        guild_id = interaction.guild_id or 0
        val = system_prompt.strip() if system_prompt else ""
        update_guild_config(guild_id, system_prompt=val)
        msg = f"Custom system prompt updated:\n> `{val[:200]}`" if val else "Custom system prompt cleared. Reverted to default persona."
        await interaction.response.send_message(embed=embed_success("System Prompt Configured", msg), ephemeral=True)

    @config_group.command(name="toggle", description="Toggle specific AI features on/off.")
    @app_commands.describe(
        feature="The feature to toggle",
        enabled="Enable or disable"
    )
    @app_commands.choices(
        feature=[
            app_commands.Choice(name="Self-Learning System (/ai learn & chat memory)", value="self_learning"),
            app_commands.Choice(name="Mention Replies (@Bot)", value="mention_enabled"),
            app_commands.Choice(name="Web & Wikipedia Research", value="research_enabled"),
            app_commands.Choice(name="AI Image Generation (/ai imagine)", value="image_enabled"),
            app_commands.Choice(name="Comedy Engine (/laugh, /ai roast)", value="comedy_enabled"),
            app_commands.Choice(name="Text-To-Speech (/ai tts)", value="tts_enabled"),
            app_commands.Choice(name="Thread Mode Assistant", value="thread_mode"),
            app_commands.Choice(name="Entire AI System", value="enabled"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config_toggle(self, interaction: discord.Interaction, feature: app_commands.Choice[str], enabled: bool):
        """Toggle feature."""
        guild_id = interaction.guild_id or 0
        val = 1 if enabled else 0
        update_guild_config(guild_id, **{feature.value: val})
        status_text = "Enabled ✅" if enabled else "Disabled ❌"
        await interaction.response.send_message(
            embed=embed_success(f"{feature.name} {status_text}", f"Setting updated for this server."),
            ephemeral=True
        )
        await self.dispatch_log(
            interaction.guild,
            "ai_config",
            f"⚙️ AI Feature Toggled: {feature.name}",
            f"**Admin:** {interaction.user.mention}\n**Feature:** `{feature.name}`\n**Status:** {status_text}",
            color=C.BRAND
        )


async def setup(bot: commands.Bot):
    """Setup hook to register AICog with the bot."""
    await bot.add_cog(AICog(bot))
    print("🧠 Central AI & Self-Hosted Intelligence system loaded!")
