"""
gkr_ui.py — GKR Bot Central UI Design System & Component Library

Single source of truth for all visual presentation across GKR Bot.
Implements a unified, modern SaaS aesthetic for Discord:
  • Clean visual hierarchy (Title > Subject > Actor > Details)
  • Zero database/internal table dumps
  • Semantic color tokens
  • Unified audit-log renderer
  • Two-layer administrative debug views
  • Polished pagination & confirmation workflows
"""

from __future__ import annotations

import datetime
from typing import Optional, Any, Callable, Sequence, Union
import discord
from bot_config import BOT_NAME


# ---------------------------------------------------------------------------
# Color Palette — Semantic Tokens
# ---------------------------------------------------------------------------

class GKRColors:
    BRAND       = 0x5865F2   # Discord Blurple  — primary actions, navigation
    SUCCESS     = 0x57F287   # Discord Emerald  — confirmations, positive feedback
    WARNING     = 0xFEE75C   # Discord Amber    — cautions, warnings, active timeouts
    DANGER      = 0xED4245   # Discord Ruby     — errors, destructive actions, bans
    GOLD        = 0xF1C40F   # Warm Gold        — economy, rewards, achievements
    NEUTRAL     = 0x2B2D31   # Discord Dark     — settings, inactive panels, secondary
    PURPLE      = 0x9B59B6   # Rich Purple      — profiles, role events, levels
    CYAN        = 0x1ABC9C   # Fresh Cyan       — voice events, threads
    MUTED       = 0x4F545C   # Slate Gray       — disabled / passive info

C = GKRColors  # Short alias


# ---------------------------------------------------------------------------
# Time & Formatting Helpers
# ---------------------------------------------------------------------------

def fmt_ts(dt: Optional[datetime.datetime] = None, style: str = "t") -> str:
    """Format a datetime into a Discord timestamp string (default: 12-hr time 't')."""
    if dt is None:
        dt = discord.utils.utcnow()
    return f"<t:{int(dt.timestamp())}:{style}>"


def fmt_rel(dt: datetime.datetime) -> str:
    """Format a datetime into a relative Discord timestamp string (e.g. '2 minutes ago')."""
    return f"<t:{int(dt.timestamp())}:R>"


def fmt_duration(total_seconds: float) -> str:
    """Convert seconds to a human-readable duration string."""
    total_seconds = int(total_seconds)
    if total_seconds < 60:
        return f"{total_seconds}s"
    mins, secs = divmod(total_seconds, 60)
    if mins < 60:
        return f"{mins}m {secs}s" if secs else f"{mins}m"
    hours, mins = divmod(mins, 60)
    if hours < 24:
        return f"{hours}h {mins}m" if mins else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"


def fmt_coins(n: int) -> str:
    """Format coin amounts with thousands commas."""
    return f"🪙 {n:,}"


def fmt_number(n: int) -> str:
    """Short number format: 1500 → 1.5K, 1000000 → 1M."""
    if abs(n) >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def ordinal(n: int) -> str:
    """Return ordinal string: 1 → 1st, 2 → 2nd, etc."""
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10 if n % 100 not in (11, 12, 13) else 0, "th")
    return f"{n}{suffix}"


# ---------------------------------------------------------------------------
# Standard Embed Feedback Factories
# ---------------------------------------------------------------------------

def embed_success(title: str, description: Optional[str] = None) -> discord.Embed:
    """Clean positive confirmation embed."""
    e = discord.Embed(title=f"✅  {title}", color=C.SUCCESS)
    if description:
        e.description = description
    return e


def embed_error(description: str, *, title: str = "Unable to complete action") -> discord.Embed:
    """Compact, user-friendly error embed."""
    e = discord.Embed(
        title=f"❌  {title}",
        description=description,
        color=C.DANGER
    )
    return e


def embed_warning(description: str, *, title: str = "Attention") -> discord.Embed:
    """Clean warning/caution embed."""
    e = discord.Embed(
        title=f"⚠️  {title}",
        description=description,
        color=C.WARNING
    )
    return e


def embed_info(title: str, description: Optional[str] = None, *, color: int = C.BRAND) -> discord.Embed:
    """Neutral informational embed."""
    e = discord.Embed(title=title, color=color)
    if description:
        e.description = description
    return e


def embed_permission_error(permission_name: str) -> discord.Embed:
    """Standardized permission required embed."""
    return embed_error(
        f"You need the **{permission_name}** permission to use this command.",
        title="Permission required"
    )


def embed_loading(title: str = "Processing...", description: Optional[str] = None) -> discord.Embed:
    """State transition / loading embed."""
    e = discord.Embed(
        title=f"⏳  {title}",
        color=C.NEUTRAL
    )
    if description:
        e.description = description
    return e


def embed_action(
    title: str,
    description: Optional[str] = None,
    *,
    color: int = C.BRAND,
    emoji: Optional[str] = None,
) -> discord.Embed:
    """
    Clean action/event embed — used for triggered events, giveaway results,
    community actions, security alerts, etc.

    Parameters
    ----------
    title:       Short event name (e.g. 'Giveaway ended', 'Image flagged').
    description: Optional detail body.
    color:       Semantic color token (default: BRAND).
    emoji:       Optional leading emoji prepended to the title.
    """
    display_title = f"{emoji}  {title}" if emoji else title
    e = discord.Embed(title=display_title, color=color)
    if description:
        e.description = description
    e.timestamp = discord.utils.utcnow()
    return e


def medal(rank: int) -> str:
    """
    Return a medal emoji for the given 0-based leaderboard rank.
    Rank 0 → 🥇, 1 → 🥈, 2 → 🥉, 3+ → plain rank number.
    """
    return {0: "🥇", 1: "🥈", 2: "🥉"}.get(rank, f"`#{rank + 1}`")


def paginate_leaderboard(
    title: str,
    rows: Sequence[Any],
    fmt_row: Callable[[int, Any], str],
    *,
    per_page: int = 10,
    color: int = C.GOLD,
    footer: Optional[str] = None,
) -> list[discord.Embed]:
    if footer is None:
        footer = f"{BOT_NAME} Leaderboard"
    """
    Build a list of leaderboard embed pages from a sequence of rows.

    Parameters
    ----------
    title:    Embed title shown on every page.
    rows:     Ordered sequence of row objects (list/tuple/etc.).
    fmt_row:  Callable(rank: int, row: Any) → str — formats a single entry line.
              ``rank`` is the 0-based global index across ALL rows.
    per_page: Rows per embed page (default 10).
    color:    Embed colour (default GOLD).
    footer:   Footer text prefix; page info is appended automatically.

    Returns a non-empty list of discord.Embed objects. If ``rows`` is empty,
    returns a single embed saying there are no entries yet.
    """
    if not rows:
        e = discord.Embed(title=title, description="*No entries yet.*", color=color)
        e.set_footer(text=footer)
        return [e]

    pages: list[discord.Embed] = []
    chunks = [rows[i : i + per_page] for i in range(0, len(rows), per_page)]
    total_pages = len(chunks)

    for page_idx, chunk in enumerate(chunks):
        lines = [fmt_row(page_idx * per_page + i, row) for i, row in enumerate(chunk)]
        e = discord.Embed(
            title=title,
            description="\n".join(lines),
            color=color,
        )
        e.set_footer(text=f"{footer} · Page {page_idx + 1}/{total_pages}")
        pages.append(e)

    return pages



# ---------------------------------------------------------------------------
# Reusable Audit Log Renderer
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Reusable Audit Log Renderer
# ---------------------------------------------------------------------------

def create_audit_embed(
    title: str,
    subject: str,
    *,
    action_desc: Optional[str] = None,
    actor: Optional[Union[discord.Member, discord.User, str]] = None,
    actor_label: Optional[str] = None,
    subject_header: Optional[str] = None,
    details: Optional[Sequence[str]] = None,
    changes: Optional[Sequence[Tuple[str, str, str]]] = None,
    color: int = C.BRAND,
    thumbnail_url: Optional[str] = None,
    footer_text: Optional[str] = None,
    timestamp: Optional[datetime.datetime] = None,
) -> discord.Embed:
    """
    Standardized, high-hierarchy audit log card matching Discord-native aesthetics:
      • Clean title with emoji (e.g. '⚙️ Channel Updated', '📁 Channel Created')
      • Summary subtitle (e.g. 'Role was removed from @User.')
      • Structured fields (Member/Channel, Moderator, Details, Changes)
      • Clean emoji indicators on all field values
      • Zero raw numerical user/channel IDs
      • Standardized footer and timestamp
    """
    ts = timestamp or discord.utils.utcnow()
    lower_title = title.lower()

    # ── 1. Determine subject field header ─────────────────────────────────────
    if not subject_header:
        if "member_role" in lower_title or "role added" in lower_title or "role removed" in lower_title or "roles updated" in lower_title:
            subject_header = "👤  Member"
        elif "member" in lower_title or "user" in lower_title or "kick" in lower_title or "ban" in lower_title or "timeout" in lower_title or "nickname" in lower_title:
            subject_header = "👤  Member"
        elif "channel" in lower_title:
            subject_header = "📁  Channel"
        elif "role" in lower_title:
            subject_header = "🎭  Role"
        elif "message" in lower_title:
            subject_header = "💬  Message"
        elif "thread" in lower_title:
            subject_header = "🧵  Thread"
        elif "voice" in lower_title:
            subject_header = "🔊  Voice"
        elif "invite" in lower_title:
            subject_header = "🔗  Invite"
        elif "emoji" in lower_title or "sticker" in lower_title:
            subject_header = "🏷️  Item"
        elif "event" in lower_title or "stage" in lower_title:
            subject_header = "📅  Event"
        elif "server" in lower_title:
            subject_header = "⚙️  Server"
        else:
            subject_header = "📌  Target"

    # ── 2. Determine actor label ──────────────────────────────────────────────
    if not actor_label:
        if "role added" in lower_title:
            actor_label = "Added By"
        elif "role removed" in lower_title:
            actor_label = "Removed By"
        elif "ban" in lower_title:
            actor_label = "Banned By"
        elif "unban" in lower_title:
            actor_label = "Unbanned By"
        elif "kick" in lower_title:
            actor_label = "Kicked By"
        elif "timeout" in lower_title or "mute" in lower_title:
            actor_label = "Moderator"
        elif "creat" in lower_title or "join" in lower_title:
            actor_label = "Created By"
        elif "delet" in lower_title:
            actor_label = "Deleted By"
        elif "updat" in lower_title or "edit" in lower_title or "chang" in lower_title:
            actor_label = "Updated By"
        else:
            actor_label = "Action By"

    # ── 3. Build description summary sentence ─────────────────────────────────
    desc_lines = []
    if action_desc:
        desc_lines.append(action_desc)
    else:
        if "role added" in lower_title:
            desc_lines.append(f"A role was added to **{subject}**.")
        elif "role removed" in lower_title:
            desc_lines.append(f"A role was removed from **{subject}**.")
        elif "roles updated" in lower_title:
            desc_lines.append(f"Roles were updated for **{subject}**.")
        elif "role created" in lower_title:
            desc_lines.append(f"Role **{subject}** was created.")
        elif "role deleted" in lower_title:
            desc_lines.append(f"Role **{subject}** was deleted.")
        elif "creat" in lower_title:
            desc_lines.append(f"{subject_header.split()[-1]} **{subject}** was created.")
        elif "delet" in lower_title:
            desc_lines.append(f"{subject_header.split()[-1]} **{subject}** was deleted.")
        elif "updat" in lower_title or "edit" in lower_title or "chang" in lower_title:
            desc_lines.append(f"{subject_header.split()[-1]} **{subject}** was modified.")

    embed = discord.Embed(
        title=title,
        description="\n".join(desc_lines) if desc_lines else None,
        color=color,
        timestamp=ts,
    )

    # Field 1: Subject (Channel, Member, Role, etc.)
    if subject:
        embed.add_field(name=subject_header, value=subject, inline=True)

    # Field 2: Actor (Updated By, Created By, etc.) — clean mention without raw IDs
    if actor:
        actor_mention = actor.mention if hasattr(actor, "mention") else str(actor)
        embed.add_field(name=f"👤  {actor_label}", value=actor_mention, inline=True)

    # Field 3+: Other metadata details (e.g. Type, Reason, Channel, etc.)
    if details:
        for item in details:
            if not item:
                continue
            if ":" in item and not item.startswith(">") and not item.startswith("http"):
                k, v = item.split(":", 1)
                k = k.strip()
                v = v.strip()
                emoji_prefix = "📋"
                if "type" in k.lower():
                    emoji_prefix = "📋"
                elif "reason" in k.lower():
                    emoji_prefix = "📝"
                elif "channel" in k.lower():
                    emoji_prefix = "📁"
                elif "role" in k.lower():
                    emoji_prefix = "🎭"
                elif "account" in k.lower() or "age" in k.lower():
                    emoji_prefix = "🕒"
                elif "expires" in k.lower() or "time" in k.lower():
                    emoji_prefix = "⏳"
                embed.add_field(name=f"{emoji_prefix}  {k}", value=v or "—", inline=True)
            else:
                embed.add_field(name="ℹ️  Information", value=item, inline=False)

    # Changes field
    if changes:
        diff_lines = []
        for name, before_val, after_val in changes:
            emoji = "📝"
            if "name" in name.lower():
                emoji = "📝"
            elif "color" in name.lower():
                emoji = "🎨"
            elif "topic" in name.lower() or "content" in name.lower():
                emoji = "💬"
            elif "slowmode" in name.lower() or "limit" in name.lower():
                emoji = "⏱️"
            elif "lock" in name.lower() or "arch" in name.lower() or "hoist" in name.lower():
                emoji = "🔒"
            diff_lines.append(f"{emoji}  **{name}**: `{before_val}` ➔ `{after_val}`")
        if diff_lines:
            embed.add_field(name="🔄  Changes", value="\n".join(diff_lines), inline=False)

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    footer_str = f"{BOT_NAME} Bot • {footer_text}" if footer_text else f"{BOT_NAME} Server Logs"
    embed.set_footer(text=footer_str)

    return embed


# ---------------------------------------------------------------------------
# Reusable Moderation Action Embed
# ---------------------------------------------------------------------------

def create_moderation_embed(
    action_title: str,
    user: Union[discord.Member, discord.User],
    moderator: Union[discord.Member, discord.User],
    *,
    reason: Optional[str] = None,
    duration_str: Optional[str] = None,
    expires_at: Optional[datetime.datetime] = None,
    color: int = C.DANGER,
    extra_info: Optional[str] = None,
) -> discord.Embed:
    """Clean moderation infraction embed."""
    lines = [
        f"**User:** {user.mention} (`{user}`)",
        f"**Moderator:** {moderator.mention}",
    ]
    if duration_str:
        lines.append(f"**Duration:** `{duration_str}`")
    if expires_at:
        lines.append(f"**Expires:** {fmt_rel(expires_at)}")
    if extra_info:
        lines.append(extra_info)

    lines.append(f"**Reason:**\n> {reason or 'No reason provided'}")

    embed = discord.Embed(
        title=action_title,
        description="\n".join(lines),
        color=color,
        timestamp=discord.utils.utcnow()
    )
    if hasattr(user, "display_avatar") and user.display_avatar:
        embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Moderation Log")
    return embed


# ---------------------------------------------------------------------------
# Reusable Two-Layer Admin Debug View
# ---------------------------------------------------------------------------

class AdminDebugView(discord.ui.View):
    """
    Presents a clean, user-facing error message with a 'Technical details'
    button that only administrators / authorized users can inspect.
    """
    def __init__(self, technical_details: str, *, admin_role_ids: Optional[Sequence[int]] = None, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.technical_details = technical_details
        self.admin_role_ids = set(admin_role_ids or [])

    @discord.ui.button(label="Technical details", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def show_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
        if not is_admin and interaction.guild and hasattr(interaction.user, "roles"):
            user_role_ids = {r.id for r in interaction.user.roles}
            if self.admin_role_ids and user_role_ids.intersection(self.admin_role_ids):
                is_admin = True

        if not is_admin:
            await interaction.response.send_message(
                embed=embed_error("Only server administrators can view technical details.", title="Access restricted"),
                ephemeral=True
            )
            return

        debug_embed = discord.Embed(
            title="⚙️  Technical Diagnostics",
            description=f"```yaml\n{self.technical_details[:3800]}\n```",
            color=C.NEUTRAL
        )
        debug_embed.set_footer(text="Internal Diagnostic Layer · Administrators Only")
        await interaction.response.send_message(embed=debug_embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Standard Interactive Components
# ---------------------------------------------------------------------------

class Paginator(discord.ui.View):
    """
    Universal embed paginator with author validation and disabled state handling.
    """
    def __init__(self, pages: Sequence[discord.Embed], author_id: int, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.pages = list(pages)
        self.author_id = author_id
        self.current = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = (self.current == 0)
        self.next_btn.disabled = (self.current >= len(self.pages) - 1)
        self.page_label.label = f"{self.current + 1} / {max(1, len(self.pages))}"

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=embed_error("This menu belongs to someone else.", title="Interaction restricted"),
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, custom_id="pag_prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction):
            return
        self.current = max(0, self.current - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="pag_label")
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="pag_next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction):
            return
        self.current = min(len(self.pages) - 1, self.current + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class ConfirmView(discord.ui.View):
    """
    Standard deliberate confirmation view.
    """
    def __init__(
        self,
        author_id: int,
        on_confirm: Callable[[discord.Interaction], Any],
        on_cancel: Optional[Callable[[discord.Interaction], Any]] = None,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        confirm_style: discord.ButtonStyle = discord.ButtonStyle.danger,
        timeout: int = 60
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.confirm_btn.label = confirm_label
        self.confirm_btn.style = confirm_style
        self.cancel_btn.label = cancel_label

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=embed_error("Only the command author can confirm this action.", title="Unauthorized"),
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, custom_id="conf_confirm")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction):
            return
        self.stop()
        await self.on_confirm(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="conf_cancel")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check(interaction):
            return
        self.stop()
        if self.on_cancel:
            await self.on_cancel(interaction)
        else:
            await interaction.response.edit_message(
                embed=embed_info("Cancelled", "The action was cancelled."),
                view=None
            )
