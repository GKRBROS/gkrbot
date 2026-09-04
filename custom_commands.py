"""
custom_commands.py — Custom Commands System for GKR Bot.

Features:
  • /cc create [name] [response] — Create a custom slash-style command
  • /cc edit   [name] [response] — Edit a custom command's response
  • /cc delete [name]            — Delete a custom command
  • /cc list                     — List all custom commands
  • !<name> or /<name>           — Execute a custom command via prefix or info
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = os.path.join(os.path.dirname(__file__), "custom_commands.sqlite3")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class CustomCommandDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS custom_commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    response TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    uses INTEGER DEFAULT 0,
                    UNIQUE(guild_id, name)
                )
            """)
            conn.commit()

    def create(self, guild_id: int, name: str, response: str, created_by: int) -> bool:
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO custom_commands (guild_id, name, response, created_by) VALUES (?, ?, ?, ?)",
                    (str(guild_id), name.lower(), response, str(created_by))
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def edit(self, guild_id: int, name: str, response: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE custom_commands SET response=? WHERE guild_id=? AND name=?",
                (response, str(guild_id), name.lower())
            )
            conn.commit()
            return cur.rowcount > 0

    def delete(self, guild_id: int, name: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM custom_commands WHERE guild_id=? AND name=?",
                (str(guild_id), name.lower())
            )
            conn.commit()
            return cur.rowcount > 0

    def get(self, guild_id: int, name: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM custom_commands WHERE guild_id=? AND name=?",
                (str(guild_id), name.lower())
            ).fetchone()
            return dict(row) if row else None

    def list_all(self, guild_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM custom_commands WHERE guild_id=? ORDER BY uses DESC",
                (str(guild_id),)
            ).fetchall()
            return [dict(r) for r in rows]

    def increment_uses(self, guild_id: int, name: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE custom_commands SET uses=uses+1 WHERE guild_id=? AND name=?",
                (str(guild_id), name.lower())
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class CustomCommandsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = CustomCommandDatabase()
        self.db.initialize()

    # ── Listener: message-based trigger ──────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        content = message.content.strip()
        if not content:
            return

        # Support prefix with ! or /
        name = None
        if content.startswith("!"):
            name = content[1:].split()[0].lower()

        if not name:
            return

        cmd = self.db.get(message.guild.id, name)
        if not cmd:
            return

        self.db.increment_uses(message.guild.id, name)

        # Interpolate variables in the response
        response = cmd["response"]
        response = response.replace("{user}", message.author.mention)
        response = response.replace("{username}", message.author.display_name)
        response = response.replace("{server}", message.guild.name)
        response = response.replace("{membercount}", str(message.guild.member_count))

        await message.channel.send(response)

    # ── Slash Commands ────────────────────────────────────────────────────────

    cc = app_commands.Group(name="cc", description="Custom command management")

    @cc.command(name="create", description="Create a custom command")
    @app_commands.describe(
        name="The command name (triggered with !name)",
        response="The response text. Use {user}, {username}, {server}, {membercount}"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def create(self, interaction: discord.Interaction, name: str, response: str) -> None:
        if len(name) > 30:
            await interaction.response.send_message("❌ Command name must be 30 characters or fewer.", ephemeral=True)
            return
        if len(response) > 2000:
            await interaction.response.send_message("❌ Response must be 2000 characters or fewer.", ephemeral=True)
            return

        success = self.db.create(interaction.guild.id, name, response, interaction.user.id)
        if success:
            await interaction.response.send_message(
                f"✅ Custom command `!{name.lower()}` created! Users can trigger it by typing `!{name.lower()}`.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(f"❌ A command named `!{name.lower()}` already exists. Use `/cc edit` to update it.", ephemeral=True)

    @cc.command(name="edit", description="Edit an existing custom command's response")
    @app_commands.describe(name="The command name to edit", response="New response text")
    @app_commands.default_permissions(manage_guild=True)
    async def edit(self, interaction: discord.Interaction, name: str, response: str) -> None:
        success = self.db.edit(interaction.guild.id, name, response)
        if success:
            await interaction.response.send_message(f"✅ Command `!{name.lower()}` updated.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Command `!{name.lower()}` not found.", ephemeral=True)

    @cc.command(name="delete", description="Delete a custom command")
    @app_commands.describe(name="The command name to delete")
    @app_commands.default_permissions(manage_guild=True)
    async def delete(self, interaction: discord.Interaction, name: str) -> None:
        success = self.db.delete(interaction.guild.id, name)
        if success:
            await interaction.response.send_message(f"✅ Command `!{name.lower()}` deleted.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Command `!{name.lower()}` not found.", ephemeral=True)

    @cc.command(name="list", description="List all custom commands in this server")
    async def list_cmds(self, interaction: discord.Interaction) -> None:
        cmds = self.db.list_all(interaction.guild.id)
        if not cmds:
            await interaction.response.send_message("📋 No custom commands yet. Create one with `/cc create`.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📋 Custom Commands — {interaction.guild.name}",
            color=0x3498DB,
            description=f"Total: **{len(cmds)}** commands"
        )
        for cmd in cmds[:25]:
            preview = cmd["response"][:60] + ("..." if len(cmd["response"]) > 60 else "")
            embed.add_field(
                name=f"!{cmd['name']} (used {cmd['uses']}×)",
                value=preview,
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @cc.command(name="info", description="Show details of a specific custom command")
    @app_commands.describe(name="The command name")
    async def info(self, interaction: discord.Interaction, name: str) -> None:
        cmd = self.db.get(interaction.guild.id, name)
        if not cmd:
            await interaction.response.send_message(f"❌ Command `!{name.lower()}` not found.", ephemeral=True)
            return
        embed = discord.Embed(title=f"📋 !{cmd['name']}", color=0x3498DB)
        embed.add_field(name="Response", value=cmd["response"][:1024], inline=False)
        embed.add_field(name="Uses", value=str(cmd["uses"]), inline=True)
        embed.add_field(name="Created by", value=f"<@{cmd['created_by']}>", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCommandsCog(bot))
