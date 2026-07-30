"""
server_template.py — Full Server Template System for GKR Bot.

Features:
  • /template save <name>     — Snapshot current server (roles, categories, channels, overwrites)
  • /template load <name>     — Replay template onto any server (rate-limit-safe, staged)
  • /template list            — List all saved templates
  • /template info <name>     — Preview template contents
  • /template delete <name>   — Remove a saved template
  • /template wipe            — Clear server channels/roles (double-confirm)
  • /template export <name>   — Download template as JSON file
  • /template import          — Upload JSON file to import template
  • /template roles save <name> — Save roles only
  • /template roles load <name> — Apply roles only (rate-limit-safe)

Rate limiting strategy:
  - 1.0s delay between each role creation
  - 1.5s delay between each category creation
  - 1.2s delay between each channel creation
  - 0.5s delay between permission overwrite patches
  - Live progress embed edited as each phase completes
"""

from __future__ import annotations

import asyncio
import datetime
import io
import json
import os
import sqlite3
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "server_templates.sqlite3")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS server_templates (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL UNIQUE,
                guild_id   INTEGER NOT NULL,
                guild_name TEXT    NOT NULL,
                saved_by   INTEGER NOT NULL,
                saved_at   TEXT    NOT NULL,
                payload    TEXT    NOT NULL
            )
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def _serialize_permissions(overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite]) -> dict:
    """Turn channel permission overwrites into a portable dict keyed by role/member name."""
    result = {}
    for target, overwrite in overwrites.items():
        if isinstance(target, discord.Member):
            continue  # skip member-level overwrites for portability
        allow, deny = overwrite.pair()
        result[target.name] = {"allow": allow.value, "deny": deny.value}
    return result


async def _snapshot_guild(guild: discord.Guild) -> dict:
    """Capture full server structure into a JSON-serialisable dict."""
    # Roles (skip @everyone and bot-managed roles, preserve position order)
    roles_data = []
    for role in sorted(guild.roles, key=lambda r: r.position):
        if role.is_bot_managed() or role.is_integration() or role.is_premium_subscriber():
            continue
        roles_data.append({
            "name": role.name,
            "color": role.color.value,
            "permissions": role.permissions.value,
            "hoist": role.hoist,
            "mentionable": role.mentionable,
            "position": role.position,
        })

    categories_data = []
    text_channels_data = []
    voice_channels_data = []
    forum_channels_data = []

    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            categories_data.append({
                "name": ch.name,
                "position": ch.position,
                "overwrites": _serialize_permissions(ch.overwrites),
            })
        elif isinstance(ch, discord.TextChannel):
            text_channels_data.append({
                "name": ch.name,
                "topic": ch.topic or "",
                "slowmode_delay": ch.slowmode_delay,
                "nsfw": ch.nsfw,
                "position": ch.position,
                "category": ch.category.name if ch.category else None,
                "overwrites": _serialize_permissions(ch.overwrites),
            })
        elif isinstance(ch, discord.VoiceChannel):
            voice_channels_data.append({
                "name": ch.name,
                "bitrate": ch.bitrate,
                "user_limit": ch.user_limit,
                "position": ch.position,
                "category": ch.category.name if ch.category else None,
                "overwrites": _serialize_permissions(ch.overwrites),
            })
        elif isinstance(ch, discord.ForumChannel):
            forum_channels_data.append({
                "name": ch.name,
                "topic": ch.topic or "",
                "position": ch.position,
                "category": ch.category.name if ch.category else None,
                "overwrites": _serialize_permissions(ch.overwrites),
            })

    # Sort by position for deterministic replay
    categories_data.sort(key=lambda c: c["position"])
    text_channels_data.sort(key=lambda c: c["position"])
    voice_channels_data.sort(key=lambda c: c["position"])
    forum_channels_data.sort(key=lambda c: c["position"])

    return {
        "server": {
            "name": guild.name,
            "description": guild.description or "",
            "verification_level": guild.verification_level.value,
        },
        "roles": roles_data,
        "categories": categories_data,
        "text_channels": text_channels_data,
        "voice_channels": voice_channels_data,
        "forum_channels": forum_channels_data,
    }


# ---------------------------------------------------------------------------
# Load helpers  (rate-limit-aware)
# ---------------------------------------------------------------------------

# Delays between API calls (seconds) — tune these to stay under Discord limits
DELAY_ROLE     = 6.0   # between each role.create()
DELAY_CATEGORY = 6.5   # between each category.create()
DELAY_CHANNEL  = 6.2   # between each channel.create()
DELAY_OVERWRITE = 5.5  # between each permission overwrite set


def _build_overwrite_dict(
    overwrites_raw: dict, guild: discord.Guild
) -> dict[discord.Role, discord.PermissionOverwrite]:
    """Rebuild overwrites dict from saved payload, matching roles by name."""
    result = {}
    for role_name, bits in overwrites_raw.items():
        if role_name == "@everyone":
            target = guild.default_role
        else:
            target = discord.utils.get(guild.roles, name=role_name)
        if target is None:
            continue
        allow = discord.Permissions(bits["allow"])
        deny = discord.Permissions(bits["deny"])
        ow = discord.PermissionOverwrite.from_pair(allow, deny)
        result[target] = ow
    return result


async def _load_template(
    guild: discord.Guild,
    payload: dict,
    progress_msg: discord.Message,
    roles_only: bool = False,
) -> dict:
    """
    Apply a template snapshot to a guild.
    Returns a summary dict {created_roles, created_categories, created_channels, errors}.
    Updates `progress_msg` as each phase completes.
    """
    summary = {
        "created_roles": 0,
        "created_categories": 0,
        "created_channels": 0,
        "errors": [],
    }

    async def _edit_progress(text: str):
        try:
            embed = discord.Embed(
                title="⏳ Loading Template…",
                description=text,
                color=0x8A2BE2,
            )
            embed.set_footer(text="GKR Template System • Rate-limited loading in progress")
            await progress_msg.edit(embed=embed)
        except Exception:
            pass

    # ── Phase 1: Roles ──────────────────────────────────────────────────────
    await _edit_progress("**Phase 1/4** — Creating roles… 🎭")
    # Exclude @everyone (position 0) from creation since it always exists
    roles_to_create = [r for r in payload.get("roles", []) if r["name"] != "@everyone"]
    existing_role_names = {r.name for r in guild.roles}

    for i, role_data in enumerate(roles_to_create):
        if role_data["name"] in existing_role_names:
            await _edit_progress(
                f"**Phase 1/4** — Roles ({i+1}/{len(roles_to_create)}) "
                f"⏭️ Skipped **{role_data['name']}** (already exists)"
            )
            await asyncio.sleep(DELAY_ROLE * 0.3)
            continue
        try:
            await guild.create_role(
                name=role_data["name"],
                color=discord.Color(role_data["color"]),
                permissions=discord.Permissions(role_data["permissions"]),
                hoist=role_data["hoist"],
                mentionable=role_data["mentionable"],
                reason="GKR Template Load",
            )
            summary["created_roles"] += 1
            await _edit_progress(
                f"**Phase 1/4** — Roles ({i+1}/{len(roles_to_create)}) "
                f"✅ Created **{role_data['name']}**"
            )
        except discord.Forbidden:
            summary["errors"].append(f"Forbidden: cannot create role `{role_data['name']}`")
        except Exception as e:
            summary["errors"].append(f"Role `{role_data['name']}`: {e}")
        await asyncio.sleep(DELAY_ROLE)

    if roles_only:
        return summary

    # ── Phase 2: Categories ─────────────────────────────────────────────────
    await _edit_progress("**Phase 2/4** — Creating categories… 📁")
    categories_to_create = payload.get("categories", [])
    existing_cat_names = {
        c.name for c in guild.channels if isinstance(c, discord.CategoryChannel)
    }
    # Map name → CategoryChannel (after creation) for channel association
    cat_map: dict[str, discord.CategoryChannel] = {
        c.name: c for c in guild.channels if isinstance(c, discord.CategoryChannel)
    }

    for i, cat_data in enumerate(categories_to_create):
        if cat_data["name"] not in existing_cat_names:
            try:
                overwrites = _build_overwrite_dict(cat_data.get("overwrites", {}), guild)
                new_cat = await guild.create_category(
                    name=cat_data["name"],
                    overwrites=overwrites,
                    reason="GKR Template Load",
                )
                cat_map[cat_data["name"]] = new_cat
                summary["created_categories"] += 1
                await _edit_progress(
                    f"**Phase 2/4** — Categories ({i+1}/{len(categories_to_create)}) "
                    f"✅ Created **{cat_data['name']}**"
                )
            except discord.Forbidden:
                summary["errors"].append(f"Forbidden: cannot create category `{cat_data['name']}`")
            except Exception as e:
                summary["errors"].append(f"Category `{cat_data['name']}`: {e}")
            await asyncio.sleep(DELAY_CATEGORY)
        else:
            await _edit_progress(
                f"**Phase 2/4** — Categories ({i+1}/{len(categories_to_create)}) "
                f"⏭️ Skipped **{cat_data['name']}** (already exists)"
            )
            await asyncio.sleep(DELAY_CATEGORY * 0.3)

    # ── Phase 3: Text Channels ──────────────────────────────────────────────
    await _edit_progress("**Phase 3/4** — Creating text channels… 💬")
    all_channels_to_create = (
        [("text", ch) for ch in payload.get("text_channels", [])]
        + [("voice", ch) for ch in payload.get("voice_channels", [])]
        + [("forum", ch) for ch in payload.get("forum_channels", [])]
    )
    existing_ch_names = {c.name for c in guild.channels if not isinstance(c, discord.CategoryChannel)}

    for i, (ch_type, ch_data) in enumerate(all_channels_to_create):
        label = f"Phase 3/4 — Channels ({i+1}/{len(all_channels_to_create)})"
        category = cat_map.get(ch_data.get("category")) if ch_data.get("category") else None
        overwrites = _build_overwrite_dict(ch_data.get("overwrites", {}), guild)

        if ch_data["name"] in existing_ch_names:
            await _edit_progress(f"**{label}** ⏭️ Skipped **#{ch_data['name']}** (exists)")
            await asyncio.sleep(DELAY_CHANNEL * 0.3)
            continue

        try:
            if ch_type == "text":
                await guild.create_text_channel(
                    name=ch_data["name"],
                    topic=ch_data.get("topic") or None,
                    slowmode_delay=ch_data.get("slowmode_delay", 0),
                    nsfw=ch_data.get("nsfw", False),
                    category=category,
                    overwrites=overwrites,
                    reason="GKR Template Load",
                )
            elif ch_type == "voice":
                await guild.create_voice_channel(
                    name=ch_data["name"],
                    bitrate=min(ch_data.get("bitrate", 64000), guild.bitrate_limit),
                    user_limit=ch_data.get("user_limit", 0),
                    category=category,
                    overwrites=overwrites,
                    reason="GKR Template Load",
                )
            elif ch_type == "forum":
                await guild.create_forum(
                    name=ch_data["name"],
                    topic=ch_data.get("topic") or None,
                    category=category,
                    overwrites=overwrites,
                    reason="GKR Template Load",
                )
            summary["created_channels"] += 1
            await _edit_progress(f"**{label}** ✅ Created **#{ch_data['name']}**")
        except discord.Forbidden:
            summary["errors"].append(f"Forbidden: cannot create channel `#{ch_data['name']}`")
        except Exception as e:
            summary["errors"].append(f"Channel `#{ch_data['name']}`: {e}")
        await asyncio.sleep(DELAY_CHANNEL)

    # ── Phase 4: Done ───────────────────────────────────────────────────────
    await _edit_progress("**Phase 4/4** — Finalizing… ✅")
    return summary


# ---------------------------------------------------------------------------
# Wipe confirmation view
# ---------------------------------------------------------------------------

class WipeConfirmView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=60)
        self.guild = guild
        self.confirmed = False

    @discord.ui.button(label="⚠️ Yes, WIPE the server", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.guild.owner and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can confirm this.", ephemeral=True)
            return
        self.confirmed = True
        self.stop()
        await interaction.response.send_message("🔥 Wiping server… this may take a while.", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_message("✅ Cancelled. Nothing was changed.", ephemeral=True)


# ---------------------------------------------------------------------------
# Owner Check
# ---------------------------------------------------------------------------

def is_bot_owner():
    def predicate(interaction: discord.Interaction) -> bool:
        owner_id_str = os.getenv("OWNER_DISCORD_ID")
        if not owner_id_str:
            return False
        return interaction.user.id == int(owner_id_str)
    return app_commands.check(predicate)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class ServerTemplateCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Command groups ──────────────────────────────────────────────────────

    template_group = app_commands.Group(
        name="template",
        description="Full server template system — save, load, export, import",
    )
    roles_group = app_commands.Group(
        name="roles",
        description="Roles-only template save/load",
        parent=template_group,
    )

    # ── /template save ──────────────────────────────────────────────────────

    @template_group.command(name="save", description="Snapshot this entire server as a reusable template")
    @app_commands.describe(name="Template name (unique)")
    @is_bot_owner()
    async def save(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # Check name availability
        with _db() as conn:
            existing = conn.execute(
                "SELECT id FROM server_templates WHERE name = ?", (name,)
            ).fetchone()
        if existing:
            await interaction.followup.send(
                f"❌ A template named **{name}** already exists. Use `/template delete` first or choose a different name.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"📸 Snapshotting **{guild.name}**… this may take a few seconds.", ephemeral=True
        )

        try:
            payload = await _snapshot_guild(guild)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to snapshot server: {e}", ephemeral=True)
            return

        with _db() as conn:
            conn.execute(
                """INSERT INTO server_templates (name, guild_id, guild_name, saved_by, saved_at, payload)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    name, guild.id, guild.name, interaction.user.id,
                    datetime.datetime.utcnow().isoformat(),
                    json.dumps(payload),
                ),
            )
            conn.commit()

        embed = discord.Embed(
            title="✅ Template Saved!",
            color=0x2ECC71,
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="Name", value=f"`{name}`", inline=True)
        embed.add_field(name="Roles", value=str(len(payload["roles"])), inline=True)
        embed.add_field(name="Categories", value=str(len(payload["categories"])), inline=True)
        embed.add_field(name="Text Channels", value=str(len(payload["text_channels"])), inline=True)
        embed.add_field(name="Voice Channels", value=str(len(payload["voice_channels"])), inline=True)
        embed.add_field(name="Forum Channels", value=str(len(payload["forum_channels"])), inline=True)
        embed.set_footer(text=f"Saved by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /template load ──────────────────────────────────────────────────────

    @template_group.command(
        name="load",
        description="Apply a saved template to this server (rate-limit-safe, staged loading)"
    )
    @app_commands.describe(name="Name of the template to load")
    @is_bot_owner()
    async def load(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=False)

        with _db() as conn:
            row = conn.execute(
                "SELECT payload FROM server_templates WHERE name = ?", (name,)
            ).fetchone()
        if not row:
            await interaction.followup.send(
                f"❌ No template named **{name}** found. Use `/template list` to see available templates.",
                ephemeral=True,
            )
            return

        payload = json.loads(row["payload"])
        guild = interaction.guild

        # Post a live progress embed (public so everyone can see the loading)
        embed = discord.Embed(
            title="⏳ Loading Template…",
            description="**Phase 1/4** — Preparing…",
            color=0x8A2BE2,
        )
        embed.set_footer(text="GKR Template System • Rate-limited loading in progress")
        progress_msg = await interaction.followup.send(embed=embed)

        try:
            summary = await _load_template(guild, payload, progress_msg, roles_only=False)
        except Exception as e:
            await progress_msg.edit(
                embed=discord.Embed(
                    title="❌ Template Load Failed",
                    description=str(e),
                    color=0xFF0000,
                )
            )
            return

        # Final report
        error_text = ""
        if summary["errors"]:
            error_text = "\n\n**⚠️ Errors:**\n" + "\n".join(f"• {e}" for e in summary["errors"][:10])

        final_embed = discord.Embed(
            title="✅ Template Loaded!",
            description=(
                f"**Template:** `{name}`\n\n"
                f"✅ **{summary['created_roles']}** roles created\n"
                f"✅ **{summary['created_categories']}** categories created\n"
                f"✅ **{summary['created_channels']}** channels created"
                + error_text
            ),
            color=0x2ECC71,
            timestamp=datetime.datetime.utcnow(),
        )
        final_embed.set_footer(text=f"Loaded by {interaction.user.display_name} • GKR Template System")
        await progress_msg.edit(embed=final_embed)

    # ── /template list ──────────────────────────────────────────────────────

    @template_group.command(name="list", description="List all saved server templates")
    @is_bot_owner()
    async def list_templates(self, interaction: discord.Interaction) -> None:
        with _db() as conn:
            rows = conn.execute(
                "SELECT name, guild_name, saved_by, saved_at FROM server_templates ORDER BY saved_at DESC"
            ).fetchall()

        if not rows:
            await interaction.response.send_message(
                "📭 No templates saved yet. Use `/template save` to create one.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📦 Saved Server Templates",
            color=0x8A2BE2,
            timestamp=datetime.datetime.utcnow(),
        )
        for row in rows[:20]:
            saved_user = self.bot.get_user(row["saved_by"])
            saved_by_str = saved_user.name if saved_user else f"User {row['saved_by']}"
            date_str = row["saved_at"][:10]
            embed.add_field(
                name=f"📋 `{row['name']}`",
                value=f"Source: **{row['guild_name']}**\nSaved by: {saved_by_str} on {date_str}",
                inline=True,
            )
        embed.set_footer(text="Use /template info <name> for details")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /template info ──────────────────────────────────────────────────────

    @template_group.command(name="info", description="Preview what a saved template contains")
    @app_commands.describe(name="Template name to preview")
    @is_bot_owner()
    async def info(self, interaction: discord.Interaction, name: str) -> None:
        with _db() as conn:
            row = conn.execute(
                "SELECT * FROM server_templates WHERE name = ?", (name,)
            ).fetchone()
        if not row:
            await interaction.response.send_message(f"❌ No template named **{name}** found.", ephemeral=True)
            return

        payload = json.loads(row["payload"])
        saved_user = self.bot.get_user(row["saved_by"])
        saved_by_str = saved_user.mention if saved_user else f"User {row['saved_by']}"

        embed = discord.Embed(
            title=f"📋 Template: `{name}`",
            color=0x5865F2,
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="Source Server", value=row["guild_name"], inline=True)
        embed.add_field(name="Saved By", value=saved_by_str, inline=True)
        embed.add_field(name="Saved At", value=row["saved_at"][:19].replace("T", " "), inline=True)
        embed.add_field(name="🎭 Roles", value=str(len(payload["roles"])), inline=True)
        embed.add_field(name="📁 Categories", value=str(len(payload["categories"])), inline=True)
        embed.add_field(name="💬 Text Channels", value=str(len(payload["text_channels"])), inline=True)
        embed.add_field(name="🔊 Voice Channels", value=str(len(payload["voice_channels"])), inline=True)
        embed.add_field(name="🗂️ Forum Channels", value=str(len(payload["forum_channels"])), inline=True)

        # List role names
        role_names = [r["name"] for r in payload["roles"] if r["name"] != "@everyone"]
        if role_names:
            embed.add_field(
                name="Roles",
                value=", ".join(f"`{r}`" for r in role_names[:30])
                      + (f"… +{len(role_names)-30} more" if len(role_names) > 30 else ""),
                inline=False,
            )

        # List category names
        cat_names = [c["name"] for c in payload["categories"]]
        if cat_names:
            embed.add_field(
                name="Categories",
                value=", ".join(f"`{c}`" for c in cat_names[:20]),
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /template delete ────────────────────────────────────────────────────

    @template_group.command(name="delete", description="Delete a saved template")
    @app_commands.describe(name="Template name to delete")
    @is_bot_owner()
    async def delete(self, interaction: discord.Interaction, name: str) -> None:
        with _db() as conn:
            cur = conn.execute("DELETE FROM server_templates WHERE name = ?", (name,))
            conn.commit()
            deleted = cur.rowcount > 0
        if deleted:
            await interaction.response.send_message(f"🗑️ Template **{name}** deleted.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ No template named **{name}** found.", ephemeral=True)

    # ── /template export ────────────────────────────────────────────────────

    @template_group.command(name="export", description="Download a template as a portable JSON file")
    @app_commands.describe(name="Template name to export")
    @is_bot_owner()
    async def export(self, interaction: discord.Interaction, name: str) -> None:
        with _db() as conn:
            row = conn.execute("SELECT payload, guild_name FROM server_templates WHERE name = ?", (name,)).fetchone()
        if not row:
            await interaction.response.send_message(f"❌ No template named **{name}** found.", ephemeral=True)
            return

        # Wrap with metadata
        export_obj = {
            "_meta": {
                "template_name": name,
                "source_guild": row["guild_name"],
                "exported_at": datetime.datetime.utcnow().isoformat(),
                "version": "1.0",
            },
            "data": json.loads(row["payload"]),
        }
        raw = json.dumps(export_obj, indent=2, ensure_ascii=False)
        file = discord.File(
            fp=io.BytesIO(raw.encode("utf-8")),
            filename=f"template_{name.replace(' ', '_')}.json",
        )
        await interaction.response.send_message(
            f"📤 Here is your template **{name}** as a JSON file:", file=file, ephemeral=True
        )

    # ── /template import ────────────────────────────────────────────────────

    @template_group.command(name="import", description="Import a template from an uploaded JSON file")
    @app_commands.describe(
        file="The .json template file to import",
        name="Custom name for this template (optional — uses file's original name if blank)",
    )
    @is_bot_owner()
    async def import_template(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        name: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if not file.filename.endswith(".json"):
            await interaction.followup.send("❌ Please upload a `.json` template file.", ephemeral=True)
            return

        try:
            raw = await file.read()
            import_obj = json.loads(raw.decode("utf-8"))
        except Exception as e:
            await interaction.followup.send(f"❌ Could not parse JSON: {e}", ephemeral=True)
            return

        # Support both wrapped (exported) and bare payload formats
        if "_meta" in import_obj and "data" in import_obj:
            meta = import_obj["_meta"]
            payload = import_obj["data"]
            template_name = name or meta.get("template_name", "imported_template")
        else:
            payload = import_obj
            template_name = name or "imported_template"

        # Basic validation
        if not isinstance(payload.get("roles"), list) or not isinstance(payload.get("categories"), list):
            await interaction.followup.send(
                "❌ Invalid template format. Expected keys: `roles`, `categories`, `text_channels`, `voice_channels`.",
                ephemeral=True,
            )
            return

        # Check name conflict
        with _db() as conn:
            existing = conn.execute(
                "SELECT id FROM server_templates WHERE name = ?", (template_name,)
            ).fetchone()
        if existing:
            await interaction.followup.send(
                f"❌ A template named **{template_name}** already exists. Provide a different `name`.",
                ephemeral=True,
            )
            return

        with _db() as conn:
            conn.execute(
                """INSERT INTO server_templates (name, guild_id, guild_name, saved_by, saved_at, payload)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    template_name,
                    interaction.guild.id,
                    interaction.guild.name,
                    interaction.user.id,
                    datetime.datetime.utcnow().isoformat(),
                    json.dumps(payload),
                ),
            )
            conn.commit()

        embed = discord.Embed(
            title="✅ Template Imported!",
            description=f"Template **{template_name}** imported successfully.",
            color=0x2ECC71,
        )
        embed.add_field(name="🎭 Roles", value=str(len(payload.get("roles", []))), inline=True)
        embed.add_field(name="📁 Categories", value=str(len(payload.get("categories", []))), inline=True)
        embed.add_field(name="💬 Text Channels", value=str(len(payload.get("text_channels", []))), inline=True)
        embed.add_field(name="🔊 Voice Channels", value=str(len(payload.get("voice_channels", []))), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /template wipe ──────────────────────────────────────────────────────

    @template_group.command(
        name="wipe",
        description="⚠️ Delete ALL channels and non-default roles (use before loading a fresh template)"
    )
    @is_bot_owner()
    async def wipe(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        view = WipeConfirmView(guild)
        embed = discord.Embed(
            title="⚠️ DANGER: Server Wipe",
            description=(
                "This will **permanently delete** all channels and all non-default, non-bot roles "
                f"from **{guild.name}**.\n\n"
                "This is intended to prepare a server for a clean template load.\n\n"
                "**There is no undo.** Are you sure?"
            ),
            color=0xFF0000,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()

        if not view.confirmed:
            return

        # Wipe channels
        failed_ch = 0
        for ch in list(guild.channels):
            try:
                await ch.delete(reason="GKR Template Wipe")
                await asyncio.sleep(0.8)
            except Exception:
                failed_ch += 1

        # Wipe roles (skip @everyone, bot-managed, integration roles)
        failed_roles = 0
        for role in list(guild.roles):
            if role.is_default() or role.is_bot_managed() or role.is_integration() or role.is_premium_subscriber():
                continue
            if role >= guild.me.top_role:
                failed_roles += 1
                continue
            try:
                await role.delete(reason="GKR Template Wipe")
                await asyncio.sleep(0.8)
            except Exception:
                failed_roles += 1

        # Try to send a summary somewhere the bot can
        try:
            summary_ch = guild.system_channel or next(
                (c for c in guild.text_channels), None
            )
            if summary_ch:
                await summary_ch.send(
                    embed=discord.Embed(
                        title="🔥 Server Wiped",
                        description=(
                            f"Wipe complete.\n"
                            f"• Channels failed to delete: {failed_ch}\n"
                            f"• Roles failed to delete: {failed_roles}\n\n"
                            "You can now run `/template load` to apply a fresh template."
                        ),
                        color=0xFF6B6B,
                    )
                )
        except Exception:
            pass

    # ── /template roles save ────────────────────────────────────────────────

    @roles_group.command(name="save", description="Snapshot only the roles of this server")
    @app_commands.describe(name="Template name for this role set")
    @is_bot_owner()
    async def roles_save(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        with _db() as conn:
            existing = conn.execute("SELECT id FROM server_templates WHERE name = ?", (name,)).fetchone()
        if existing:
            await interaction.followup.send(
                f"❌ A template named **{name}** already exists.", ephemeral=True
            )
            return

        roles_data = []
        for role in sorted(guild.roles, key=lambda r: r.position):
            if role.is_bot_managed() or role.is_integration() or role.is_premium_subscriber():
                continue
            roles_data.append({
                "name": role.name,
                "color": role.color.value,
                "permissions": role.permissions.value,
                "hoist": role.hoist,
                "mentionable": role.mentionable,
                "position": role.position,
            })

        payload = {
            "server": {"name": guild.name},
            "roles": roles_data,
            "categories": [],
            "text_channels": [],
            "voice_channels": [],
            "forum_channels": [],
        }

        with _db() as conn:
            conn.execute(
                """INSERT INTO server_templates (name, guild_id, guild_name, saved_by, saved_at, payload)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    name, guild.id, guild.name, interaction.user.id,
                    datetime.datetime.utcnow().isoformat(),
                    json.dumps(payload),
                ),
            )
            conn.commit()

        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Role Template Saved",
                description=f"**{len(roles_data)}** roles saved as template `{name}`.",
                color=0x2ECC71,
            ),
            ephemeral=True,
        )

    # ── /template roles load ────────────────────────────────────────────────

    @roles_group.command(
        name="load",
        description="Apply a saved role template to this server (rate-limit-safe)"
    )
    @app_commands.describe(name="Template name to load roles from")
    @is_bot_owner()
    async def roles_load(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=False)

        with _db() as conn:
            row = conn.execute(
                "SELECT payload FROM server_templates WHERE name = ?", (name,)
            ).fetchone()
        if not row:
            await interaction.followup.send(
                f"❌ No template named **{name}** found.", ephemeral=True
            )
            return

        payload = json.loads(row["payload"])
        guild = interaction.guild

        embed = discord.Embed(
            title="⏳ Loading Roles…",
            description="**Phase 1/1** — Preparing…",
            color=0x8A2BE2,
        )
        progress_msg = await interaction.followup.send(embed=embed)

        try:
            summary = await _load_template(guild, payload, progress_msg, roles_only=True)
        except Exception as e:
            await progress_msg.edit(
                embed=discord.Embed(title="❌ Role Load Failed", description=str(e), color=0xFF0000)
            )
            return

        error_text = ""
        if summary["errors"]:
            error_text = "\n\n**⚠️ Errors:**\n" + "\n".join(f"• {e}" for e in summary["errors"][:10])

        final_embed = discord.Embed(
            title="✅ Roles Loaded!",
            description=(
                f"**Template:** `{name}`\n"
                f"✅ **{summary['created_roles']}** roles created"
                + error_text
            ),
            color=0x2ECC71,
            timestamp=datetime.datetime.utcnow(),
        )
        final_embed.set_footer(text=f"Loaded by {interaction.user.display_name}")
        await progress_msg.edit(embed=final_embed)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot) -> None:
    _init_db()
    await bot.add_cog(ServerTemplateCog(bot))
    print("📦 Server Template System loaded!")
