"""
bot_profile.py — Bot Profile Customization per Server.

Commands (/botprofile)
-----------------------
  setnick <nickname>   — Set the bot's nickname in THIS server
  resetnick            — Remove the bot's nickname in THIS server (revert to default)
  setavatar <image>    — Upload an image to change the bot's server-specific avatar
  resetavatar          — Remove the bot's server-specific avatar in THIS server
  view                 — View the bot's current name and avatar in this server

All commands require Manage Server permission.
"""

import io
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands
from gkr_ui import C


class BotProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.approvals_file = Path(__file__).with_name("approved_banner_guilds.json")

    def _load_approved_guilds(self) -> set[str]:
        try:
            if not self.approvals_file.exists():
                return set()
            data = json.loads(self.approvals_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return set()
            return {str(guild_id) for guild_id in data if str(guild_id).isdigit()}
        except (OSError, json.JSONDecodeError):
            # Fail closed if the approval registry cannot be trusted.
            return set()

    def _save_approved_guilds(self, guild_ids: set[str]) -> None:
        self.approvals_file.write_text(
            json.dumps(sorted(guild_ids), indent=2), encoding="utf-8"
        )

    profile_group = app_commands.Group(
        name="botprofile",
        description="Customize the bot's name and profile picture in this server"
    )

    # ── Owner-only guild approval: /bb ─────────────────────────────────────────

    @app_commands.command(name="bb", description="Bot owner: approve or revoke banner access for a guild")
    @app_commands.describe(guild_id="The Discord server ID", action="Approve or revoke banner access")
    @app_commands.choices(action=[
        app_commands.Choice(name="Approve", value="approve"),
        app_commands.Choice(name="Revoke", value="revoke"),
    ])
    async def bb(self, interaction: discord.Interaction, guild_id: str,
                 action: app_commands.Choice[str]):
        owner_id = os.getenv("OWNER_DISCORD_ID", "").strip()
        if not owner_id.isdigit() or interaction.user.id != int(owner_id):
            await interaction.response.send_message(
                "❌ Only the configured bot owner can manage guild approvals.", ephemeral=True
            )
            return

        if not guild_id.isdigit():
            await interaction.response.send_message("❌ Please provide a valid numeric guild ID.", ephemeral=True)
            return

        guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            await interaction.response.send_message(
                "❌ I cannot find that guild. Make sure the bot is a member of it and the ID is correct.",
                ephemeral=True,
            )
            return

        try:
            approved = self._load_approved_guilds()
            if action.value == "approve":
                approved.add(guild_id)
                self._save_approved_guilds(approved)
                message = f"✅ Banner management approved for **{guild.name}** (`{guild_id}`)."
            else:
                approved.discard(guild_id)
                self._save_approved_guilds(approved)
                message = f"✅ Banner management access revoked for **{guild.name}** (`{guild_id}`)."
            await interaction.response.send_message(message, ephemeral=True)
        except OSError:
            await interaction.response.send_message(
                "❌ Could not save the approval registry. No change was confirmed.", ephemeral=True
            )

    # ── Global profile banner command: /botbanner ───────────────────────────────

    @app_commands.command(name="botbanner", description="Change the bot's global profile banner using an image URL")
    @app_commands.describe(url="Direct HTTPS image URL (PNG, JPG, WEBP, or GIF)")
    @app_commands.checks.has_permissions(administrator=True)
    async def botbanner(self, interaction: discord.Interaction, url: str):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Use this command inside an approved server.", ephemeral=True)
            return
        if str(interaction.guild.id) not in self._load_approved_guilds():
            await interaction.response.send_message(
                "❌ This server has not been approved by the bot owner. Use /bb to approve it.",
                ephemeral=True,
            )
            return

        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            await interaction.response.send_message(
                "❌ Provide a valid direct HTTPS image URL. File uploads are not supported.", ephemeral=True
            )
            return
        if not parsed.path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            await interaction.response.send_message(
                "❌ URL must point directly to a PNG, JPG, WEBP, or GIF image.", ephemeral=True
            )
            return

        # Discord's supported bot API does not expose editing the bot account's
        # global profile banner. Do not fake success or use undocumented endpoints.
        await interaction.response.send_message(
            "⚠️ Your server is approved and the URL is valid, but Discord's supported bot API "
            "does not provide a method for changing a bot account's global profile banner. "
            "No changes were made. This is separate from the server-specific avatar command.",
            ephemeral=True,
        )

    # ── /botprofile setnick ────────────────────────────────────────────────────

    @profile_group.command(name="setnick", description="Set the bot's nickname in this server")
    @app_commands.describe(nickname="The new nickname for the bot in this server (max 32 chars)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setnick(self, interaction: discord.Interaction, nickname: str):
        await interaction.response.defer(ephemeral=True)

        if len(nickname) > 32:
            await interaction.followup.send(
                "❌ Nickname must be 32 characters or less.", ephemeral=True
            )
            return

        try:
            await interaction.guild.me.edit(nick=nickname)
            embed = discord.Embed(
                title="✅ Nickname Updated",
                description=f"My nickname in **{interaction.guild.name}** has been set to **{nickname}**.",
                color=C.SUCCESS
            )
            embed.set_footer(text="This only affects this server.")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to change my own nickname here.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed: `{e}`", ephemeral=True)

    # ── /botprofile resetnick ──────────────────────────────────────────────────

    @profile_group.command(name="resetnick", description="Remove the bot's nickname in this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def resetnick(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.guild.me.edit(nick=None)
            embed = discord.Embed(
                title="✅ Nickname Removed",
                description=f"My nickname in **{interaction.guild.name}** has been reset to my default name: **{self.bot.user.name}**.",
                color=C.SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to change my nickname here.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed: `{e}`", ephemeral=True)

    # ── /botprofile setavatar ──────────────────────────────────────────────────

    @profile_group.command(name="setavatar", description="Set the bot's server avatar via file upload or image URL")
    @app_commands.describe(
        image="Upload an image file directly (PNG, JPG, WEBP)",
        url="Or provide a direct image URL (https://...)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setavatar(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment = None,
        url: str = None
    ):
        await interaction.response.defer(ephemeral=True)

        # Must provide at least one source
        if image is None and url is None:
            await interaction.followup.send(
                "❌ Please provide either an **image file** or an **image URL**.\n"
                "Example: `/botprofile setavatar image:<upload>` or `/botprofile setavatar url:https://example.com/avatar.png`",
                ephemeral=True
            )
            return

        # Both provided — prefer file upload
        if image is not None and url is not None:
            await interaction.followup.send(
                "⚠️ You provided both a file and a URL. I'll use the **uploaded file** and ignore the URL.",
                ephemeral=True
            )

        try:
            # ── Method 1: File upload ──────────────────────────────────────
            if image is not None:
                if not image.content_type or not image.content_type.startswith("image/"):
                    await interaction.followup.send(
                        "❌ The uploaded file is not a valid image (PNG, JPG, WEBP).", ephemeral=True
                    )
                    return

                if image.size > 10 * 1024 * 1024:
                    await interaction.followup.send(
                        "❌ Image is too large. Please use an image under 10 MB.", ephemeral=True
                    )
                    return

                image_bytes = await image.read()
                preview_url = image.url
                source_label = "📎 Uploaded File"

            # ── Method 2: URL ──────────────────────────────────────────────
            else:
                import aiohttp
                # Basic URL validation
                if not (url.startswith("http://") or url.startswith("https://")):
                    await interaction.followup.send(
                        "❌ Invalid URL. It must start with `http://` or `https://`.", ephemeral=True
                    )
                    return

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            await interaction.followup.send(
                                f"❌ Failed to download image from URL (HTTP {resp.status}). "
                                "Make sure the URL is a **direct link** to an image file.",
                                ephemeral=True
                            )
                            return

                        content_type = resp.content_type or ""
                        if not content_type.startswith("image/"):
                            await interaction.followup.send(
                                "❌ The URL does not point to a valid image. "
                                "Make sure the URL ends in `.png`, `.jpg`, or `.webp`.",
                                ephemeral=True
                            )
                            return

                        image_bytes = await resp.read()

                if len(image_bytes) > 10 * 1024 * 1024:
                    await interaction.followup.send(
                        "❌ Image from URL is too large (over 10 MB).", ephemeral=True
                    )
                    return

                preview_url = url
                source_label = "🔗 Image URL"

            # ── Apply the avatar ───────────────────────────────────────────
            await interaction.guild.me.edit(avatar=image_bytes)

            embed = discord.Embed(
                title="✅ Server Avatar Updated",
                description=f"My profile picture in **{interaction.guild.name}** has been updated!",
                color=C.SUCCESS
            )
            embed.add_field(name="Source", value=source_label, inline=True)
            embed.set_image(url=preview_url)
            embed.set_footer(text="This only affects this server.")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to update my avatar in this server.", ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Discord rejected the avatar: `{e}`", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Unexpected error: `{e}`", ephemeral=True)

    # ── /botprofile resetavatar ────────────────────────────────────────────────

    @profile_group.command(name="resetavatar", description="Remove the bot's server avatar in this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def resetavatar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.guild.me.edit(avatar=None)
            embed = discord.Embed(
                title="✅ Server Avatar Removed",
                description=f"My server-specific avatar in **{interaction.guild.name}** has been removed. I'll now show my global profile picture.",
                color=C.SUCCESS
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to update my avatar here.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Failed: `{e}`", ephemeral=True)

    # ── /botprofile view ───────────────────────────────────────────────────────

    @profile_group.command(name="view", description="View the bot's current profile in this server")
    async def view(self, interaction: discord.Interaction):
        me = interaction.guild.me
        nick = me.nick or f"*(using default: {self.bot.user.name})*"

        # Guild avatar if set, otherwise fall back to global avatar
        avatar_url = me.guild_avatar.url if me.guild_avatar else (self.bot.user.avatar.url if self.bot.user.avatar else self.bot.user.default_avatar.url)

        embed = discord.Embed(
            title=f"🤖 Bot Profile — {interaction.guild.name}",
            color=C.INFO
        )
        embed.add_field(name="Default Name", value=f"`{self.bot.user.name}`", inline=True)
        embed.add_field(name="Server Nickname", value=nick, inline=True)
        embed.add_field(
            name="Avatar Type",
            value="🖼️ Server-Specific" if me.guild_avatar else "🌐 Global",
            inline=True
        )
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text="Use /botprofile setnick or /botprofile setavatar to customize")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Error handler ──────────────────────────────────────────────────────────

    @setnick.error
    @resetnick.error
    @setavatar.error
    @resetavatar.error
    @botbanner.error
    async def profile_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need the **Administrator** permission to use /botbanner, or the required server-management permission for other profile commands.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(BotProfileCog(bot))
    print("🤖 BotProfile cog loaded!")
