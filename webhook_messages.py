"""
webhook_messages.py — Webhook Embed Message Builder for GKR Bot.

Allows admins to post customizable embeds by pasting text into a modal.
Supports attaching an image file directly via the slash command, or providing an image URL.
Uses Webhooks to allow custom sender names and avatars.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class WebhookEmbedModal(discord.ui.Modal, title="🛠️ Build Webhook Embed"):
    embed_title = discord.ui.TextInput(
        label="Embed Title",
        style=discord.TextStyle.short,
        placeholder="Enter the title for your embed...",
        required=True,
        max_length=256,
    )
    embed_content = discord.ui.TextInput(
        label="Message Content (Paste text here)",
        style=discord.TextStyle.paragraph,
        placeholder="Paste your text here. Newlines and spacing are preserved.",
        required=True,
        max_length=4000,
    )
    hex_color = discord.ui.TextInput(
        label="Embed Color (Hex)",
        style=discord.TextStyle.short,
        default="#8A2BE2",
        placeholder="#8A2BE2",
        required=False,
        max_length=10,
    )

    def __init__(
        self,
        target_channel: discord.TextChannel,
        image_url: str | None,
        custom_name: str | None,
        custom_avatar: str | None,
    ):
        super().__init__()
        self.target_channel = target_channel
        self.image_url = image_url
        self.custom_name = custom_name
        self.custom_avatar = custom_avatar

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        
        # 1. Parse Color
        color_str = str(self.hex_color).strip().replace("#", "")
        try:
            color_int = int(color_str, 16) if color_str else 0x8A2BE2
        except ValueError:
            color_int = 0x8A2BE2

        # 2. Build Embed
        embed = discord.Embed(
            title=str(self.embed_title),
            description=str(self.embed_content),
            color=color_int,
        )

        if self.image_url:
            embed.set_image(url=self.image_url)

        # 3. Send via Webhook OR normal bot
        try:
            if self.custom_name or self.custom_avatar:
                # Webhook route
                webhooks = await self.target_channel.webhooks()
                webhook = discord.utils.get(webhooks, name="GKR Webhook Sender")
                if not webhook:
                    webhook = await self.target_channel.create_webhook(name="GKR Webhook Sender", reason="For webhook_embed command")
                
                await webhook.send(
                    embed=embed,
                    username=self.custom_name or interaction.guild.me.display_name,
                    avatar_url=self.custom_avatar or interaction.guild.me.display_avatar.url,
                )
            else:
                # Normal bot route
                await self.target_channel.send(embed=embed)

            await interaction.followup.send(f"✅ Successfully posted the webhook embed to {self.target_channel.mention}!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I do not have permission to send messages or manage webhooks in that channel.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred while sending the message: {e}", ephemeral=True)


class WebhookMessagesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="webhook_embed", description="Create an embed via Webhook. Allows file uploads for images and pasting text.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        channel="Channel to post the message in",
        image_file="Upload an image/GIF file to attach to the embed",
        image_url="OR provide a direct URL to an image/GIF",
        custom_name="Webhook feature: Custom username for the message sender",
        custom_avatar="Webhook feature: Custom profile picture URL for the sender",
    )
    async def webhook_embed(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        image_file: discord.Attachment | None = None,
        image_url: str | None = None,
        custom_name: str | None = None,
        custom_avatar: str | None = None,
    ) -> None:
        
        # Determine final image URL
        final_image_url = None
        if image_file:
            if not image_file.content_type or not image_file.content_type.startswith("image/"):
                await interaction.response.send_message("❌ The uploaded file must be an image or GIF.", ephemeral=True)
                return
            # Discord attachments from interactions are hosted on Discord's CDN temporarily or permanently.
            # We can use the attachment's URL directly for the embed image.
            final_image_url = image_file.url
        elif image_url:
            final_image_url = image_url

        # Send the modal
        modal = WebhookEmbedModal(
            target_channel=channel,
            image_url=final_image_url,
            custom_name=custom_name,
            custom_avatar=custom_avatar
        )
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WebhookMessagesCog(bot))
    print("🕸️ Webhook Messages module loaded!")
