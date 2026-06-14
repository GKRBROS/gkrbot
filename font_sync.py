from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

import discord
from discord import app_commands


DB_PATH = os.path.join(os.path.dirname(__file__), "font_sync.sqlite3")


# ---------------------------------------------------------------------------
# Font conversion utilities
# ---------------------------------------------------------------------------


def _build_font_map(upper_start: int, lower_start: int, digit_start: Optional[int] = None) -> dict[str, str]:
    mapping: dict[str, str] = {}

    for index, source in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        mapping[source] = chr(upper_start + index)

    for index, source in enumerate("abcdefghijklmnopqrstuvwxyz"):
        mapping[source] = chr(lower_start + index)

    if digit_start is not None:
        for index, source in enumerate("0123456789"):
            mapping[source] = chr(digit_start + index)

    return mapping


FONT_STYLES: dict[str, dict[str, str]] = {
    "classic": {},
    "bold": _build_font_map(0x1D400, 0x1D41A, 0x1D7CE),
    "italic": _build_font_map(0x1D434, 0x1D44E),
    "bold_italic": _build_font_map(0x1D468, 0x1D482),
    "sans": _build_font_map(0x1D5A0, 0x1D5BA, 0x1D7E2),
    "sans_bold": _build_font_map(0x1D5D4, 0x1D5EE, 0x1D7EC),
    "sans_italic": _build_font_map(0x1D608, 0x1D622),
    "sans_bold_italic": _build_font_map(0x1D63C, 0x1D656),
    "monospace": _build_font_map(0x1D670, 0x1D68A, 0x1D7F6),
    "custom": {},  # Populated per-guild from FontSyncConfig.custom_font
}

FONT_STYLE_LABELS: dict[str, str] = {
    "classic": "Classic",
    "bold": "Bold",
    "italic": "Italic",
    "bold_italic": "Bold Italic",
    "sans": "Sans",
    "sans_bold": "Sans Bold",
    "sans_italic": "Sans Italic",
    "sans_bold_italic": "Sans Bold Italic",
    "monospace": "Monospace",
    "custom": "Custom ✨",
}

# Reverse map: fancy Unicode char → plain ASCII letter (built-in styles only)
_REVERSE_FONT_MAP: dict[str, str] = {}
for _style_map in FONT_STYLES.values():
    for _plain, _fancy in _style_map.items():
        _REVERSE_FONT_MAP[_fancy] = _plain


def available_font_styles() -> list[dict[str, str]]:
    styles = []
    sample_base = "gkr-server-123"
    for style_name, label in FONT_STYLE_LABELS.items():
        styles.append(
            {
                "name": style_name,
                "label": label,
                "preview": apply_font(sample_base, style_name),
            }
        )
    return styles


def normalize_font_text(text: str) -> str:
    """Reverse built-in font chars to plain ASCII. Other chars are passed through unchanged."""
    return "".join(_REVERSE_FONT_MAP.get(char, char) for char in text)


DECORATION_STYLES: dict[str, tuple[str, str]] = {
    "none": ("", ""),
    "brackets": ("[", "]"),
    "double_brackets": ("[[", "]]"),
    "frames": ("【", "】"),
    "curly": ("{", "}"),
    "stars": ("✦ ", " ✦"),
    "arrows": ("» ", " «"),
    "diamonds": ("❖ ", " ❖"),
    "shells": ("🐚 ", " 🐚"),
}

DECORATION_LABELS: dict[str, str] = {
    "none": "No Decoration",
    "brackets": "[ Brackets ]",
    "double_brackets": "[[ Double Brackets ]]",
    "frames": "【 Frames 】",
    "curly": "{ Curly }",
    "stars": "✦ Stars ✦",
    "arrows": "» Arrows «",
    "diamonds": "❖ Diamonds ❖",
    "shells": "🐚 Custom Emojis 🐚",
}


def _normalize_name(name: str, custom_reverse: Optional[dict[str, str]] = None) -> str:
    """
    Reverse both built-in font chars AND optional custom font chars back to plain text.
    Also strips any configured decoration prefix/suffix symbols.
    Non-font Unicode (emoji, symbols) pass through unchanged.
    """
    # Strip known decoration brackets/frames/stars/arrows
    cleaned = name
    for prefix, suffix in DECORATION_STYLES.values():
        if prefix and cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
        if suffix and cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            
    # Also strip default markdown/plain ASCII bracket types just in case
    cleaned = cleaned.strip("[]{}()【】»«❖✦ ")

    rev = custom_reverse or {}
    return "".join(_REVERSE_FONT_MAP.get(ch, rev.get(ch, ch)) for ch in cleaned)


def sanitize_channel_base(name: str, custom_reverse: Optional[dict[str, str]] = None) -> str:
    """
    Prepare a channel name for font application.
    - Reverses any existing font (built-in + custom).
    - Converts spaces/underscores to dashes.
    - Lowercases ASCII letters.
    - Preserves emoji and non-ASCII symbols (they pass through unchanged).
    - Strips control characters.
    """
    normalized = _normalize_name(name, custom_reverse)
    result: list[str] = []
    for ch in normalized:
        if ch in " _":
            result.append("-")
        elif ch.isascii():
            if ch.isalpha():
                result.append(ch.lower())
            elif ch in "0123456789.-":
                result.append(ch)
            # Strip ASCII control chars and other invalid channel-name chars silently
        else:
            # Non-ASCII: emoji, Unicode symbols — preserve as-is
            result.append(ch)
    text = re.sub(r"-{2,}", "-", "".join(result)).strip("-")
    return text or "channel"


def sanitize_category_base(name: str, custom_reverse: Optional[dict[str, str]] = None) -> str:
    """
    Prepare a category name for font application.
    - Reverses any existing font (built-in + custom).
    - Preserves spaces, emoji, mixed case, and all other symbols unchanged.
    """
    return _normalize_name(name, custom_reverse)


def apply_font(text: str, style_name: str, custom_map: Optional[dict[str, str]] = None) -> str:
    """
    Apply a Unicode font mapping to text.
    Only chars present in the mapping are converted; everything else (emoji, symbols,
    numbers without a digit map) passes through unchanged.
    """
    if style_name == "custom":
        mapping = custom_map or {}
    else:
        mapping = FONT_STYLES.get(style_name, FONT_STYLES["classic"])
    if not mapping:
        return text
    return text.translate(str.maketrans(mapping))


# ---------------------------------------------------------------------------
# Database layer
# ---------------------------------------------------------------------------


@dataclass
class FontSyncConfig:
    guild_id: int
    enabled: bool = False
    font_style: str = "classic"
    sync_mode: str = "server"
    category_ids: list[int] = field(default_factory=list)
    channel_ids: list[int] = field(default_factory=list)
    custom_font: dict[str, str] = field(default_factory=dict)  # plain letter → styled char
    decoration: str = "none"  # none, brackets, double_brackets, frames, curly, stars, arrows


class FontSyncDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS font_sync_configs (
                    guild_id    TEXT PRIMARY KEY,
                    enabled     INTEGER NOT NULL,
                    font_style  TEXT NOT NULL,
                    sync_mode   TEXT NOT NULL,
                    category_ids TEXT NOT NULL,
                    channel_ids  TEXT NOT NULL,
                    custom_font  TEXT NOT NULL DEFAULT '{}',
                    decoration   TEXT NOT NULL DEFAULT 'none'
                )
                """
            )
            # Migrations for existing schemas
            try:
                connection.execute(
                    "ALTER TABLE font_sync_configs ADD COLUMN custom_font TEXT NOT NULL DEFAULT '{}'"
                )
            except Exception:
                pass
            try:
                connection.execute(
                    "ALTER TABLE font_sync_configs ADD COLUMN decoration TEXT NOT NULL DEFAULT 'none'"
                )
            except Exception:
                pass
            connection.commit()

    def get_config(self, guild_id: int) -> FontSyncConfig:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM font_sync_configs WHERE guild_id = ?",
                (str(guild_id),),
            ).fetchone()

        if not row:
            return FontSyncConfig(guild_id=guild_id)

        col_names = row.keys()
        custom_font_raw = row["custom_font"] if "custom_font" in col_names else "{}"
        decoration = row["decoration"] if "decoration" in col_names else "none"
        return FontSyncConfig(
            guild_id=guild_id,
            enabled=bool(row["enabled"]),
            font_style=row["font_style"],
            sync_mode=row["sync_mode"],
            category_ids=json.loads(row["category_ids"]),
            channel_ids=json.loads(row["channel_ids"]),
            custom_font=json.loads(custom_font_raw or "{}"),
            decoration=decoration,
        )

    def save_config(self, config: FontSyncConfig) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO font_sync_configs (
                    guild_id, enabled, font_style, sync_mode, category_ids, channel_ids, custom_font, decoration
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    enabled      = excluded.enabled,
                    font_style   = excluded.font_style,
                    sync_mode    = excluded.sync_mode,
                    category_ids = excluded.category_ids,
                    channel_ids  = excluded.channel_ids,
                    custom_font  = excluded.custom_font,
                    decoration   = excluded.decoration
                """,
                (
                    str(config.guild_id),
                    1 if config.enabled else 0,
                    config.font_style,
                    config.sync_mode,
                    json.dumps(config.category_ids),
                    json.dumps(config.channel_ids),
                    json.dumps(config.custom_font),
                    config.decoration,
                ),
            )
            connection.commit()


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------


@dataclass
class RenameJob:
    guild_id: int
    channel_id: int
    desired_name: str
    reason: str


class FontSyncService:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.db = FontSyncDatabase()
        self.queue: asyncio.Queue[RenameJob] = asyncio.Queue()
        self.worker_task: Optional[asyncio.Task] = None
        self.pending_channel_ids: set[int] = set()

    async def start(self) -> None:
        await asyncio.to_thread(self.db.initialize)
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._worker(), name="font-sync-worker")

    async def stop(self) -> None:
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

    async def get_config(self, guild_id: int) -> FontSyncConfig:
        return await asyncio.to_thread(self.db.get_config, guild_id)

    async def save_config(self, config: FontSyncConfig) -> None:
        await asyncio.to_thread(self.db.save_config, config)

    def _is_renameable_channel(self, channel: discord.abc.GuildChannel) -> bool:
        # Categories are now included. Only Threads are excluded (they cannot be renamed via edit()).
        return not isinstance(channel, discord.Thread)

    def matches_scope(self, config: FontSyncConfig, channel: discord.abc.GuildChannel) -> bool:
        if not config.enabled or not self._is_renameable_channel(channel):
            return False

        if config.sync_mode == "server":
            return True

        if config.sync_mode == "category_only":
            # Only rename the category headers themselves, not child channels
            return isinstance(channel, discord.CategoryChannel) and channel.id in config.category_ids

        if config.sync_mode == "category_channels_only":
            # Only rename channels within the categories, not headers
            return not isinstance(channel, discord.CategoryChannel) and getattr(channel, "parent_id", None) in config.category_ids

        if config.sync_mode in ("category_combined", "category"):
            # Rename headers AND child channels
            if isinstance(channel, discord.CategoryChannel):
                return channel.id in config.category_ids
            return getattr(channel, "parent_id", None) in config.category_ids

        if config.sync_mode == "channel":
            return channel.id in config.channel_ids

        return False

    def _get_desired_name(self, channel: discord.abc.GuildChannel, config: FontSyncConfig) -> str:
        """
        Compute the correctly-fonted name for a channel or category.

        Reverses both built-in and custom font chars so switching between font
        styles never double-applies or leaves stale styled characters.
        Emoji and non-font Unicode symbols are always preserved.
        Also applies name decorations if configured.
        """
        custom_reverse = {v: k for k, v in config.custom_font.items()} if config.custom_font else None

        if isinstance(channel, discord.CategoryChannel):
            base = sanitize_category_base(channel.name, custom_reverse)
        else:
            base = sanitize_channel_base(channel.name, custom_reverse)

        styled = apply_font(base, config.font_style, config.custom_font or None)
        
        # Apply name decoration
        prefix, suffix = DECORATION_STYLES.get(config.decoration, ("", ""))
        return f"{prefix}{styled}{suffix}"

    async def _worker(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                guild = self.bot.get_guild(job.guild_id)
                if guild is None:
                    continue

                channel = guild.get_channel(job.channel_id)
                if channel is None or not self._is_renameable_channel(channel):
                    continue

                bot_member = guild.me or guild.get_member(self.bot.user.id if self.bot.user else 0)
                if bot_member is None or not channel.permissions_for(bot_member).manage_channels:
                    print(f"[Font Sync] Skipped {channel} - missing Manage Channels permission")
                    continue

                if channel.name == job.desired_name:
                    continue

                await channel.edit(name=job.desired_name, reason=job.reason)
                print(f"[Font Sync] Renamed {channel} -> {job.desired_name} ({job.reason})")
                await asyncio.sleep(1.2)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[Font Sync] Rename failed for channel {job.channel_id}: {exc}")
            finally:
                self.pending_channel_ids.discard(job.channel_id)
                self.queue.task_done()

    async def _enqueue_rename(self, channel: discord.abc.GuildChannel, desired_name: str, reason: str) -> None:
        if channel.id in self.pending_channel_ids:
            return

        self.pending_channel_ids.add(channel.id)
        await self.queue.put(
            RenameJob(
                guild_id=channel.guild.id,
                channel_id=channel.id,
                desired_name=desired_name,
                reason=reason,
            )
        )

    async def _maybe_queue_channel(self, channel: discord.abc.GuildChannel, reason: str) -> None:
        if not self._is_renameable_channel(channel):
            return

        config = await self.get_config(channel.guild.id)
        if not self.matches_scope(config, channel):
            return

        desired_name = self._get_desired_name(channel, config)
        if channel.name != desired_name:
            await self._enqueue_rename(channel, desired_name, reason)

    async def sync_guild(self, guild: discord.Guild, reason: str) -> int:
        config = await self.get_config(guild.id)
        if not config.enabled:
            return 0

        queued = 0
        for channel in guild.channels:
            if not self._is_renameable_channel(channel):
                continue
            if not self.matches_scope(config, channel):
                continue

            desired_name = self._get_desired_name(channel, config)
            if channel.name == desired_name:
                continue

            await self._enqueue_rename(channel, desired_name, reason)
            queued += 1

        return queued

    async def sync_category(self, category: discord.CategoryChannel, reason: str) -> int:
        config = await self.get_config(category.guild.id)
        if not config.enabled or config.sync_mode not in ("category", "category_only", "category_channels_only", "category_combined") or category.id not in config.category_ids:
            return 0

        queued = 0

        # Rename the category header itself
        if config.sync_mode in ("category", "category_only", "category_combined"):
            cat_desired = self._get_desired_name(category, config)
            if category.name != cat_desired:
                await self._enqueue_rename(category, cat_desired, reason)
                queued += 1

        # Rename channels inside the category
        if config.sync_mode in ("category", "category_channels_only", "category_combined"):
            for channel in category.channels:
                if not self._is_renameable_channel(channel):
                    continue

                desired_name = self._get_desired_name(channel, config)
                if channel.name == desired_name:
                    continue

                await self._enqueue_rename(channel, desired_name, reason)
                queued += 1

        return queued

    async def on_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self._maybe_queue_channel(channel, "Font Sync channel create")

    async def on_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        config = await self.get_config(after.guild.id)
        if not config.enabled:
            return

        if isinstance(after, discord.CategoryChannel):
            # Rename the category header itself if it is in scope
            if self.matches_scope(config, after):
                await self._maybe_queue_channel(after, "Font Sync category update")
            # Also resync all child channels when in category mode
            if config.sync_mode in ("category", "category_only", "category_channels_only", "category_combined") and after.id in config.category_ids:
                await self.sync_category(after, "Font Sync category update")
            return

        if self.matches_scope(config, after):
            await self._maybe_queue_channel(after, "Font Sync channel update")

        # Handle a channel moving between categories
        if config.sync_mode in ("category", "category_channels_only", "category_combined") and before.parent_id != after.parent_id:
            parent_ids = {pid for pid in (before.parent_id, after.parent_id) if pid is not None}
            if parent_ids.intersection(config.category_ids):
                for parent_id in parent_ids.intersection(config.category_ids):
                    category = after.guild.get_channel(parent_id)
                    if isinstance(category, discord.CategoryChannel):
                        await self.sync_category(category, "Font Sync category move update")

    async def set_enabled(self, guild_id: int, enabled: bool) -> FontSyncConfig:
        config = await self.get_config(guild_id)
        config.enabled = enabled
        await self.save_config(config)
        return config

    async def set_font_style(self, guild_id: int, font_style: str) -> FontSyncConfig:
        if font_style not in FONT_STYLES:
            raise ValueError("Unknown font style")

        config = await self.get_config(guild_id)
        config.font_style = font_style
        config.enabled = True
        await self.save_config(config)
        return config

    async def set_custom_font(
        self,
        guild_id: int,
        lowercase_chars: str,
        uppercase_chars: str = "",
    ) -> FontSyncConfig:
        """
        Build a custom font map from user-supplied styled character strings and save it.

        lowercase_chars — string of 26 styled chars representing a–z (spaces ignored).
        uppercase_chars — optional string of 26 styled chars for A–Z; if omitted only
                          lowercase letters are mapped.
        """
        plain_lower = "abcdefghijklmnopqrstuvwxyz"
        plain_upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        lower_list = list(lowercase_chars.replace(" ", ""))
        upper_list = list(uppercase_chars.replace(" ", "")) if uppercase_chars.strip() else []

        custom_map: dict[str, str] = {}
        for i, ch in enumerate(lower_list[:26]):
            custom_map[plain_lower[i]] = ch
        for i, ch in enumerate(upper_list[:26]):
            custom_map[plain_upper[i]] = ch

        config = await self.get_config(guild_id)
        config.custom_font = custom_map
        config.font_style = "custom"
        config.enabled = True
        await self.save_config(config)
        return config

    async def set_decoration(self, guild_id: int, decoration: str) -> FontSyncConfig:
        if decoration not in DECORATION_STYLES:
            raise ValueError("Unknown decoration style")

        config = await self.get_config(guild_id)
        config.decoration = decoration
        config.enabled = True
        await self.save_config(config)
        return config

    async def set_scope(
        self,
        guild_id: int,
        sync_mode: str,
        category_ids: Optional[list[int]] = None,
        channel_ids: Optional[list[int]] = None,
    ) -> FontSyncConfig:
        if sync_mode not in {"server", "category", "category_only", "category_channels_only", "category_combined", "channel"}:
            raise ValueError("Unknown sync mode")

        config = await self.get_config(guild_id)
        config.sync_mode = sync_mode
        config.category_ids = category_ids or []
        config.channel_ids = channel_ids or []
        config.enabled = True
        await self.save_config(config)
        return config


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def build_status_embed(guild: discord.Guild, config: FontSyncConfig) -> discord.Embed:
    embed = discord.Embed(
        title="Font Sync Settings",
        description="Manage automatic channel & category font synchronization for this server.",
        color=0x00AAFF if config.enabled else 0x808080,
    )

    embed.add_field(name="Enabled", value="Yes" if config.enabled else "No", inline=True)
    embed.add_field(name="Font", value=FONT_STYLE_LABELS.get(config.font_style, config.font_style), inline=True)
    
    sync_mode_label = config.sync_mode.replace("_", " ").title()
    embed.add_field(name="Scope", value=sync_mode_label, inline=True)

    if config.sync_mode == "server":
        scope_details = "All channels & categories in the guild"
    elif config.sync_mode in ("category", "category_only", "category_channels_only", "category_combined"):
        if config.category_ids:
            category_names = []
            for category_id in config.category_ids:
                category = guild.get_channel(category_id)
                category_names.append(
                    category.name if isinstance(category, discord.CategoryChannel) else str(category_id)
                )
            scope_details = ", ".join(category_names)
        else:
            scope_details = "No categories selected"
    else:
        if config.channel_ids:
            channel_names = []
            for channel_id in config.channel_ids:
                channel = guild.get_channel(channel_id)
                channel_names.append(channel.name if channel else str(channel_id))
            scope_details = ", ".join(channel_names)
        else:
            scope_details = "No channels selected"

    embed.add_field(name="Scope Details", value=scope_details[:1024], inline=False)

    # Preview computation with both font styling and decoration applied
    plain_preview = apply_font("gkr-channel", config.font_style, config.custom_font or None)
    prefix, suffix = DECORATION_STYLES.get(config.decoration, ("", ""))
    preview = f"{prefix}{plain_preview}{suffix}"
    
    embed.add_field(name="Decoration", value=DECORATION_LABELS.get(config.decoration, config.decoration), inline=True)
    embed.add_field(name="Preview", value=preview, inline=False)

    if config.font_style == "custom":
        if config.custom_font:
            embed.add_field(name="Custom Map", value=f"{len(config.custom_font)} chars defined", inline=True)
        else:
            embed.add_field(
                name="⚠️ Custom Font",
                value="No custom font set yet — use the **Custom Font ✨** button.",
                inline=False,
            )

    embed.set_footer(text="Font Sync keeps matching channels and categories aligned automatically")
    return embed


class FontStyleSelect(discord.ui.Select):
    def __init__(self, current_style: str, has_custom_font: bool = False):
        options = []
        for style in available_font_styles():
            if style["name"] == "custom" and not has_custom_font:
                desc = "Define via Custom Font ✨ button first"
            else:
                desc = style["preview"][:100]
            options.append(
                discord.SelectOption(
                    label=style["label"],
                    value=style["name"],
                    description=desc,
                    default=style["name"] == current_style,
                )
            )
        super().__init__(placeholder="Choose a font style", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: FontStyleView = self.view  # type: ignore[assignment]
        view.selected_style = self.values[0]
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class FontStyleView(discord.ui.View):
    def __init__(
        self,
        service: FontSyncService,
        guild: discord.Guild,
        owner_id: int,
        current_style: str,
        custom_font_map: Optional[dict[str, str]] = None,
    ):
        super().__init__(timeout=180)
        self.service = service
        self.guild = guild
        self.owner_id = owner_id
        self.selected_style = current_style
        self.custom_font_map = custom_font_map or {}
        self.add_item(FontStyleSelect(current_style, has_custom_font=bool(custom_font_map)))

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Choose Font Style",
            description="Pick a font style and save it to the database.",
            color=0x8A2BE2,
        )
        embed.add_field(name="Selected", value=FONT_STYLE_LABELS.get(self.selected_style, self.selected_style), inline=False)
        preview = apply_font("gkr-server", self.selected_style, self.custom_font_map or None)
        embed.add_field(name="Preview", value=preview, inline=False)
        if self.selected_style == "custom" and not self.custom_font_map:
            embed.add_field(
                name="⚠️ Note",
                value="No custom font defined yet. Use the **Custom Font ✨** button on the main panel first.",
                inline=False,
            )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the invoking administrator can use this panel.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Save Font", style=discord.ButtonStyle.primary)
    async def save_font(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.selected_style == "custom" and not self.custom_font_map:
            await interaction.response.send_message(
                "❌ No custom font defined yet. Use the **Custom Font ✨** button on the main panel to set one first.",
                ephemeral=True,
            )
            return
        config = await self.service.set_font_style(self.guild.id, self.selected_style)
        await interaction.response.edit_message(
            embed=build_status_embed(self.guild, config),
            view=FontSyncPanelView(self.service, self.guild, self.owner_id, config),
        )
        await interaction.followup.send("Font style saved! Use the **Apply Changes** button on the main panel to update channels.", ephemeral=True)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.get_config(self.guild.id)
        await interaction.response.edit_message(
            embed=build_status_embed(self.guild, config),
            view=FontSyncPanelView(self.service, self.guild, self.owner_id, config),
        )


class ScopeModeSelect(discord.ui.Select):
    def __init__(self, current_mode: str):
        super().__init__(
            placeholder="Choose sync scope",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Entire Server",
                    value="server",
                    description="Sync every channel & category in the guild",
                    default=current_mode == "server",
                ),
                discord.SelectOption(
                    label="Category Headers Only (All)",
                    value="category_only",
                    description="Sync ALL category names/headers (no channels inside)",
                    default=current_mode == "category_only",
                ),
                discord.SelectOption(
                    label="Category Channels Only (All)",
                    value="category_channels_only",
                    description="Sync channels within ALL categories (headers untouched)",
                    default=current_mode == "category_channels_only",
                ),
                discord.SelectOption(
                    label="Category + Channels Combined (All)",
                    value="category_combined",
                    description="Sync category headers AND channels inside all categories",
                    default=current_mode in ("category_combined", "category"),
                ),
                discord.SelectOption(
                    label="Individual Categories",
                    value="category_individual",
                    description="Sync only selected categories & their channels",
                    default=current_mode == "category_individual",
                ),
                discord.SelectOption(
                    label="Individual Channels",
                    value="channel",
                    description="Sync only selected individual channels",
                    default=current_mode == "channel",
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ScopeModeView = self.view  # type: ignore[assignment]
        mode = self.values[0]
        view.draft.sync_mode = mode

        # If it's an automatic mode that doesn't need channel/category picker, save & sync immediately!
        if mode in ("server", "category_only", "category_channels_only", "category_combined"):
            config = await view.service.set_scope(view.guild.id, mode)
            await interaction.response.edit_message(
                embed=build_status_embed(view.guild, config),
                view=FontSyncPanelView(view.service, view.guild, view.owner_id, config),
            )
            await interaction.followup.send(
                f"Scope updated to **{mode.replace('_', ' ').title()}**. Use the **Apply Changes** button on the main panel to update channels.",
                ephemeral=True,
            )
        else:
            await interaction.response.edit_message(embed=view.build_embed(), view=view)


@dataclass
class ScopeDraft:
    sync_mode: str = "server"
    category_ids: list[int] = field(default_factory=list)
    channel_ids: list[int] = field(default_factory=list)


class ScopeModeView(discord.ui.View):
    def __init__(self, service: FontSyncService, guild: discord.Guild, owner_id: int, config: FontSyncConfig):
        super().__init__(timeout=180)
        self.service = service
        self.guild = guild
        self.owner_id = owner_id
        # Normalize legacy mode "category" to "category_combined"
        sync_mode = config.sync_mode
        if sync_mode == "category":
            sync_mode = "category_combined"
        self.draft = ScopeDraft(
            sync_mode=sync_mode,
            category_ids=list(config.category_ids),
            channel_ids=list(config.channel_ids),
        )
        self.add_item(ScopeModeSelect(sync_mode))

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Choose Sync Scope",
            description="Select where Font Sync should apply.",
            color=0x00AAFF,
        )
        embed.add_field(name="Mode", value=self.draft.sync_mode.replace("_", " ").title(), inline=False)
        if self.draft.sync_mode == "server":
            embed.add_field(name="Selection", value="All channels & categories in the guild", inline=False)
        elif self.draft.sync_mode == "category_only":
            embed.add_field(name="Selection", value="All category headers in the guild", inline=False)
        elif self.draft.sync_mode == "category_channels_only":
            embed.add_field(name="Selection", value="All channels within any category", inline=False)
        elif self.draft.sync_mode in ("category_combined", "category"):
            embed.add_field(name="Selection", value="All category headers and channels inside them", inline=False)
        elif self.draft.sync_mode == "category_individual":
            if self.draft.category_ids:
                selected = [self.guild.get_channel(cid) for cid in self.draft.category_ids]
                names = [c.name for c in selected if isinstance(c, discord.CategoryChannel)]
                embed.add_field(name="Categories", value=", ".join(names) if names else "None", inline=False)
            else:
                embed.add_field(name="Categories", value="None selected (Click Configure Selection below)", inline=False)
        else:
            if self.draft.channel_ids:
                selected = [self.guild.get_channel(cid) for cid in self.draft.channel_ids]
                names = [c.name for c in selected if c is not None and not isinstance(c, discord.CategoryChannel)]
                embed.add_field(name="Channels", value=", ".join(names) if names else "None", inline=False)
            else:
                embed.add_field(name="Channels", value="None selected (Click Configure Selection below)", inline=False)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the invoking administrator can use this panel.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Configure Selection", style=discord.ButtonStyle.primary)
    async def configure_selection(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.draft.sync_mode in ("server", "category_only", "category_channels_only", "category_combined"):
            config = await self.service.set_scope(self.guild.id, self.draft.sync_mode)
            await interaction.response.edit_message(
                embed=build_status_embed(self.guild, config),
                view=FontSyncPanelView(self.service, self.guild, self.owner_id, config),
            )
            await interaction.followup.send(
                f"Scope updated to **{self.draft.sync_mode.replace('_', ' ').title()}**. Use the **Apply Changes** button on the main panel to update channels.",
                ephemeral=True,
            )
            return

        if self.draft.sync_mode == "category_individual":
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="Pick Categories",
                    description="Select the categories you want to keep synchronized.",
                    color=0x00AAFF,
                ),
                view=CategorySelectionView(self.service, self.guild, self.owner_id, self.draft),
            )
            return

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Pick Channels",
                description="Select one or more individual channels to keep synchronized.",
                color=0x00AAFF,
            ),
            view=ChannelSelectionView(self.service, self.guild, self.owner_id, self.draft),
        )

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.get_config(self.guild.id)
        await interaction.response.edit_message(
            embed=build_status_embed(self.guild, config),
            view=FontSyncPanelView(self.service, self.guild, self.owner_id, config),
        )


class CategorySelect(discord.ui.ChannelSelect):
    def __init__(self, values: list[int]):
        super().__init__(
            placeholder="Select categories",
            min_values=0,
            max_values=25,
            channel_types=[discord.ChannelType.category],
        )
        self.default_values = [discord.Object(id=v) for v in values]

    async def callback(self, interaction: discord.Interaction) -> None:
        view: CategorySelectionView = self.view  # type: ignore[assignment]
        view.draft.category_ids = [c.id for c in self.values]
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class CategorySelectionView(discord.ui.View):
    def __init__(self, service: FontSyncService, guild: discord.Guild, owner_id: int, draft: ScopeDraft):
        super().__init__(timeout=180)
        self.service = service
        self.guild = guild
        self.owner_id = owner_id
        self.draft = draft
        self.add_item(CategorySelect(draft.category_ids))

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Pick Categories",
            description="Select one or more categories to keep synchronized.",
            color=0x00AAFF,
        )
        names = []
        for cid in self.draft.category_ids:
            cat = self.guild.get_channel(cid)
            if isinstance(cat, discord.CategoryChannel):
                names.append(cat.name)
        embed.add_field(name="Selected Categories", value=", ".join(names) if names else "None", inline=False)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the invoking administrator can use this panel.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Save Categories", style=discord.ButtonStyle.primary)
    async def save_categories(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.set_scope(self.guild.id, "category_individual", category_ids=self.draft.category_ids)
        await interaction.response.edit_message(
            embed=build_status_embed(self.guild, config),
            view=FontSyncPanelView(self.service, self.guild, self.owner_id, config),
        )
        await interaction.followup.send("Selected categories saved! Use the **Apply Changes** button on the main panel to update channels.", ephemeral=True)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.get_config(self.guild.id)
        view = ScopeModeView(self.service, self.guild, self.owner_id, config)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class ChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, values: list[int]):
        super().__init__(
            placeholder="Select channels",
            min_values=0,
            max_values=25,
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.voice,
                discord.ChannelType.news,
                discord.ChannelType.stage_voice,
                discord.ChannelType.forum,
            ],
        )
        self.default_values = [discord.Object(id=v) for v in values]

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ChannelSelectionView = self.view  # type: ignore[assignment]
        view.draft.channel_ids = [c.id for c in self.values]
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class ChannelSelectionView(discord.ui.View):
    def __init__(self, service: FontSyncService, guild: discord.Guild, owner_id: int, draft: ScopeDraft):
        super().__init__(timeout=180)
        self.service = service
        self.guild = guild
        self.owner_id = owner_id
        self.draft = draft
        self.add_item(ChannelSelect(draft.channel_ids))

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Pick Channels",
            description="Select one or more channels to keep synchronized.",
            color=0x00AAFF,
        )
        names = []
        for cid in self.draft.channel_ids:
            ch = self.guild.get_channel(cid)
            if ch is not None and not isinstance(ch, discord.CategoryChannel):
                names.append(ch.name)
        embed.add_field(name="Selected Channels", value=", ".join(names) if names else "None", inline=False)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the invoking administrator can use this panel.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Save Channels", style=discord.ButtonStyle.primary)
    async def save_channels(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.set_scope(self.guild.id, "channel", channel_ids=self.draft.channel_ids)
        await interaction.response.edit_message(
            embed=build_status_embed(self.guild, config),
            view=FontSyncPanelView(self.service, self.guild, self.owner_id, config),
        )
        await interaction.followup.send("Selected channels saved! Use the **Apply Changes** button on the main panel to update channels.", ephemeral=True)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.get_config(self.guild.id)
        view = ScopeModeView(self.service, self.guild, self.owner_id, config)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class CustomFontModal(discord.ui.Modal, title="Set Custom Font"):
    """
    Discord modal that lets an admin define a custom Unicode font by pasting
    26 styled characters corresponding to a–z (and optionally A–Z).

    Example input for lowercase: 𝒶𝒿𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏
    """

    lowercase = discord.ui.TextInput(
        label="Styled a–z  (paste exactly 26 custom chars)",
        placeholder="𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏",
        min_length=26,
        max_length=200,
        style=discord.TextStyle.short,
    )
    uppercase = discord.ui.TextInput(
        label="Styled A–Z  (optional, 26 chars)",
        placeholder="Leave empty to only map lowercase letters",
        required=False,
        max_length=200,
        style=discord.TextStyle.short,
    )

    def __init__(self, service: FontSyncService, guild: discord.Guild):
        super().__init__()
        self.service = service
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction) -> None:
        lower_raw = self.lowercase.value.replace(" ", "")
        upper_raw = (self.uppercase.value or "").replace(" ", "")

        lower_chars = list(lower_raw)
        if len(lower_chars) < 26:
            await interaction.response.send_message(
                f"❌ Need at least **26** lowercase characters — you provided **{len(lower_chars)}**.\n"
                "Make sure each styled letter is a single Unicode character (no spaces between them).",
                ephemeral=True,
            )
            return

        try:
            config = await self.service.set_custom_font(self.guild.id, lower_raw, upper_raw)
            preview = apply_font("example-channel", "custom", config.custom_font)
            embed = discord.Embed(
                title="✅ Custom Font Saved",
                description=f"**Preview:** {preview}\n\nUse the **Apply Changes** button on the main panel to update channels.",
                color=0x8A2BE2,
            )
            embed.add_field(name="Chars Mapped", value=f"{len(config.custom_font)} letter(s)", inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as exc:
            await interaction.response.send_message(f"❌ Failed to save custom font: {exc}", ephemeral=True)


class FontSyncPanelView(discord.ui.View):
    def __init__(self, service: FontSyncService, guild: discord.Guild, owner_id: int, config: Optional[FontSyncConfig] = None):
        super().__init__(timeout=180)
        self.service = service
        self.guild = guild
        self.owner_id = owner_id

        # Dynamically set styling for enable/disable button
        enabled = config.enabled if config is not None else True
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label in ("Disable", "Enable"):
                if enabled:
                    child.label = "Disable"
                    child.style = discord.ButtonStyle.danger
                else:
                    child.label = "Enable"
                    child.style = discord.ButtonStyle.success

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the invoking administrator can use this panel.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Font", style=discord.ButtonStyle.primary, row=0)
    async def open_font(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.get_config(self.guild.id)
        view = FontStyleView(self.service, self.guild, self.owner_id, config.font_style, config.custom_font)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    @discord.ui.button(label="Scope", style=discord.ButtonStyle.secondary, row=0)
    async def open_scope(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.get_config(self.guild.id)
        view = ScopeModeView(self.service, self.guild, self.owner_id, config)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    @discord.ui.button(label="Custom Font ✨", style=discord.ButtonStyle.secondary, row=0)
    async def open_custom_font(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Open a modal where the admin can paste their own 26-char styled alphabet."""
        modal = CustomFontModal(self.service, self.guild)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Decorate 🎨", style=discord.ButtonStyle.primary, row=1)
    async def open_decoration(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.get_config(self.guild.id)
        view = DecorationStyleView(self.service, self.guild, self.owner_id, config.decoration)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    @discord.ui.button(label="Apply Changes", style=discord.ButtonStyle.success, row=1)
    async def apply_changes(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        queued = await self.service.sync_guild(self.guild, "Font Sync manual apply")
        await interaction.response.send_message(f"✅ Successfully queued {queued} channel/category rename(s) to match your scope, font, and decoration settings.", ephemeral=True)

    @discord.ui.button(label="Disable", style=discord.ButtonStyle.danger, row=1)
    async def toggle_enabled(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.get_config(self.guild.id)
        new_state = not config.enabled
        config = await self.service.set_enabled(self.guild.id, new_state)
        
        view = FontSyncPanelView(self.service, self.guild, self.owner_id, config)
        await interaction.response.edit_message(embed=build_status_embed(self.guild, config), view=view)
        
        if new_state:
            await interaction.followup.send("Font Sync enabled! Use the **Apply Changes** button to update existing channels.", ephemeral=True)
        else:
            await interaction.followup.send("Font Sync disabled.", ephemeral=True)


class DecorationSelect(discord.ui.Select):
    def __init__(self, current_decoration: str):
        options = []
        for name, label in DECORATION_LABELS.items():
            prefix, suffix = DECORATION_STYLES[name]
            sample = f"{prefix}example-channel{suffix}"
            options.append(
                discord.SelectOption(
                    label=label,
                    value=name,
                    description=sample[:100],
                    default=name == current_decoration,
                )
            )
        super().__init__(placeholder="Choose a decoration style", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: DecorationStyleView = self.view  # type: ignore[assignment]
        view.selected_decoration = self.values[0]
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class DecorationStyleView(discord.ui.View):
    def __init__(self, service: FontSyncService, guild: discord.Guild, owner_id: int, current_decoration: str):
        super().__init__(timeout=180)
        self.service = service
        self.guild = guild
        self.owner_id = owner_id
        self.selected_decoration = current_decoration
        self.add_item(DecorationSelect(current_decoration))

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Choose Channel/Category Decoration",
            description="Pick a text framing decoration to make your channels stand out.",
            color=0x8A2BE2,
        )
        embed.add_field(name="Selected", value=DECORATION_LABELS.get(self.selected_decoration, self.selected_decoration), inline=False)
        prefix, suffix = DECORATION_STYLES.get(self.selected_decoration, ("", ""))
        embed.add_field(name="Preview", value=f"{prefix}example-channel{suffix}", inline=False)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the invoking administrator can use this panel.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Save Decoration", style=discord.ButtonStyle.primary)
    async def save_decoration(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.set_decoration(self.guild.id, self.selected_decoration)
        await interaction.response.edit_message(
            embed=build_status_embed(self.guild, config),
            view=FontSyncPanelView(self.service, self.guild, self.owner_id, config),
        )
        await interaction.followup.send("Decoration saved! Use the **Apply Changes** button on the main panel to update channels.", ephemeral=True)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.secondary)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        config = await self.service.get_config(self.guild.id)
        await interaction.response.edit_message(
            embed=build_status_embed(self.guild, config),
            view=FontSyncPanelView(self.service, self.guild, self.owner_id, config),
        )


# ---------------------------------------------------------------------------
# Command wiring
# ---------------------------------------------------------------------------


def setup_font_sync(bot: discord.Client, guild: Optional[discord.abc.Snowflake] = None) -> FontSyncService:
    service = FontSyncService(bot)
    bot.font_sync_service = service  # type: ignore[attr-defined]

    font_sync_group = app_commands.Group(name="font-sync", description="Manage guild font synchronization")

    async def send_panel(interaction: discord.Interaction) -> None:
        config = await service.get_config(interaction.guild.id)  # type: ignore[union-attr]
        view = FontSyncPanelView(service, interaction.guild, interaction.user.id, config)  # type: ignore[arg-type]
        await interaction.response.send_message(
            embed=build_status_embed(interaction.guild, config),  # type: ignore[arg-type]
            view=view,
            ephemeral=True,
        )

    @bot.tree.command(name="font", description="Open the Font Sync settings panel", guild=guild)
    @app_commands.checks.has_permissions(manage_channels=True)
    async def font_root(interaction: discord.Interaction) -> None:
        await send_panel(interaction)

    @font_sync_group.command(name="enable", description="Enable Font Sync and open the settings panel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def enable(interaction: discord.Interaction) -> None:
        config = await service.set_enabled(interaction.guild.id, True)  # type: ignore[union-attr]
        await interaction.response.send_message(
            embed=build_status_embed(interaction.guild, config),  # type: ignore[arg-type]
            view=FontSyncPanelView(service, interaction.guild, interaction.user.id, config),  # type: ignore[arg-type]
            ephemeral=True,
        )

    @font_sync_group.command(name="disable", description="Disable Font Sync")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def disable(interaction: discord.Interaction) -> None:
        config = await service.set_enabled(interaction.guild.id, False)  # type: ignore[union-attr]
        await interaction.response.send_message(
            embed=build_status_embed(interaction.guild, config), ephemeral=True  # type: ignore[arg-type]
        )

    @font_sync_group.command(name="status", description="Show the current Font Sync configuration")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def status(interaction: discord.Interaction) -> None:
        await send_panel(interaction)

    @font_sync_group.command(name="font", description="Choose a font style")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def font(interaction: discord.Interaction) -> None:
        config = await service.get_config(interaction.guild.id)  # type: ignore[union-attr]
        view = FontStyleView(
            service, interaction.guild, interaction.user.id,  # type: ignore[arg-type]
            config.font_style, config.custom_font,
        )
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    @font_sync_group.command(name="scope", description="Choose the sync scope")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def scope(interaction: discord.Interaction) -> None:
        config = await service.get_config(interaction.guild.id)  # type: ignore[union-attr]
        view = ScopeModeView(service, interaction.guild, interaction.user.id, config)  # type: ignore[arg-type]
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    @font_sync_group.command(name="resync", description="Rescan the configured scope and fix channel/category names")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def resync(interaction: discord.Interaction) -> None:
        queued = await service.sync_guild(interaction.guild, "Font Sync manual resync")  # type: ignore[union-attr]
        await interaction.response.send_message(f"Queued {queued} rename(s) for resync.", ephemeral=True)

    @font_sync_group.command(name="decorate", description="Choose a channel/category text framing decoration style")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def decorate(interaction: discord.Interaction) -> None:
        config = await service.get_config(interaction.guild.id)  # type: ignore[union-attr]
        view = DecorationStyleView(service, interaction.guild, interaction.user.id, config.decoration)  # type: ignore[arg-type]
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    bot.tree.add_command(font_sync_group, guild=guild)
    return service