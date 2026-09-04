"""
poll.py — Advanced Customizable Interactive Polling System for GKR Bot.

Features:
  • Single-choice & Multiple-choice modes
  • Anonymous vs Public vote tallying
  • Live graphical visual percentage bars (████████░░ 80%)
  • Timed auto-closing polls with countdown & automatic winner announcement
  • Persistent SQLite database for poll state across bot restarts
  • Clean button-based voting UI with results inspection
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import sqlite3
from typing import Optional, List, Dict

import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = os.path.join(os.path.dirname(__file__), "poll.sqlite3")

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


# ─── Database ──────────────────────────────────────────────────────────────────

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                message_id      INTEGER PRIMARY KEY,
                channel_id      INTEGER NOT NULL,
                guild_id        INTEGER NOT NULL,
                author_id       INTEGER NOT NULL,
                question        TEXT NOT NULL,
                options_json    TEXT NOT NULL,
                votes_json      TEXT NOT NULL DEFAULT '{}',
                multi_choice    INTEGER NOT NULL DEFAULT 0,
                anonymous       INTEGER NOT NULL DEFAULT 0,
                expires_at      REAL,
                ended           INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()


def save_poll(
    message_id: int,
    channel_id: int,
    guild_id: int,
    author_id: int,
    question: str,
    options: List[str],
    multi_choice: bool,
    anonymous: bool,
    expires_at: Optional[float] = None,
):
    with _db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO polls (
                message_id, channel_id, guild_id, author_id, question,
                options_json, votes_json, multi_choice, anonymous, expires_at, ended
            ) VALUES (?, ?, ?, ?, ?, ?, '{}', ?, ?, ?, 0)
        """, (
            message_id, channel_id, guild_id, author_id, question,
            json.dumps(options), 1 if multi_choice else 0, 1 if anonymous else 0, expires_at
        ))
        conn.commit()


def get_poll(message_id: int) -> Optional[dict]:
    with _db() as conn:
        row = conn.execute("SELECT * FROM polls WHERE message_id = ?", (message_id,)).fetchone()
    if not row:
        return None
    return {
        "message_id": row["message_id"],
        "channel_id": row["channel_id"],
        "guild_id": row["guild_id"],
        "author_id": row["author_id"],
        "question": row["question"],
        "options": json.loads(row["options_json"]),
        "votes": json.loads(row["votes_json"]),
        "multi_choice": bool(row["multi_choice"]),
        "anonymous": bool(row["anonymous"]),
        "expires_at": row["expires_at"],
        "ended": bool(row["ended"]),
    }


def record_vote(message_id: int, user_id: int, option_idx: int) -> dict:
    with _db() as conn:
        row = conn.execute("SELECT * FROM polls WHERE message_id = ?", (message_id,)).fetchone()
        if not row or row["ended"]:
            return {}
        votes = json.loads(row["votes_json"])
        user_key = str(user_id)
        multi = bool(row["multi_choice"])

        user_votes = votes.get(user_key, [])
        if option_idx in user_votes:
            # Toggle off
            user_votes.remove(option_idx)
            if not user_votes:
                votes.pop(user_key, None)
            else:
                votes[user_key] = user_votes
        else:
            if multi:
                user_votes.append(option_idx)
                votes[user_key] = user_votes
            else:
                votes[user_key] = [option_idx]

        conn.execute("UPDATE polls SET votes_json = ? WHERE message_id = ?", (json.dumps(votes), message_id))
        conn.commit()

    return get_poll(message_id) or {}


def close_poll_in_db(message_id: int):
    with _db() as conn:
        conn.execute("UPDATE polls SET ended = 1 WHERE message_id = ?", (message_id,))
        conn.commit()


# ─── Visual Bar Generator ──────────────────────────────────────────────────────

def _render_bar(percent: float, length: int = 10) -> str:
    filled = int(round(length * (percent / 100)))
    empty = length - filled
    return "█" * filled + "░" * empty


def build_poll_embed(poll_data: dict, is_closed: bool = False) -> discord.Embed:
    question = poll_data["question"]
    options = poll_data["options"]
    votes: Dict[str, List[int]] = poll_data["votes"]
    multi_choice = poll_data["multi_choice"]
    anonymous = poll_data["anonymous"]
    expires_at = poll_data.get("expires_at")

    # Count votes per option
    counts = [0] * len(options)
    total_voters = len(votes)
    total_selections = 0

    for user_id, user_opts in votes.items():
        for opt in user_opts:
            if 0 <= opt < len(options):
                counts[opt] += 1
                total_selections += 1

    color = 0xED4245 if is_closed else 0x5865F2

    status_badge = "🔴  POLL ENDED" if is_closed else "📊  COMMUNITY POLL"

    embed = discord.Embed(
        title=f"{status_badge}\n{question}",
        color=color,
        timestamp=discord.utils.utcnow()
    )

    lines = []
    for idx, opt_text in enumerate(options):
        emoji = NUMBER_EMOJIS[idx] if idx < len(NUMBER_EMOJIS) else f"`{idx+1}.`"
        count = counts[idx]
        pct = (count / total_selections * 100) if total_selections > 0 else 0.0
        bar = _render_bar(pct, length=12)

        lines.append(f"{emoji} **{opt_text}**")
        lines.append(f"`{bar}` **{pct:.1f}%** ({count:,} vote{'s' if count != 1 else ''})\n")

    embed.description = "\n".join(lines)

    # Metadata footer
    mode_tags = []
    mode_tags.append("Multiple Choice" if multi_choice else "Single Choice")
    mode_tags.append("Anonymous" if anonymous else "Public")
    if expires_at and not is_closed:
        mode_tags.append(f"Ends <t:{int(expires_at)}:R>")

    meta_str = " · ".join(mode_tags)
    embed.set_footer(text=f"Total Voters: {total_voters:,}  •  {meta_str}")
    return embed


# ─── Interactive UI View ──────────────────────────────────────────────────────

class PollVoteButton(discord.ui.Button):
    def __init__(self, option_idx: int, label: str, emoji: Optional[str] = None):
        super().__init__(
            label=label[:80],
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"poll_vote:{option_idx}",
            row=option_idx // 5
        )
        self.option_idx = option_idx

    async def callback(self, interaction: discord.Interaction):
        poll = record_vote(interaction.message.id, interaction.user.id, self.option_idx)
        if not poll:
            await interaction.response.send_message("❌ This poll has already ended.", ephemeral=True)
            return

        embed = build_poll_embed(poll)
        await interaction.response.edit_message(embed=embed)

        user_votes = poll["votes"].get(str(interaction.user.id), [])
        if self.option_idx in user_votes:
            await interaction.followup.send(
                f"✅ You voted for **Option {self.option_idx + 1}**.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"↩️ You removed your vote for **Option {self.option_idx + 1}**.",
                ephemeral=True
            )


class PollControlView(discord.ui.View):
    def __init__(self, poll_data: dict):
        super().__init__(timeout=None)
        options = poll_data["options"]

        for idx, opt_text in enumerate(options):
            emoji = NUMBER_EMOJIS[idx] if idx < len(NUMBER_EMOJIS) else None
            self.add_item(PollVoteButton(idx, opt_text, emoji))

        # Bottom row controls
        btn_row = min(4, (len(options) - 1) // 5 + 1)
        self.add_item(PollResultsButton(row=btn_row))
        self.add_item(PollEndButton(poll_data["author_id"], row=btn_row))


class PollResultsButton(discord.ui.Button):
    def __init__(self, row: int):
        super().__init__(
            label="Voter Breakdown",
            emoji="👥",
            style=discord.ButtonStyle.primary,
            custom_id="poll:breakdown",
            row=row
        )

    async def callback(self, interaction: discord.Interaction):
        poll = get_poll(interaction.message.id)
        if not poll:
            await interaction.response.send_message("Poll not found.", ephemeral=True)
            return

        if poll["anonymous"]:
            await interaction.response.send_message("🔒 This poll is **anonymous**. Individual voter details are private.", ephemeral=True)
            return

        votes = poll["votes"]
        options = poll["options"]
        lines = []

        for idx, opt_text in enumerate(options):
            voters_for_opt = []
            for uid_str, user_opts in votes.items():
                if idx in user_opts:
                    voters_for_opt.append(f"<@{uid_str}>")

            emoji = NUMBER_EMOJIS[idx] if idx < len(NUMBER_EMOJIS) else f"`{idx+1}.`"
            voter_str = ", ".join(voters_for_opt) if voters_for_opt else "*None*"
            lines.append(f"{emoji} **{opt_text}** ({len(voters_for_opt)}):\n> {voter_str}\n")

        embed = discord.Embed(
            title=f"👥  Public Voter Breakdown",
            description="\n".join(lines) if lines else "*No votes yet.*",
            color=0x5865F2
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PollEndButton(discord.ui.Button):
    def __init__(self, author_id: int, row: int):
        super().__init__(
            label="End Poll",
            emoji="🔒",
            style=discord.ButtonStyle.danger,
            custom_id="poll:end",
            row=row
        )
        self.author_id = author_id

    async def callback(self, interaction: discord.Interaction):
        is_mod = interaction.user.guild_permissions.manage_messages if interaction.guild else False
        if interaction.user.id != self.author_id and not is_mod:
            await interaction.response.send_message("❌ Only the poll creator or moderators can end this poll.", ephemeral=True)
            return

        close_poll_in_db(interaction.message.id)
        poll = get_poll(interaction.message.id)
        embed = build_poll_embed(poll, is_closed=True)
        await interaction.response.edit_message(embed=embed, view=None)
        await interaction.followup.send("🔒 Poll has been concluded!", ephemeral=True)


# ─── Cog ──────────────────────────────────────────────────────────────────────

class PollCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._timer_task: Optional[asyncio.Task] = None

    async def cog_load(self):
        _init_db()
        self._timer_task = asyncio.create_task(self._expiry_checker())

    async def cog_unload(self):
        if self._timer_task:
            self._timer_task.cancel()

    async def _expiry_checker(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(15)
            now = datetime.datetime.now(datetime.timezone.utc).timestamp()
            with _db() as conn:
                rows = conn.execute("SELECT * FROM polls WHERE ended = 0 AND expires_at IS NOT NULL AND expires_at <= ?", (now,)).fetchall()
                for row in rows:
                    msg_id = row["message_id"]
                    ch_id = row["channel_id"]
                    conn.execute("UPDATE polls SET ended = 1 WHERE message_id = ?", (msg_id,))
                    conn.commit()

                    ch = self.bot.get_channel(ch_id)
                    if ch and isinstance(ch, discord.TextChannel):
                        try:
                            msg = await ch.fetch_message(msg_id)
                            poll = get_poll(msg_id)
                            if poll:
                                embed = build_poll_embed(poll, is_closed=True)
                                await msg.edit(embed=embed, view=None)
                        except Exception:
                            pass

    @app_commands.command(name="poll", description="Create an advanced interactive poll with live graphical progress bars.")
    @app_commands.describe(
        question="The question or topic of the poll",
        option1="First option",
        option2="Second option",
        option3="Third option (optional)",
        option4="Fourth option (optional)",
        option5="Fifth option (optional)",
        option6="Sixth option (optional)",
        duration_minutes="Auto-close duration in minutes (e.g. 5, 60, 1440 for 24h)",
        multiple_choice="Allow members to vote for multiple options",
        anonymous="Hide who voted for which option"
    )
    async def create_poll(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: Optional[str] = None,
        option4: Optional[str] = None,
        option5: Optional[str] = None,
        option6: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        multiple_choice: bool = False,
        anonymous: bool = False,
    ):
        raw_options = [option1, option2, option3, option4, option5, option6]
        options = [opt.strip() for opt in raw_options if opt and opt.strip()]

        if len(options) < 2:
            await interaction.response.send_message("❌ A poll must have at least 2 options.", ephemeral=True)
            return

        expires_at = None
        if duration_minutes and duration_minutes > 0:
            expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=duration_minutes)).timestamp()

        poll_data = {
            "question": question,
            "options": options,
            "votes": {},
            "multi_choice": multiple_choice,
            "anonymous": anonymous,
            "expires_at": expires_at,
            "author_id": interaction.user.id
        }

        embed = build_poll_embed(poll_data)
        view = PollControlView(poll_data)

        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()

        save_poll(
            message_id=msg.id,
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            author_id=interaction.user.id,
            question=question,
            options=options,
            multi_choice=multiple_choice,
            anonymous=anonymous,
            expires_at=expires_at
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(PollCog(bot))
    print("📊 Advanced Polling System Loaded")
