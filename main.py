import sys
import subprocess
import traceback
import os
import shutil

# Self-healing dependency check (e.g. for PyNaCl, yt-dlp, spotipy)
required_packages = {
    "yt_dlp": "yt-dlp",
    "spotipy": "spotipy",
    "ytnoti": "ytnoti"
}
for check_module, pip_name in required_packages.items():
    try:
        __import__(check_module)
    except ImportError:
        print(f"⚙️ Auto-installing missing dependency: {pip_name}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
            print(f"✅ Successfully installed {pip_name}!")
        except Exception as e:
            print(f"❌ Failed to auto-install {pip_name}: {e}")

# Force-upgrade yt-dlp on startup to bypass YouTube datacenter blocks
print("⚙️ Force-upgrading yt-dlp to latest version for anti-bot patches...")
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"], stdout=subprocess.DEVNULL)
    print("✅ yt-dlp is up to date!")
except Exception as e:
    print(f"⚠️ Failed to upgrade yt-dlp: {e}")

# Check PyNaCl specifically since it requires voice extras
try:
    import nacl.secret
    import nacl.signing
except ImportError:
    print("⚙️ PyNaCl voice components are missing or failed to import. Auto-installing discord.py[voice]...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "discord.py[voice]"])
        import nacl.secret
        import nacl.signing
        print("✅ Successfully installed and verified PyNaCl submodules!")
    except Exception as e:
        print(f"❌ Failed to resolve PyNaCl voice components: {e}")

# Detailed voice diagnostic checks
print("=== GKR Voice Diagnostics ===")
print(f"Python version: {sys.version}")
print(f"Platform: {sys.platform}")

try:
    import ctypes
    print("✅ Standard library 'ctypes' imported successfully!")
    try:
        import ctypes.util
        print("✅ 'ctypes.util' imported successfully!")
        opus_path = ctypes.util.find_library('opus')
        print(f"ℹ️ libopus library search path: {opus_path}")
    except Exception as e:
        print(f"⚠️ ctypes.util check failed: {e}")
except ImportError as e:
    print(f"❌ ctypes import failed! This is why voice fails: {e}")
    traceback.print_exc()

try:
    import nacl
    print("✅ PyNaCl ('nacl') imported successfully!")
    try:
        import nacl.secret
        import nacl.signing
        print("✅ nacl.secret and nacl.signing imported successfully!")
    except Exception as e:
        print(f"❌ PyNaCl submodules import failed! This is why voice fails: {e}")
        traceback.print_exc()
except ImportError as e:
    print(f"❌ PyNaCl import failed! This is why voice fails: {e}")
    traceback.print_exc()
print("=============================")

import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import datetime
import asyncio
import random
from discord.app_commands import Choice
from dotenv import load_dotenv
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
# import wavelink  # Music disabled
import json
import io

# Force standard streams to use UTF-8 encoding on Windows to prevent emoji printing crashes
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Load environment variables early so modules can access them
load_dotenv()

# All modules are loaded as discord.py extensions (Cogs) in setup_hook below.
# No direct imports needed — load_extension handles everything.

# Run environment validation checks first
def validate_environment():
    required_vars = {
        'DISCORD_TOKEN': 'Bot token from Discord Developer Portal',
        'DISCORD_APPLICATION_ID': 'Bot Application ID from Discord Developer Portal',
        'DISCORD_GUILD_ID': 'The target Discord Server ID',
        'BOT_ROLE_ID': 'The role ID used to enforce the "GKR" nickname',
        'MEMBER_ROLE_ID': 'The role ID for member count tracking (MEMBER_ROLE_ID or memeber_role_id)',
        'REACTION_CHANNEL_ID': 'The channel ID where reaction roles are setup'
    }
    
    missing = []
    invalid = []
    
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        missing.append('DISCORD_TOKEN')
        
    app_id = os.getenv('DISCORD_APPLICATION_ID')
    if not app_id:
        missing.append('DISCORD_APPLICATION_ID')
    else:
        try:
            int(app_id)
        except ValueError:
            invalid.append(('DISCORD_APPLICATION_ID', app_id, 'Must be an integer'))
            
    guild_id = os.getenv('DISCORD_GUILD_ID')
    if not guild_id:
        missing.append('DISCORD_GUILD_ID')
    else:
        try:
            int(guild_id)
        except ValueError:
            invalid.append(('DISCORD_GUILD_ID', guild_id, 'Must be an integer'))
            
    bot_role = os.getenv('BOT_ROLE_ID')
    if not bot_role:
        missing.append('BOT_ROLE_ID')
    else:
        try:
            int(bot_role)
        except ValueError:
            invalid.append(('BOT_ROLE_ID', bot_role, 'Must be an integer'))
            
    member_role = os.getenv('MEMBER_ROLE_ID') or os.getenv('memeber_role_id')
    if not member_role:
        missing.append('MEMBER_ROLE_ID')
    else:
        try:
            int(member_role)
        except ValueError:
            invalid.append(('MEMBER_ROLE_ID', member_role, 'Must be an integer'))
            
    reaction_channel = os.getenv('REACTION_CHANNEL_ID')
    if not reaction_channel:
        missing.append('REACTION_CHANNEL_ID')
    else:
        try:
            int(reaction_channel)
        except ValueError:
            invalid.append(('REACTION_CHANNEL_ID', reaction_channel, 'Must be an integer'))

    if missing or invalid:
        print("\n" + "=" * 50)
        print("❌ CONFIGURATION ERROR: Invalid or missing environment variables!")
        print("=" * 50)
        if missing:
            print("\n🔍 Missing Variables:")
            for var in missing:
                print(f"  - {var}: {required_vars.get(var)}")
        if invalid:
            print("\n⚠️ Invalid Formats (Expected Numeric IDs):")
            for var, val, reason in invalid:
                print(f"  - {var} = '{val}' ({reason})")
        print("\n💡 Please check your .env file and ensure all values are correct.")
        print("=" * 50 + "\n")
        return False
    return True

if not validate_environment():
    import sys
    sys.exit(1)

# Bot configuration
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID'))
APPLICATION_ID = int(os.getenv('DISCORD_APPLICATION_ID', '0') or 0)
GUILD_OBJECT = discord.Object(id=GUILD_ID)
BOT_ROLE_ID = int(os.getenv('BOT_ROLE_ID'))  # Role for bot nickname management
MEMBER_ROLE_ID = int(os.getenv('MEMBER_ROLE_ID') or os.getenv('memeber_role_id'))  # Role for member count watching
PORT = int(os.getenv('PORT', 8080)) 

# ── Music / Wavelink disabled ──
# Uncomment below to re-enable music once a working Lavalink node is found
# LAVALINK_URI      = os.getenv('LAVALINK_URI', '')
# LAVALINK_PASSWORD = os.getenv('LAVALINK_PASSWORD', '')
# _LAVALINK_FALLBACKS = [ ... ]
# async def _get_lavalink_nodes(): ...


# Reaction roles configuration
REACTION_CHANNEL_ID = int(os.getenv('REACTION_CHANNEL_ID', '0'))  # Default to 0 if not set
REACTION_MESSAGE_ID = None  # Will be set when message is created

# Emoji to role mapping
EMOJI_ROLE_MAP = {
    # Format for custom emoji is either:
    # "<:emoji_name:emoji_id>" or "<a:emoji_name:emoji_id>" for animated emojis
    "<:valo:1416294130648088718>": int(os.getenv('VALORANT_ROLE_ID', '0')),    # Valorant
    "<:gta5:1416294123987669094>": int(os.getenv('GTA_ROLE_ID', '0')),         # GTA V
    "<:other:1416294127972384818>": int(os.getenv('OTHER_ROLE_ID', '0')),      # Other
}

# Import FiveM functions
# from fivem import load_fivem_names, save_fivem_names

# Helper functions for reaction roles
def get_role_menu_gif():
    """Get the custom role menu GIF URL if available"""
    gif_file_path = os.path.join(os.path.dirname(__file__), 'role_menu_gif.txt')
    
    if os.path.exists(gif_file_path):
        try:
            with open(gif_file_path, 'r') as f:
                return f.read().strip()
        except:
            pass
            
    # Default GIF if none is set
    return "https://media.giphy.com/media/3o7qE6zfkGHpAQgLrq/giphy.gif"

def save_message_id(message_id):
    """Save the reaction message ID to a file so we can find it again on restart"""
    message_id_path = os.path.join(os.path.dirname(__file__), 'reaction_message_id.txt')
    try:
        with open(message_id_path, 'w') as f:
            f.write(str(message_id))
    except Exception as e:
        print(f"❌ Failed to save message ID: {e}")

def load_message_id():
    """Load the saved reaction message ID if it exists"""
    message_id_path = os.path.join(os.path.dirname(__file__), 'reaction_message_id.txt')
    if os.path.exists(message_id_path):
        try:
            with open(message_id_path, 'r') as f:
                return int(f.read().strip())
        except Exception:
            return None
    return None

# Bot setup with intents
intents = discord.Intents.default()
intents.members = True  # Required for member events (privileged intent)
intents.guilds = True
intents.message_content = True  # Required for reading message content (privileged intent)
intents.reactions = True  # Required for reaction events

bot_kwargs = {
    'command_prefix': '!',
    'intents': intents,
}

if APPLICATION_ID:
    bot_kwargs['application_id'] = APPLICATION_ID

bot = commands.Bot(**bot_kwargs)

# Add app_commands tree for slash commands
tree = bot.tree


async def setup_hook():
    print("🔄 Running setup_hook...")

    # ── Load all Cog extensions ───────────────────────────────────────────────
    extensions = [
        "font_sync",
        "welcome",
        "server_logs",
        "birthdays",
        "bot_status",
        "stream_alerts",
        "tickets",
        "protection",
        "temp_vc",
        "server_template",
        "server_backup",
        "dashboard_api",
        "notifications",
        "webhook_messages",
        "server_stats",
        "invite_tracker",
        "role_sync",
        "dev_global_logs",
        "music",
        "self_roles",
        "role_restore",
        "sticky_messages",
        "auto_reactions",
        "anti_hacked",
        "honeypot",
    ]
    for ext in extensions:
        try:
            await bot.load_extension(ext)
        except Exception as e:
            print(f"❌ Failed to load extension '{ext}': {e}")

    # Global sync inside setup hook
    try:
        global_synced = await bot.tree.sync()
        print(f"🌍 Global sync: {len(global_synced)} command(s) → {[c.name for c in global_synced]}")
        bot.tree.copy_global_to(guild=GUILD_OBJECT)
        guild_synced = await bot.tree.sync(guild=GUILD_OBJECT)
        print(f"🏠 Guild sync:  {len(guild_synced)} command(s) → {[c.name for c in guild_synced]}")
    except Exception as e:
        print(f"⚠️ Command sync warning: {e}")

bot.setup_hook = setup_hook

@tree.command(name="sync-commands", description="Sync the bot's slash commands to this server")
async def sync_commands(interaction: discord.Interaction):
    """Sync slash commands to the current guild."""
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("You need the Manage Guild permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        synced = await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"✅ Synced {len(synced)} slash command(s) to this server.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to sync commands: {e}", ephemeral=True)

# --- SLASH COMMANDS ---
# /reactionroles command
@tree.command(name="reactionroles", description="Create the reaction roles message")
async def reactionroles(interaction: discord.Interaction):
    """Create the reaction roles message (slash command)"""
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message("You need the Manage Roles permission to use this command.", ephemeral=True)
        return

    await interaction.response.send_message("Setting up reaction roles...", ephemeral=True)
    await auto_setup_reaction_roles()

# Debug command to test custom emojis
@tree.command(name="testemojis", description="Test if custom emojis are working")
async def testemojis(interaction: discord.Interaction):
    """Test custom emojis (slash command)"""
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message("You need the Manage Roles permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    test_message = "Testing custom emojis:\n"
    
    for emoji, role_id in EMOJI_ROLE_MAP.items():
        role = interaction.guild.get_role(role_id) if role_id != 0 else None
        role_name = role.name if role else f"Role ID {role_id} (not found)"
        
        try:
            # Try to send the emoji in a message
            test_message += f"{emoji} → {role_name}\n"
        except Exception as e:
            test_message += f"❌ {emoji} → ERROR: {e}\n"
    
    await interaction.followup.send(test_message, ephemeral=True)

# Tracker for startup command sync success status
command_sync_succeeded = False

# Diagnostics command
@tree.command(name="botdiagnostics", description="Display system and diagnostic info for GKR Bot")
async def botdiagnostics(interaction: discord.Interaction):
    """Display system diagnostics (slash command)"""
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You need the Manage Guild permission to use this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        # Count registered top-level slash commands
        guild_cmds = len(bot.tree.get_commands(guild=GUILD_OBJECT))
        global_cmds = len(bot.tree.get_commands())
        total_cmds = guild_cmds + global_cmds

        # Check intents status
        members_intent = "✅ Enabled" if bot.intents.members else "❌ Disabled"
        message_intent = "✅ Enabled" if bot.intents.message_content else "❌ Disabled"
        
        # Check command sync success status
        sync_status = "✅ Succeeded" if command_sync_succeeded else "❌ Failed / Pending"

        embed = discord.Embed(
            title="🤖 GKR Bot Diagnostics",
            description="Diagnostic overview and status details for GKR Bot.",
            color=0x8A2BE2  # Vibrant purple
        )
        embed.add_field(name="🤖 Bot Name", value=f"`{bot.user}`", inline=True)
        embed.add_field(name="🆔 Application ID", value=f"`{bot.application_id or APPLICATION_ID}`", inline=True)
        embed.add_field(name="🏠 Guild ID", value=f"`{GUILD_ID}`", inline=True)
        embed.add_field(name="📦 Discord.py Version", value=f"`{discord.__version__}`", inline=True)
        embed.add_field(name="📋 Registered Slash Commands", value=f"`{total_cmds}`", inline=True)
        embed.add_field(name="🌐 Loaded Guilds", value=f"`{len(bot.guilds)}`", inline=True)
        embed.add_field(name="👥 Members Intent", value=members_intent, inline=True)
        embed.add_field(name="💬 Message Content Intent", value=message_intent, inline=True)
        embed.add_field(name="✅ Command Sync Status", value=sync_status, inline=True)
        embed.set_footer(text=f"Diagnostics run at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error compiling diagnostics: {e}", ephemeral=True)


# --- PING COMMANDS ---
ping_group = app_commands.Group(name="ping", description="Ping commands for the bot and roles")
bot.tree.add_command(ping_group)

@ping_group.command(name="bot", description="Show the bot's current websocket latency")
async def ping_bot(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot Latency: `{latency_ms}ms`",
        color=0x2ECC71 if latency_ms < 150 else (0xF1C40F if latency_ms < 300 else 0xE74C3C)
    )
    await interaction.response.send_message(embed=embed)

@ping_group.command(name="role", description="Mention a specific role (pinging only)")
@app_commands.default_permissions(manage_messages=True)
async def ping_role(interaction: discord.Interaction, role: discord.Role, message: str = None):
    # Temporarily make the role mentionable if it isn't
    was_mentionable = role.mentionable
    try:
        if not was_mentionable:
            await role.edit(mentionable=True)
        
        content = f"{role.mention}"
        if message:
            content += f"\n{message}"
            
        await interaction.response.send_message(content, allowed_mentions=discord.AllowedMentions(roles=True))
    except discord.Forbidden:
        await interaction.response.send_message("❌ I do not have permission to mention that role or edit its status.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
    finally:
        if not was_mentionable:
            try:
                await role.edit(mentionable=False)
            except:
                pass

# --- UTILITY SLASH COMMANDS ---

def format_text(text: str, style: str) -> str:
    """Helper to apply Markdown formatting to a text string."""
    if style == "bold":
        return f"**{text}**"
    elif style == "italic":
        return f"*{text}*"
    elif style == "underline":
        return f"_/__{text}__" if text.startswith("_") else f"__{text}__"  # prevent escaping conflicts
    elif style == "code":
        return f"`{text}`"
    elif style == "code_block":
        return f"```\n{text}\n```"
    return text


async def send_with_role_ping(
    interaction: discord.Interaction,
    target: discord.TextChannel | discord.Interaction,
    content: str | None,
    role: discord.Role | None,
    embed: discord.Embed | None = None,
    ephemeral: bool = False
) -> None:
    """Sends a message to either a TextChannel or an Interaction response, ensuring the role ping is active/notified."""
    guild = role.guild if role else (interaction.guild if interaction else None)
    me = guild.me if guild else None
    
    # Check if we need to temporarily enable role mentionability
    was_mentionable = False
    should_toggle = False
    if role and not role.mentionable and me:
        bot_has_manage_roles = me.guild_permissions.manage_roles
        bot_higher_than_role = me.top_role > role
        if bot_has_manage_roles and bot_higher_than_role:
            was_mentionable = role.mentionable
            should_toggle = True
            try:
                await role.edit(mentionable=True)
            except Exception:
                should_toggle = False

    try:
        allowed = discord.AllowedMentions(roles=True, everyone=True, users=True)
        if isinstance(target, discord.Interaction):
            if target.response.is_done():
                await target.followup.send(content=content, embed=embed, allowed_mentions=allowed, ephemeral=ephemeral)
            else:
                await target.response.send_message(content=content, embed=embed, allowed_mentions=allowed, ephemeral=ephemeral)
        else:
            # target is a TextChannel
            await target.send(content=content, embed=embed, allowed_mentions=allowed)
    finally:
        if should_toggle and role:
            try:
                await role.edit(mentionable=was_mentionable)
            except Exception:
                pass


FORMAT_CHOICES = [
    app_commands.Choice(name="Normal", value="normal"),
    app_commands.Choice(name="Bold", value="bold"),
    app_commands.Choice(name="Italic", value="italic"),
    app_commands.Choice(name="Underline", value="underline"),
    app_commands.Choice(name="Inline Code", value="code"),
    app_commands.Choice(name="Code Block", value="code_block")
]


# ── Modals for multi-line / formatted text input ───────────────────────────

class SayModal(discord.ui.Modal, title="✉️ Send a Message"):
    """Popup dialog capturing multi-line message body for /say."""
    message_text = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.paragraph,
        placeholder="Type or paste your message here.\nNewlines and spacing are fully preserved.",
        required=True,
        max_length=2000,
    )

    def __init__(self, target_channel: discord.TextChannel, ping_role: discord.Role | None, format_style: str):
        super().__init__()
        self.target_channel = target_channel
        self.ping_role = ping_role
        self.format_style = format_style

    async def on_submit(self, interaction: discord.Interaction) -> None:
        formatted_msg = format_text(str(self.message_text), self.format_style)
        
        if self.ping_role:
            # Discord passes the @everyone role as a normal role object, but its mention string
            # resolves to <@&guild_id> which doesn't actually ping everyone. We must use the literal string.
            mention_str = "@everyone" if self.ping_role.name == "@everyone" else self.ping_role.mention
            content = f"{mention_str} {formatted_msg}"
        else:
            content = formatted_msg
            
        try:
            await send_with_role_ping(interaction, self.target_channel, content, self.ping_role)
            await interaction.response.send_message(f"✅ Sent message to {self.target_channel.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to send message: {e}", ephemeral=True)


class DmModal(discord.ui.Modal, title="📨 Direct Message"):
    """Popup dialog capturing multi-line DM body for /dm."""
    message_text = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.paragraph,
        placeholder="Type or paste your DM here.\nNewlines and spacing are fully preserved.",
        required=True,
        max_length=2000,
    )

    def __init__(self, user: discord.Member | None, role: discord.Role | None):
        super().__init__()
        self._user = user
        self._role = role

    async def on_submit(self, interaction: discord.Interaction) -> None:
        message = str(self.message_text)
        await interaction.response.defer(ephemeral=True)

        if self._user:
            try:
                await self._user.send(message)
                await interaction.followup.send(f"✅ Successfully sent DM to {self._user.mention}.", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(f"❌ Failed to DM {self._user.mention}. (User has DMs closed or has blocked the bot)", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Error sending DM to {self._user.mention}: {e}", ephemeral=True)
            return

        if self._role:
            members = self._role.members
            if not members:
                await interaction.followup.send(f"⚠️ No members found with the role {self._role.mention}.", ephemeral=True)
                return
            await interaction.followup.send(f"⏳ Sending DMs to {len(members)} members with role {self._role.name}...", ephemeral=True)
            success = 0
            failed = 0
            for member in members:
                if member.bot:
                    continue
                try:
                    await member.send(message)
                    success += 1
                    await asyncio.sleep(0.5)
                except Exception:
                    failed += 1
            await interaction.followup.send(f"🎯 DM campaign complete: {success} sent, {failed} failed.", ephemeral=True)


class AnnouncementModal(discord.ui.Modal, title="📢 Create Announcement"):
    """Popup dialog capturing title + multi-line body for /announcement."""
    ann_title = discord.ui.TextInput(
        label="Announcement Title",
        style=discord.TextStyle.short,
        placeholder="e.g. Server Update — June 2026",
        required=True,
        max_length=256,
    )
    message_text = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.paragraph,
        placeholder="Type or paste your announcement here.\nNewlines and spacing are fully preserved.",
        required=True,
        max_length=4000,
    )

    def __init__(
        self,
        target_channel: discord.TextChannel,
        ping: str,
        ping_role: discord.Role | None,
        format_style: str,
        invoker: discord.Member,
    ):
        super().__init__()
        self.target_channel = target_channel
        self.ping = ping
        self.ping_role = ping_role
        self.format_style = format_style
        self.invoker = invoker

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ping_prefix = ""
        role_obj = None
        if self.ping == "everyone":
            ping_prefix = "@everyone"
        elif self.ping == "here":
            ping_prefix = "@here"
        elif self.ping == "role" and self.ping_role:
            ping_prefix = self.ping_role.mention
            role_obj = self.ping_role

        formatted_msg = format_text(str(self.message_text), self.format_style)

        embed = discord.Embed(
            title=f"📢  {str(self.ann_title)}",
            description=formatted_msg,
            color=0x8A2BE2,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(
            text=f"Announcement by {self.invoker.display_name}",
            icon_url=self.invoker.display_avatar.url
        )

        try:
            await send_with_role_ping(interaction, self.target_channel, ping_prefix if ping_prefix else None, role_obj, embed=embed)
            await interaction.response.send_message(f"✅ Announcement sent to {self.target_channel.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to send announcement: {e}", ephemeral=True)


class RulesModal(discord.ui.Modal, title="📋 Post Server Rules"):
    """Popup dialog for composing and posting the server rules embed."""
    rule_title = discord.ui.TextInput(
        label="Rules Title",
        style=discord.TextStyle.short,
        default="Server Rules",
        placeholder="e.g. Server Rules",
        required=True,
        max_length=256,
    )
    rules_text = discord.ui.TextInput(
        label="Rules Content",
        style=discord.TextStyle.paragraph,
        placeholder="Paste your full rules here. Newlines & spacing are preserved exactly as written.",
        required=True,
        max_length=4000,
    )
    image_url = discord.ui.TextInput(
        label="Image / GIF URL (optional)",
        style=discord.TextStyle.short,
        placeholder="https://... image or GIF link (leave blank for none)",
        required=False,
        max_length=1024,
    )

    def __init__(
        self,
        target_channel: discord.TextChannel,
        ping: str,
        ping_role: discord.Role | None,
    ):
        super().__init__()
        self.target_channel = target_channel
        self.ping = ping
        self.ping_role = ping_role

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild

        # Build ping content & role object
        ping_content = ""
        role_obj = None
        if self.ping == "everyone":
            ping_content = "@everyone"
        elif self.ping == "here":
            ping_content = "@here"
        elif self.ping == "role" and self.ping_role:
            ping_content = self.ping_role.mention
            role_obj = self.ping_role

        # Build embed — mirroring the style shown in the screenshot
        embed = discord.Embed(
            title=str(self.rule_title),
            description=str(self.rules_text),
            color=0x8A2BE2,  # GKR Purple
        )

        # Server name + icon as the embed author (top-left)
        embed.set_author(
            name=guild.name,
            icon_url=guild.icon.url if guild.icon else None,
        )

        # Server icon as the thumbnail (top-right of embed)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        # Optional image or GIF at the bottom of the embed
        url = str(self.image_url).strip()
        if url:
            embed.set_image(url=url)

        embed.set_footer(
            text=f"{guild.name} • Server Rules",
            icon_url=guild.icon.url if guild.icon else None,
        )

        try:
            await send_with_role_ping(
                interaction, self.target_channel,
                ping_content if ping_content else None,
                role_obj, embed=embed
            )
            await interaction.response.send_message(
                f"✅ Rules posted to {self.target_channel.mention}.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to post rules: {e}", ephemeral=True)


@tree.command(name="rules", description="Post the server rules as a beautiful formatted embed")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    channel="The channel to post rules in (optional, defaults to current channel)",
    ping="Who to ping alongside the rules post (optional)",
    role="Role to ping if ping is set to Role (optional)",
)
@app_commands.choices(
    ping=[
        app_commands.Choice(name="None", value="none"),
        app_commands.Choice(name="Everyone", value="everyone"),
        app_commands.Choice(name="Here", value="here"),
        app_commands.Choice(name="Role", value="role"),
    ]
)
async def rules_cmd(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    ping: str = "none",
    role: discord.Role | None = None,
) -> None:
    """Open a multi-line rules modal — paste your rules, add an optional image/GIF URL."""
    target_channel = channel or interaction.channel
    if not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message("❌ Target channel must be a text channel.", ephemeral=True)
        return

    if ping == "role" and not role:
        await interaction.response.send_message("❌ You selected role ping but did not specify a role.", ephemeral=True)
        return

    ping_role = role if ping == "role" else None
    await interaction.response.send_modal(RulesModal(target_channel, ping, ping_role))


@tree.command(name="say", description="Make GKR Bot send a message in a channel")
@app_commands.default_permissions(manage_messages=True)
@app_commands.describe(
    channel="The channel to send the message in (optional)",
    ping_role="Role to ping alongside the message (optional)",
    format="Text formatting style (optional)"
)
@app_commands.choices(format=FORMAT_CHOICES)
async def say(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    ping_role: discord.Role | None = None,
    format: str = "normal"
) -> None:
    """Open a multi-line message modal — newlines and spacing are fully preserved."""
    target_channel = channel or interaction.channel
    if not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message("❌ Target channel must be a text channel.", ephemeral=True)
        return
    await interaction.response.send_modal(SayModal(target_channel, ping_role, format))


@tree.command(name="dm", description="Send a direct message (DM) to a specific user or everyone with a role")
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    user="The specific user to DM (optional)",
    role="All members with this role to DM (optional)"
)
async def dm(
    interaction: discord.Interaction,
    user: discord.Member | None = None,
    role: discord.Role | None = None
) -> None:
    """Open a multi-line DM modal — newlines and spacing are fully preserved."""
    if not user and not role:
        await interaction.response.send_message("❌ You must specify either a user or a role to DM.", ephemeral=True)
        return
    await interaction.response.send_modal(DmModal(user, role))


@tree.command(name="announcement", description="Create a beautiful, formatted Embed announcement")
@app_commands.default_permissions(manage_messages=True)
@app_commands.describe(
    channel="The channel to send the announcement in (optional)",
    ping="Who to ping with the announcement: None | Everyone | Here | Role (optional)",
    role="Role to ping if ping is set to Role (optional)",
    format="Embed text formatting style (optional)"
)
@app_commands.choices(
    ping=[
        app_commands.Choice(name="None", value="none"),
        app_commands.Choice(name="Everyone", value="everyone"),
        app_commands.Choice(name="Here", value="here"),
        app_commands.Choice(name="Role", value="role")
    ],
    format=FORMAT_CHOICES
)
async def announcement(
    interaction: discord.Interaction,
    channel: discord.TextChannel | None = None,
    ping: str = "none",
    role: discord.Role | None = None,
    format: str = "normal"
) -> None:
    """Open a multi-line announcement modal (title + body) — newlines and spacing are fully preserved."""
    target_channel = channel or interaction.channel
    if not isinstance(target_channel, discord.TextChannel):
        await interaction.response.send_message("❌ Target channel must be a text channel.", ephemeral=True)
        return

    if ping == "role" and not role:
        await interaction.response.send_message("❌ You selected role ping but did not specify which role to ping.", ephemeral=True)
        return

    ping_role = role if ping == "role" else None
    await interaction.response.send_modal(
        AnnouncementModal(target_channel, ping, ping_role, format, interaction.user)
    )


@tree.command(name="valo", description="Invite players to join Valorant (Malayalam gaming call)")
@app_commands.describe(
    role="Specific game/gaming role to ping",
    format="Text formatting style (optional)",
    extra_text="Additional note or message details to add (optional)"
)
@app_commands.choices(format=FORMAT_CHOICES)
async def valo(
    interaction: discord.Interaction,
    role: discord.Role,
    format: str = "normal",
    extra_text: str | None = None
) -> None:
    """Send a fun Valorant ping invitation with custom formatting and role ping."""
    call_msg = "vada makale valo kalikam"
    if extra_text:
        call_msg = f"{call_msg} — {extra_text}"

    formatted_msg = format_text(call_msg, format)
    content = f"{role.mention} {formatted_msg}"

    await send_with_role_ping(interaction, interaction, content, role)


@tree.command(name="pubg", description="Invite players to join PUBG (Malayalam gaming call)")
@app_commands.describe(
    role="Specific game/gaming role to ping",
    format="Text formatting style (optional)",
    extra_text="Additional note or message details to add (optional)"
)
@app_commands.choices(format=FORMAT_CHOICES)
async def pubg(
    interaction: discord.Interaction,
    role: discord.Role,
    format: str = "normal",
    extra_text: str | None = None
) -> None:
    """Send a fun PUBG ping invitation with custom formatting and role ping."""
    call_msg = "vada makale pubg kalikam"
    if extra_text:
        call_msg = f"{call_msg} — {extra_text}"

    formatted_msg = format_text(call_msg, format)
    content = f"{role.mention} {formatted_msg}"

    await send_with_role_ping(interaction, interaction, content, role)


# Activity rotation list - Simple and focused activities
base_activities = [
    # Only two core activities
    {"type": discord.ActivityType.watching, "name": "all members 👀"},
    {"type": discord.ActivityType.playing, "name": "helping players 🤝"}
]

async def auto_setup_reaction_roles():
    """Automatically create a reaction role message in the specified channel on bot startup"""
    # Check if reaction channel is configured
    if REACTION_CHANNEL_ID == 0:
        print("⚠️ Reaction roles channel not configured. Set REACTION_CHANNEL_ID in .env file.")
        return
    
    # Get the guild and channel
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("❌ Guild not found for auto reaction roles setup")
        return
    
    channel = guild.get_channel(REACTION_CHANNEL_ID)
    if not channel:
        print(f"❌ Channel with ID {REACTION_CHANNEL_ID} not found for reaction roles")
        return
    
    print(f"🎮 Setting up auto reaction roles in channel: {channel.name}")
    
    # Use custom emojis from EMOJI_ROLE_MAP
    emoji_map = EMOJI_ROLE_MAP.copy()
    
    # Check if roles exist
    valid_roles = 0
    invalid_roles = []
    for emoji, role_id in emoji_map.items():
        role = guild.get_role(role_id)
        if role:
            valid_roles += 1
        else:
            invalid_roles.append((emoji, role_id))
    
    if valid_roles == 0:
        print("❌ No valid roles configured for reaction roles. Please check your role IDs in .env file.")
        return
    
    # Create the embed message with role options
    embed = discord.Embed(
        title="🎮 Choose Your Game Roles",
        description="React with an emoji below to receive a role.\nRoles grant you access to exclusive channels, updates, and community events.\n\nYou can remove your reaction anytime to remove the role.",
        color=0x8A2BE2  # Vibrant purple color
    )
    
    # Add a GIF banner image to the embed
    embed.set_image(url=get_role_menu_gif())
    
    # Add fields for each role
    for emoji, role_id in emoji_map.items():
        role = guild.get_role(role_id)
        if role:
            # Check which game based on role name or environment variable
            if "VALORANT" in str(role_id) or role_id == int(os.getenv('VALORANT_ROLE_ID', '0')):
                embed.add_field(
                    name=f"{emoji} — @{role.name}",
                    value="🔫 Tactical 5v5 shooter with abilities",
                    inline=False
                )
            elif "GTA" in str(role_id) or role_id == int(os.getenv('GTA_ROLE_ID', '0')):
                embed.add_field(
                    name=f"{emoji} — @{role.name}",
                    value="🚗 Open-world crime action adventure",
                    inline=False
                )
            else:  # Other
                embed.add_field(
                    name=f"{emoji} — @{role.name}",
                    value="🎲 Other awesome games",
                    inline=False
                )
    
    # Add footer with timestamp
    embed.set_footer(text="Powered by GKR Bot • Select your roles below")
    embed.timestamp = datetime.datetime.now()

    try:
        # Check if we should use existing message or create new one
        existing_msg_id = load_message_id()
        existing_message = None
        
        if existing_msg_id:
            try:
                existing_message = await channel.fetch_message(existing_msg_id)
                print(f"📜 Found existing reaction roles message (ID: {existing_msg_id})")
            except (discord.NotFound, discord.HTTPException):
                print(f"📜 Couldn't find existing message with ID {existing_msg_id}, will create new one")
        
        # Send header and embed message or update existing message
        if existing_message:
            # Update the existing message
            await existing_message.edit(embed=embed)
            message = existing_message
            print(f"🔄 Updated existing reaction roles message")
        else:
            # Send a header message
            await channel.send("**✨ `S E L F   R O L E S` ✨**")
            
            # Create a new message
            message = await channel.send(embed=embed)
            print(f"✨ Created new reaction roles message")
            
            # Save the message ID for future reference
            save_message_id(message.id)
        
        # Remove any existing reactions
        await message.clear_reactions()
        
        # Add reactions
        for emoji in emoji_map.keys():
            if guild.get_role(emoji_map[emoji]):
                try:
                    await message.add_reaction(emoji)
                except Exception as e:
                    print(f"❌ Failed to add reaction {emoji}: {e}")
        
        # Store the message ID for reaction handling
        global REACTION_MESSAGE_ID
        REACTION_MESSAGE_ID = message.id
        
        # The global EMOJI_ROLE_MAP is already set with custom emojis
        # No need to update it since we're using the original custom emojis
        
        print(f"✅ Auto reaction roles setup complete! Message ID: {REACTION_MESSAGE_ID}")
        
    except Exception as e:
        print(f"❌ Error setting up auto reaction roles: {e}")

def has_gkr_role(member: discord.Member) -> bool:
    """Check if a member has a GKR role by ID or by role name GKR."""
    # 1. Home guild check
    if member.guild.id == GUILD_ID:
        role = member.guild.get_role(BOT_ROLE_ID)
        if role and role in member.roles:
            return True
            
    # 2. Case-insensitive role name check for any guild
    for r in member.roles:
        if r.name.upper() == "GKR":
            return True
            
    return False


@tasks.loop(minutes=10)
async def nickname_sync_task():
    """Background task to sync nicknames for GKR role members across all guilds."""
    total_changed = 0
    total_failed = 0
    
    for guild in bot.guilds:
        roles = []
        if guild.id == GUILD_ID:
            br = guild.get_role(BOT_ROLE_ID)
            if br:
                roles.append(br)
        for r in guild.roles:
            if r.name.upper() == "GKR" and r not in roles:
                roles.append(r)
                
        if not roles:
            continue
            
        changed = 0
        failed = 0
        synced_members = set()
        
        for role in roles:
            for member in role.members:
                if member.id in synced_members:
                    continue
                synced_members.add(member.id)
                if member.nick != "GKR":
                    try:
                        await member.edit(nick="GKR")
                        changed += 1
                    except discord.Forbidden:
                        failed += 1
                    except discord.HTTPException:
                        failed += 1
                        
        if changed > 0:
            print(f"🎯 Server {guild.name} sync complete: {changed} changed, {failed} failed")
        total_changed += changed
        total_failed += failed
        
    if total_changed > 0:
        print(f"🎯 Global Nickname sync complete: {total_changed} changed, {total_failed} failed")
        print('='*50)


@bot.event
async def on_ready():
    global command_sync_succeeded
    
    # 1. Verify Bot is fully ready and in cache
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f"❌ ERROR: Bot is not a member of the configured Guild ID: {GUILD_ID}")
        print("💡 Ensure the bot has been invited to the server and the ID is correct.")
        return

    # Count registered top-level slash commands
    # Get actual Application ID
    actual_app_id = bot.application_id or bot.user.id

    # Print clean startup box
    print('='*50)
    print(f"🤖 Logged in as: {bot.user}")
    print(f"🆔 Application ID: {actual_app_id}")
    print(f"🏠 Home Guild ID: {GUILD_ID}")
    print('='*50)

    # Application ID configuration check
    if APPLICATION_ID and actual_app_id != APPLICATION_ID:
        print(f"⚠️  WARNING: Configured DISCORD_APPLICATION_ID ({APPLICATION_ID}) does not match the bot's actual Application ID ({actual_app_id})!")
        print("💡 Please update your .env file with the correct DISCORD_APPLICATION_ID.")
        print('='*50)

    # Verify the bot invite requirements and print warning if missing scopes
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={actual_app_id}&permissions=8&scope=bot%20applications.commands"
    print("📢 BOT INVITE REQUIREMENTS VERIFICATION:")
    print("⚠️  Warning: Ensure the bot was invited to the server using BOTH the 'bot' and 'applications.commands' scopes.")
    print("   Without 'applications.commands', slash commands will NOT appear in the server.")
    print(f"🔗 Recommended Invite Link: {invite_url}")
    print('='*50)

    # Check intents
    if not bot.intents.members:
        print("⚠️  WARNING: Members intent not enabled. Member join/update events won't work.")
    if not bot.intents.message_content:
        print("⚠️  WARNING: Message Content intent not enabled.")
    print('='*50)

    # Start task loops if they aren't running
    if not rotate_activity.is_running():
        rotate_activity.start()
        print("🔄 Activity rotation started!")
    if not periodic_nickname_sync.is_running():
        periodic_nickname_sync.start()
        print("🔄 Periodic nickname sync started!")

    # Check roles configurations in the guild
    try:
        bot_role = guild.get_role(BOT_ROLE_ID)
        member_role = guild.get_role(MEMBER_ROLE_ID)

        if bot_role:
            print(f'🎯 Bot management role: {bot_role.name} (ID: {bot_role.id})')
            if bot.intents.members:
                print(f'👑 Members with bot role: {len(bot_role.members)}')
        else:
            print(f'❌ WARNING: Bot role with ID {BOT_ROLE_ID} not found in guild')

        if member_role:
            print(f'👥 Member watch role: {member_role.name} (ID: {member_role.id})')
            if bot.intents.members:
                print(f'👥 Members with member role: {len(member_role.members)}')
        else:
            print(f'❌ WARNING: Member role with ID {MEMBER_ROLE_ID} not found in guild')
    except Exception as e:
        print(f'❌ Error checking role information: {e}')

    print('✅ Bot is ready to manage GKR nicknames!')
    print('='*50)

    # Start the nickname sync loop (runs every 10 mins)
    if not nickname_sync_task.is_running():
        nickname_sync_task.start()
        print('🔄 Global nickname sync background task started!')

    # Auto-setup reaction roles in the specified channel
    await auto_setup_reaction_roles()

    # Font Sync system starts automatically via cog_load() inside FontSyncCog


@bot.event
async def on_member_join(member):
    """Handle when a member joins any server the bot is in"""
    guild = member.guild

    print(f"👋 New member joined: {member.display_name} in {guild.name}")

    # ── GKR-specific nickname logic ──────────────────────────────────────────
    # Small delay to allow role assignment bots to work
    await asyncio.sleep(2)

    # Refresh member data to get updated roles
    try:
        member = await guild.fetch_member(member.id)
    except Exception:
        pass

    if has_gkr_role(member):
        if member.nick != "GKR":
            try:
                await member.edit(nick="GKR")
                print(f"🎉 Welcome! Changed {member.display_name}'s nickname to GKR in {guild.name} ✨")
            except discord.Forbidden:
                print(f"❌ No permission to change nickname for {member.display_name} in {guild.name}")
            except discord.HTTPException as e:
                print(f"⚠️  Failed to change nickname for {member.display_name} in {guild.name}: {e}")

@bot.event
async def on_member_update(before, after):
    """Handle when a member's roles are updated"""
    had_gkr = False
    if before.guild.id == GUILD_ID:
        br = before.guild.get_role(BOT_ROLE_ID)
        if br and br in before.roles:
            had_gkr = True
    if not had_gkr:
        had_gkr = any(r.name.upper() == "GKR" for r in before.roles)

    has_gkr = has_gkr_role(after)

    if has_gkr and not had_gkr:
        if after.nick != "GKR":
            try:
                await after.edit(nick="GKR")
                print(f"👑 Role upgrade! Changed {after.display_name} to GKR in {after.guild.name} (role added) 🚀")
            except discord.Forbidden:
                print(f"❌ No permission to change nickname for {after.display_name} in {after.guild.name}")
            except discord.HTTPException as e:
                print(f"⚠️  Failed to change nickname for {after.display_name} in {after.guild.name}: {e}")

@bot.event
async def on_guild_channel_create(channel):
    """Handle newly created guild channels for font sync"""
    service = getattr(bot, "font_sync_service", None)
    if service is None:
        return

    try:
        await service.on_channel_create(channel)
    except Exception as e:
        print(f"❌ Font Sync channel create handler failed: {e}")


@bot.event
async def on_guild_channel_update(before, after):
    """Handle guild channel updates for font sync"""
    service = getattr(bot, "font_sync_service", None)
    if service is None:
        return

    try:
        await service.on_channel_update(before, after)
    except Exception as e:
        print(f"❌ Font Sync channel update handler failed: {e}")

@tasks.loop(minutes=1)  # Changed from 5 seconds to 1 minute to respect Discord rate limits
async def rotate_activity():
    """Rotate bot activities with simple descriptions"""
    
    # Simply alternate between the two defined activities
    activity_data = random.choice(base_activities)
    activity = discord.Activity(type=activity_data["type"], name=activity_data["name"])
    
    await bot.change_presence(activity=activity)
    
    # Occasional logging to avoid console spam
    if random.randint(1, 12) == 1:  # Only log every ~12th change to reduce console spam
        print(f"🔄 Activity changed to: {activity.name}")

@tasks.loop(hours=1)  # Run nickname sync every hour
async def periodic_nickname_sync():
    """Periodically sync nicknames to catch any missed changes across all servers"""
    for guild in bot.guilds:
        roles = []
        if guild.id == GUILD_ID:
            br = guild.get_role(BOT_ROLE_ID)
            if br:
                roles.append(br)
        for r in guild.roles:
            if r.name.upper() == "GKR" and r not in roles:
                roles.append(r)
                
        if not roles:
            continue
            
        changed = 0
        synced_members = set()
        
        for role in roles:
            for member in role.members:
                if member.id in synced_members or member.bot:
                    continue
                synced_members.add(member.id)
                if member.nick != "GKR":
                    try:
                        await member.edit(nick="GKR")
                        changed += 1
                        print(f"🔄 Periodic sync: {member.display_name} → GKR in {guild.name}")
                        await asyncio.sleep(0.5)
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                        
        if changed > 0:
            print(f"🎯 Periodic sync complete: {changed} nicknames updated in {guild.name}")

@periodic_nickname_sync.before_loop
async def before_periodic_sync():
    await bot.wait_until_ready()

@bot.command(name='setnick')
@commands.has_permissions(manage_nicknames=True)
async def set_nickname(ctx, member: discord.Member = None):
    """Command to manually set nickname to GKR for users with the GKR role in this server"""
    if member is None:
        member = ctx.author
    
    if has_gkr_role(member):
        try:
            await member.edit(nick="GKR")
            await ctx.send(f"✅ Changed {member.mention}'s nickname to GKR!")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to change that member's nickname.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to change nickname: {e}")
    else:
        await ctx.send("❌ That member doesn't have a qualifying GKR role.")

@bot.command(name='setallnicks')
@commands.has_permissions(manage_nicknames=True)
async def set_all_nicknames(ctx):
    """Command to set all members with the GKR role to have GKR nickname in this server"""
    roles = []
    if ctx.guild.id == GUILD_ID:
        br = ctx.guild.get_role(BOT_ROLE_ID)
        if br:
            roles.append(br)
    for r in ctx.guild.roles:
        if r.name.upper() == "GKR" and r not in roles:
            roles.append(r)

    if not roles:
        await ctx.send("❌ GKR role not found on this server.")
        return
    
    changed = 0
    failed = 0
    synced_members = set()
    
    await ctx.send(f"🔄 Processing members with GKR roles...")
    
    for role in roles:
        for member in role.members:
            if member.id in synced_members or member.bot:
                continue
            synced_members.add(member.id)
            if member.nick != "GKR":
                try:
                    await member.edit(nick="GKR")
                    changed += 1
                    await asyncio.sleep(0.2)
                except (discord.Forbidden, discord.HTTPException):
                    failed += 1
    
    result_msg = f"✅ Changed {changed} nicknames to GKR"
    if failed > 0:
        result_msg += f" ({failed} failed due to permissions)"
    
    await ctx.send(result_msg)

@bot.command(name='syncnicks')
@commands.has_permissions(manage_nicknames=True)
async def sync_nicknames(ctx):
    """Manually sync all nicknames for members with the GKR role in this server"""
    await set_all_nicknames(ctx)

@bot.command(name='checkrole')
async def check_role(ctx):
    """Check how many members have both specified roles"""
    bot_role = ctx.guild.get_role(BOT_ROLE_ID)
    member_role = ctx.guild.get_role(MEMBER_ROLE_ID)
    
    embed = discord.Embed(title="Role Statistics", color=0x00ff00)
    
    if bot_role:
        bot_role_count = len(bot_role.members)
        embed.add_field(name=f"{bot_role.name} Role", value=f"{bot_role_count} members", inline=True)
    else:
        embed.add_field(name="Bot Role", value="❌ Not found", inline=True)
    
    if member_role:
        member_role_count = len(member_role.members)
        embed.add_field(name=f"{member_role.name} Role", value=f"{member_role_count} members", inline=True)
    else:
        embed.add_field(name="Member Role", value="❌ Not found", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='stats')
async def server_stats(ctx):
    """Display server statistics"""
    guild = ctx.guild
    embed = discord.Embed(title="Server Statistics", color=0x00ff00)
    embed.add_field(name="Total Members", value=guild.member_count, inline=True)
    embed.add_field(name="Online Members", value=len([m for m in guild.members if m.status != discord.Status.offline]), inline=True)
    embed.add_field(name="Text Channels", value=len(guild.text_channels), inline=True)
    embed.add_field(name="Voice Channels", value=len(guild.voice_channels), inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Server Created", value=guild.created_at.strftime("%B %d, %Y"), inline=True)
    
    bot_role = guild.get_role(BOT_ROLE_ID)
    member_role = guild.get_role(MEMBER_ROLE_ID)
    
    if bot_role:
        embed.add_field(name=f"{bot_role.name} Members", value=len(bot_role.members), inline=True)
    
    if member_role:
        embed.add_field(name=f"{member_role.name} Members", value=len(member_role.members), inline=True)
    
    await ctx.send(embed=embed)

# @bot.command(name='setfivem')
# async def set_fivem_name(ctx, *, fivem_name=None):
#     """Set your FiveM in-game player name
#     
#     Args:
#         fivem_name: The name you use in FiveM. If not provided, shows your current name.
#         
#     Example:
#         /setfivem John_Doe
#     """
#     # Check if we're in a server or DM
#     if not ctx.guild:
#         await ctx.send("❌ This command can only be used in a server.")
#         return
#     
#     # Get current FiveM names
#     fivem_names = load_fivem_names()
#     user_id = str(ctx.author.id)
#     
#     # If no name provided, show current name
#     if fivem_name is None:
#         if user_id in fivem_names:
#             embed = discord.Embed(
#                 title="Your FiveM Player Name", 
#                 description=f"Your current FiveM name is set to: **{fivem_names[user_id]}**",
#                 color=0x00FF00
#             )
#             embed.set_footer(text="Use /setfivem [new name] to change it")
#             
#             # Add instruction on how this works with FiveM
#             embed.add_field(
#                 name="How to use in FiveM", 
#                 value="This name will be used by FiveM servers that are connected to this Discord bot. "
#                       "Server admins can verify your identity using your Discord ID.",
#                 inline=False
#             )
#             
#             # Add Discord ID for reference
#             embed.add_field(
#                 name="Your Discord ID",
#                 value=f"`{user_id}`",
#                 inline=False
#             )
#             
#             await ctx.send(embed=embed)
#         else:
#             embed = discord.Embed(
#                 title="FiveM Player Name Not Set",
#                 description="❓ You don't have a FiveM name set yet. Use `/setfivem [your name]` to set one.",
#                 color=0xFFAA00
#             )
#             
#             embed.add_field(
#                 name="What is this for?",
#                 value="Setting your FiveM name allows server admins to verify your identity between Discord and FiveM servers "
#                       "that are connected to this bot.",
#                 inline=False
#             )
#             
#             await ctx.send(embed=embed)
#         return
#     
#     # Check if name is valid (basic validation)
#     if len(fivem_name) < 3:
#         await ctx.send("❌ FiveM name must be at least 3 characters long.")
#         return
#     
#     if len(fivem_name) > 32:
#         await ctx.send("❌ FiveM name must be less than 32 characters long.")
#         return
#     
#     # Update the name in our dictionary
#     fivem_names[user_id] = fivem_name
#     
#     # Save back to file
#     if save_fivem_names(fivem_names):
#         embed = discord.Embed(
#             title="FiveM Name Updated",
#             description=f"✅ Your FiveM player name has been set to:\n**{fivem_name}**",
#             color=0x00FF00
#         )
#         
#         # Add info about how this works
#         embed.add_field(
#             name="How This Works",
#             value="Your name is now stored in the bot's database. FiveM servers that are integrated "
#                   "with this bot can verify your identity using your Discord ID.",
#             inline=False
#         )
#         
#         # Add instruction for server owners
#         embed.add_field(
#             name="For Server Owners",
#             value="FiveM server owners can access the API to verify names at:\n"
#                   f"`http://your-bot-url:{PORT}/fivem/player/{user_id}`",
#             inline=False
#         )
#         
#         embed.set_footer(text="Note: This doesn't automatically change your name in FiveM")
#         await ctx.send(embed=embed)
#     else:
#         await ctx.send("❌ There was an error saving your FiveM name. Please try again later.")

# @bot.command(name='fivemexport')
# @commands.has_permissions(administrator=True)
# async def fivem_export(ctx):
#     """Export FiveM player names in a format suitable for server integration (admin only)"""
#     fivem_names = load_fivem_names()
#     
#     if not fivem_names:
#         await ctx.send("❓ No FiveM names have been registered yet.")
#         return
#     
#     # Create a nice looking embed with information
#     embed = discord.Embed(
#         title="FiveM Integration Guide",
#         description="Here's how to integrate this Discord bot with your FiveM server",
#         color=0x00AAFF
#     )
#     
#     # Add API information
#     embed.add_field(
#         name="API Endpoint - Single Player",
#         value=f"GET `http://your-bot-url:{PORT}/fivem/player/DISCORD_ID`\n"
#               f"Example: `http://your-bot-url:{PORT}/fivem/player/123456789012345678`",
#         inline=False
#     )
#     
#     embed.add_field(
#         name="API Endpoint - All Players",
#         value=f"GET `http://your-bot-url:{PORT}/fivem/players`\n"
#               f"**Requires:** Header `Authorization: Bearer {FIVEM_API_KEY}`",
#         inline=False
#     )
#     
#     embed.add_field(
#         name="Response Format",
#         value="```json\n"
#               '{\n'
#               '  "discord_id": "123456789012345678",\n'
#               '  "fivem_name": "Player_Name",\n'
#               '  "found": true\n'
#               '}\n'
#               "```",
#         inline=False
#     )
#     
#     embed.add_field(
#         name="FiveM Script Example",
#         value="```lua\n"
#               'local function GetPlayerDiscordName(discord_id)\n'
#               '    local apiUrl = "http://your-bot-url:' + str(PORT) + '/fivem/player/" .. discord_id\n'
#               '    PerformHttpRequest(apiUrl, function(statusCode, response, headers)\n'
#               '        if statusCode == 200 then\n'
#               '            local data = json.decode(response)\n'
#               '            print("Player Discord name: " .. data.fivem_name)\n'
#               '            -- Use data.fivem_name here\n'
#               '        else\n'
#               '            print("Player not found or error")\n'
#               '        end\n'
#               '    end, "GET")\n'
#               'end\n'
#               "```",
#         inline=False
#     )
#     
#     embed.add_field(
#         name="Verifying Players",
#         value="Use the Discord API to get a player's Discord ID from their FiveM identity, "
#               "then use the above endpoint to verify their registered name.",
#         inline=False
#     )
#     
#     # Add note about API key
#     embed.add_field(
#         name="⚠️ Security Note",
#         value=f"The API key used to access all players is `{FIVEM_API_KEY}`. "
#               f"Set this in your .env file using `FIVEM_API_KEY=your_secure_key_here`",
#         inline=False
#     )
#     
#     embed.set_footer(text=f"Total registered players: {len(fivem_names)}")
#     
#     # Send export instructions via DM to avoid leaking to public
#     try:
#         await ctx.author.send(embed=embed)
#         await ctx.send("✅ FiveM integration guide has been sent to your DMs!")
#     except discord.Forbidden:
#         await ctx.send("❌ I couldn't send you a DM. Please enable DMs from server members.")
#         await ctx.send(embed=embed)

# @bot.command(name='fivemhelp')
# async def fivem_help(ctx):
#     """Shows help on how the FiveM name integration works"""
#     embed = discord.Embed(
#         title="FiveM Name Integration - How It Works",
#         description="Understanding how the Discord FiveM name system works",
#         color=0x4B0082  # Indigo
#     )
#     
#     # Add explanations
#     embed.add_field(
#         name="What this does",
#         value="This bot stores your preferred FiveM name and links it to your Discord ID. "
#               "FiveM servers that are connected to this bot can look up your registered name.",
#         inline=False
#     )
#     
#     embed.add_field(
#         name="What this does NOT do",
#         value="• This does **NOT** automatically change your name in FiveM\n"
#               "• FiveM names are set within the FiveM client itself\n"
#               "• This is a verification system, not an automatic name changer",
#         inline=False
#     )
#     
#     embed.add_field(
#         name="How to use it",
#         value="1. Set your name using `/setfivem YourFiveMName`\n"
#               "2. Make sure your FiveM name matches what you registered\n"
#               "3. Server admins can verify your identity",
#         inline=False
#     )
#     
#     embed.add_field(
#         name="For server owners",
#         value="Server owners can use the bot's API to verify player identities. "
#               "Admin can get integration details using the `/fivemexport` command.",
#         inline=False
#     )
#     
#     await ctx.send(embed=embed)

# Simple HTTP server for Render deployment
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Get bot status
            status = {
                "status": "online" if bot.is_ready() else "offline",
                "bot_name": str(bot.user) if bot.user else "GKR Bot",
                "guilds": len(bot.guilds) if bot.guilds else 0,
                "message": "GKR Discord Bot is running! 🚀"
            }
            
            import json
            self.wfile.write(json.dumps(status, indent=2).encode())
        # elif self.path.startswith('/fivem/player/'):
        #     # Extract Discord ID from URL
        #     try:
        #         # Path format: /fivem/player/123456789
        #         discord_id = self.path.split('/fivem/player/')[1]
                
        #         # Load FiveM names
        #         fivem_names = load_fivem_names()
                
        #         # Check if player exists
        #         if discord_id in fivem_names:
        #             self.send_response(200)
        #             self.send_header('Content-type', 'application/json')
        #             self.end_headers()
                    
        #             response = {
        #                 "discord_id": discord_id,
        #                 "fivem_name": fivem_names[discord_id],
        #                 "found": True
        #             }
        #             self.wfile.write(json.dumps(response).encode())
        #         else:
        #             self.send_response(404)
        #             self.send_header('Content-type', 'application/json')
        #             self.end_headers()
                    
        #             response = {
        #                 "discord_id": discord_id,
        #                 "error": "Player not found",
        #                 "found": False
        #             }
        #             self.wfile.write(json.dumps(response).encode())
                    
        #     except Exception as e:
        #         self.send_response(500)
        #         self.send_header('Content-type', 'application/json')
        #         self.end_headers()
        #         self.wfile.write(json.dumps({"error": str(e)}).encode())
        
        # elif self.path == '/fivem/players' and 'Authorization' in self.headers:
        #     # API endpoint to get all players - requires API key
        #     auth_header = self.headers.get('Authorization')
        #     if auth_header == f"Bearer {FIVEM_API_KEY}":
        #         fivem_names = load_fivem_names()
                
        #         self.send_response(200)
        #         self.send_header('Content-type', 'application/json')
        #         self.end_headers()
        #         self.wfile.write(json.dumps(fivem_names).encode())
        #     else:
        #         self.send_response(401)
        #         self.send_header('Content-type', 'application/json')
        #         self.end_headers()
        #         self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())

        # elif self.path.startswith('/fivem/player/'):
        #     # Extract Discord ID from URL
        #     try:
        #         # Path format: /fivem/player/123456789
        #         discord_id = self.path.split('/fivem/player/')[1]
        #         
        #         # Load FiveM names
        #         fivem_names = load_fivem_names()
        #         
        #         # Check if player exists
        #         if discord_id in fivem_names:
        #             self.send_response(200)
        #             self.send_header('Content-type', 'application/json')
        #             self.end_headers()
        #             
        #             response = {
        #                 "discord_id": discord_id,
        #                 "fivem_name": fivem_names[discord_id],
        #                 "found": True
        #             }
        #             self.wfile.write(json.dumps(response).encode())
        #         else:
        #             self.send_response(404)
        #             self.send_header('Content-type', 'application/json')
        #             self.end_headers()
        #             
        #             response = {
        #                 "discord_id": discord_id,
        #                 "error": "Player not found",
        #                 "found": False
        #             }
        #             self.wfile.write(json.dumps(response).encode())
        #             
        #     except Exception as e:
        #         self.send_response(500)
        #         self.send_header('Content-type', 'application/json')
        #         self.end_headers()
        #         self.wfile.write(json.dumps({"error": str(e)}).encode())
        # 
        # elif self.path == '/fivem/players' and 'Authorization' in self.headers:
        #     # API endpoint to get all players - requires API key
        #     auth_header = self.headers.get('Authorization')
        #     if auth_header == f"Bearer {FIVEM_API_KEY}":
        #         fivem_names = load_fivem_names()
        #         
        #         self.send_response(200)
        #         self.send_header('Content-type', 'application/json')
        #         self.end_headers()
        #         self.wfile.write(json.dumps(fivem_names).encode())
        #     else:
        #         self.send_response(401)
        #         self.send_header('Content-type', 'application/json')
        #         self.end_headers()
        #         self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass

def start_http_server():
    """Start HTTP server for Render health checks"""
    try:
        server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
        print(f"🌐 HTTP server started on port {PORT} for Render deployment")
        server.serve_forever()
    except Exception as e:
        print(f"❌ Failed to start HTTP server: {e}")

@bot.command(name='rroles')
@commands.has_permissions(manage_roles=True)
async def setup_reaction_roles(ctx):
    """Create a reaction role message in the specified channel"""
    # Check if we're in the correct guild
    if ctx.guild.id != GUILD_ID:
        await ctx.send("❌ This command can only be used in the configured guild.")
        return
        
    # Check if we're in the correct channel for reaction roles
    if ctx.channel.id != REACTION_CHANNEL_ID:
        channel = ctx.guild.get_channel(REACTION_CHANNEL_ID)
        if channel:
            await ctx.send(f"❌ Reaction roles can only be set up in {channel.mention}")
        else:
            await ctx.send("❌ Reaction roles channel not configured. Set REACTION_CHANNEL_ID in .env file.")
        return
    
    # Check if roles exist
    valid_roles = 0
    invalid_roles = []
    for emoji, role_id in EMOJI_ROLE_MAP.items():
        role = ctx.guild.get_role(role_id)
        if role:
            valid_roles += 1
        else:
            invalid_roles.append((emoji, role_id))
    
    if valid_roles == 0:
        await ctx.send("❌ No valid roles configured. Please check your role IDs in .env file.")
        return
        
    if invalid_roles:
        warning = "⚠️ Some roles are not configured correctly:\n"
        for emoji, role_id in invalid_roles:
            warning += f"- Role ID {role_id} ({emoji}) not found\n"
        await ctx.send(warning)
    
    # Create the embed message with role options and enhanced visual design
    embed = discord.Embed(
        title="🎮 Choose Your Game Roles",
        description="React with an emoji below to receive a role.\nRoles grant you access to exclusive channels, updates, and community events.\n\nYou can remove your reaction anytime to remove the role.",
        color=0x8A2BE2  # Vibrant purple color to match your self-role image
    )
    
    # Add a cool GIF banner image to the embed
    embed.set_image(url=get_role_menu_gif())  # Use custom GIF if set
    
    # Add fields for each role with enhanced formatting
    for emoji, role_id in EMOJI_ROLE_MAP.items():
        role = ctx.guild.get_role(role_id)
        if role:
            # Create more visually appealing role entries
            if "valo" in emoji.lower():
                embed.add_field(
                    name=f"{emoji} — @{role.name}",
                    value="🔫 Tactical 5v5 shooter with abilities",
                    inline=False
                )
            elif "gta" in emoji.lower():
                embed.add_field(
                    name=f"{emoji} — @{role.name}",
                    value="🚗 Open-world crime action adventure",
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"{emoji} — @{role.name}",
                    value="🎲 Other awesome games",
                    inline=False
                )
    
    # Add footer with powered by text and timestamp
    embed.set_footer(text="Powered by GKR Bot • Select your roles below")
    embed.timestamp = datetime.datetime.now()
    
    # Send a header message with animated text effect
    await ctx.send("**✨ `S E L F   R O L E S` ✨**")
    
    # Send the embed message
    message = await ctx.send(embed=embed)
    
    # Add reactions
    for emoji in EMOJI_ROLE_MAP.keys():
        if ctx.guild.get_role(EMOJI_ROLE_MAP[emoji]):
            await message.add_reaction(emoji)
    
    # Store the message ID for reaction handling
    global REACTION_MESSAGE_ID
    REACTION_MESSAGE_ID = message.id
    await ctx.send(f"✅ Reaction roles set up! Message ID: {REACTION_MESSAGE_ID}")
    print(f"🎮 Reaction roles message created. ID: {REACTION_MESSAGE_ID}")

@bot.event
async def on_raw_reaction_add(payload):
    """Handle adding roles when users react to the reaction roles message"""
    # Skip if reaction is not on the reaction roles message or is from the bot
    if payload.message_id != REACTION_MESSAGE_ID or payload.user_id == bot.user.id:
        return
    
    # Skip if not in the specified channel
    if payload.channel_id != REACTION_CHANNEL_ID:
        return
        
    # Debug logging
    print(f"🔍 Reaction detected - Message ID: {payload.message_id}, Expected: {REACTION_MESSAGE_ID}")
    print(f"🔍 Emoji detected: {payload.emoji} (type: {type(payload.emoji)}, repr: {repr(str(payload.emoji))})")
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        print(f"❌ Guild not found: {payload.guild_id}")
        return
        
    member = guild.get_member(payload.user_id)
    if not member:
        print(f"❌ Member not found: {payload.user_id}")
        return
    
    # Convert emoji to string representation
    emoji = str(payload.emoji)
    
    print(f"🔍 Looking for emoji {emoji} in role map...")
    print(f"🔍 Available emojis in map: {list(EMOJI_ROLE_MAP.keys())}")
    
    # Check if this emoji is mapped to a role
    if emoji in EMOJI_ROLE_MAP:
        role_id = EMOJI_ROLE_MAP[emoji]
        role = guild.get_role(role_id)
        
        if role:
            # Add the role to the user
            try:
                await member.add_roles(role)
                print(f"✅ Added role {role.name} to {member.display_name}")
                
                # Keep only this user's reaction for this emoji (count stays at 1)
                try:
                    channel = guild.get_channel(payload.channel_id)
                    message = await channel.fetch_message(payload.message_id)
                    for reaction in message.reactions:
                        if str(reaction.emoji) == emoji:
                            async for user in reaction.users():
                                if user.id != payload.user_id and user.id != bot.user.id:
                                    await message.remove_reaction(reaction.emoji, user)
                except Exception as e:
                    print(f"⚠️ Warning when cleaning reactions: {e}")
                                
            except discord.Forbidden:
                print(f"❌ No permission to add role {role.name} to {member.display_name}")
            except discord.HTTPException as e:
                print(f"❌ Error adding role: {e}")
        else:
            print(f"❌ Role with ID {role_id} not found in guild")
    else:
        print(f"❌ Emoji {emoji} not found in role map")

@bot.event
async def on_raw_reaction_remove(payload):
    """Handle removing roles when users remove their reaction"""
    # Skip if reaction is not on the reaction roles message
    if payload.message_id != REACTION_MESSAGE_ID:
        return
        
    # Skip if not in the specified channel
    if payload.channel_id != REACTION_CHANNEL_ID:
        return
        
    print(f"🔍 Reaction removed - Message ID: {payload.message_id}")
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
        
    member = guild.get_member(payload.user_id)
    if not member:
        return
    
    emoji = str(payload.emoji)
    
    # Check if this emoji is mapped to a role
    if emoji in EMOJI_ROLE_MAP:
        role_id = EMOJI_ROLE_MAP[emoji]
        role = guild.get_role(role_id)
        
        if role:
            # Remove the role from the user
            try:
                await member.remove_roles(role)
                print(f"✅ Removed role {role.name} from {member.display_name}")
            except discord.Forbidden:
                print(f"❌ No permission to remove role {role.name} from {member.display_name}")
            except discord.HTTPException as e:
                print(f"❌ Error removing role: {e}")
        else:
            print(f"❌ Role with ID {role_id} not found in guild")
    else:
        print(f"❌ Emoji {emoji} not found in role map")

@bot.command(name='setrolemenugif')
@commands.has_permissions(manage_roles=True)
async def set_role_menu_gif(ctx, gif_url=None):
    """Set a custom GIF URL for the reaction roles menu
    
    Args:
        gif_url: The URL to the GIF you want to display. If not provided, shows current GIF
    
    Example:
        /setrolemenugif https://media.giphy.com/media/example/giphy.gif
    """
    # Save the GIF URL to a file
    gif_file_path = os.path.join(os.path.dirname(__file__), 'role_menu_gif.txt')
    
    # If no URL provided, show the current one
    if gif_url is None:
        try:
            if os.path.exists(gif_file_path):
                with open(gif_file_path, 'r') as f:
                    current_gif = f.read().strip()
                embed = discord.Embed(title="Current Role Menu GIF", color=0x8A2BE2)
                embed.set_image(url=current_gif)
                embed.description = f"Current GIF URL: {current_gif}\n\nTo change it, use `/setrolemenugif [new URL]`"
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ No custom GIF has been set yet. Use `/setrolemenugif [URL]` to set one.")
        except Exception as e:
            await ctx.send(f"❌ Error retrieving current GIF: {e}")
        return
        
    # Basic validation that it's a URL
    if not (gif_url.startswith('http://') or gif_url.startswith('https://')):
        await ctx.send("❌ Please provide a valid URL starting with http:// or https://")
        return
        
    # Save the URL
    try:
        with open(gif_file_path, 'w') as f:
            f.write(gif_url)
        
        # Show a preview
        embed = discord.Embed(title="Role Menu GIF Updated", color=0x8A2BE2)
        embed.set_image(url=gif_url)
        embed.description = "✅ Your custom GIF has been set! It will be used for future reaction role menus."
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Failed to save GIF URL: {e}")

@bot.command(name='debugroles')
@commands.has_permissions(manage_roles=True)
async def debug_reaction_roles(ctx):
    """Debug version of reaction roles setup with detailed logging"""
    await ctx.send("🔧 **Debugging Reaction Roles Setup**")
    
    # Check emoji configuration
    await ctx.send("🔍 **Current Emoji Configuration:**")
    debug_msg = ""
    for emoji, role_id in EMOJI_ROLE_MAP.items():
        role = ctx.guild.get_role(role_id)
        role_name = role.name if role else "NOT FOUND"
        debug_msg += f"- Emoji `{emoji}` -> Role ID: `{role_id}` ({role_name})\n"
    await ctx.send(f"```{debug_msg}```")
    
    # Check if we have valid custom emojis
    await ctx.send("🔍 **Testing Custom Emoji Access:**")
    
    # Get all emojis from the server
    all_emojis = ctx.guild.emojis
    await ctx.send(f"Found {len(all_emojis)} custom emojis in the server")
    
    # List the first few emojis
    emoji_list = ""
    for i, emoji in enumerate(all_emojis[:10]):  # Show up to 10 emojis
        emoji_list += f"{i+1}. {str(emoji)} - `{str(emoji)}` (ID: {emoji.id})\n"
    await ctx.send(f"**Available Custom Emojis:**\n{emoji_list}")
    
    # Try creating a simplified reaction role message with standard emojis
    await ctx.send("🔧 **Creating test reaction roles with standard emojis**")
    
    # Create a test embed
    embed = discord.Embed(
        title="🎮 Test Role Selection",
        description="React to get roles (using standard emojis for testing)",
        color=0xFF0000
    )
    
    # Use standard emojis instead
    test_emojis = {
        "🔴": int(os.getenv('VALORANT_ROLE_ID', '0')),
        "🟢": int(os.getenv('GTA_ROLE_ID', '0')),
        "🟣": int(os.getenv('OTHER_ROLE_ID', '0')),
    }
    
    for emoji, role_id in test_emojis.items():
        role = ctx.guild.get_role(role_id)
        if role:
            embed.add_field(name=f"{emoji} {role.name}", value=f"Click {emoji} to get this role", inline=False)
    
    test_msg = await ctx.send(embed=embed)
    
    # Add standard emoji reactions
    for emoji in test_emojis.keys():
        try:
            await test_msg.add_reaction(emoji)
            await ctx.send(f"✅ Successfully added standard emoji reaction: {emoji}")
        except Exception as e:
            await ctx.send(f"❌ Failed to add reaction {emoji}: {e}")
    
    await ctx.send("✅ Test complete! Try reacting to the message above.")
    
    # Guide to fix custom emoji issues
    help_text = (
        "**📋 To fix custom emoji issues:**\n"
        "1. Make sure the bot is in the server where the emojis are located\n"
        "2. The format for custom emojis should be `<:name:id>` or `<a:name:id>` for animated\n"
        "3. Try using `/emoji` command in Discord to see emoji codes\n"
        "4. You can also use standard emojis like 🔴, 🟢, 🔵 instead"
    )
    await ctx.send(help_text)

@bot.command(name='simpleroles')
@commands.has_permissions(manage_roles=True)
async def simple_reaction_roles(ctx):
    """Create a reaction role message with standard emojis (easier compatibility)"""
    # Check if we're in the correct guild
    if ctx.guild.id != GUILD_ID:
        await ctx.send("❌ This command can only be used in the configured guild.")
        return
        
    # Check if we're in the correct channel for reaction roles
    if ctx.channel.id != REACTION_CHANNEL_ID:
        channel = ctx.guild.get_channel(REACTION_CHANNEL_ID)
        if channel:
            await ctx.send(f"❌ Reaction roles can only be set up in {channel.mention}")
        else:
            await ctx.send("❌ Reaction roles channel not configured. Set REACTION_CHANNEL_ID in .env file.")
        return
    
    # Create mapping using standard emojis instead of custom ones
    standard_emoji_map = {
        "🔴": int(os.getenv('VALORANT_ROLE_ID', '0')),  # Valorant (red circle)
        "🟢": int(os.getenv('GTA_ROLE_ID', '0')),       # GTA (green circle)
        "🟣": int(os.getenv('OTHER_ROLE_ID', '0')),     # Other (purple circle)
    }
    
    # Check if roles exist
    valid_roles = 0
    invalid_roles = []
    for emoji, role_id in standard_emoji_map.items():
        role = ctx.guild.get_role(role_id)
        if role:
            valid_roles += 1
        else:
            invalid_roles.append((emoji, role_id))
    
    if valid_roles == 0:
        await ctx.send("❌ No valid roles configured. Please check your role IDs in .env file.")
        return
    
    # Create the embed message with role options
    embed = discord.Embed(
        title="🎮 Choose Your Game Roles",
        description="React with an emoji below to receive a role.\nRoles grant you access to exclusive channels, updates, and community events.\n\nYou can remove your reaction anytime to remove the role.",
        color=0x8A2BE2  # Vibrant purple color
    )
    
    # Add a GIF banner image to the embed
    embed.set_image(url=get_role_menu_gif())
    
    # Add fields for each role
    for emoji, role_id in standard_emoji_map.items():
        role = ctx.guild.get_role(role_id)
        if role:
            if emoji == "🔴":  # Valorant
                embed.add_field(
                    name=f"{emoji} — @{role.name}",
                    value="🔫 Tactical 5v5 shooter with abilities",
                    inline=False
                )
            elif emoji == "🟢":  # GTA
                embed.add_field(
                    name=f"{emoji} — @{role.name}",
                    value="🚗 Open-world crime action adventure",
                    inline=False
                )
            else:  # Other
                embed.add_field(
                    name=f"{emoji} — @{role.name}",
                    value="🎲 Other awesome games",
                    inline=False
                )
    
    # Add footer with timestamp
    embed.set_footer(text="Powered by GKR Bot • Select your roles below")
    embed.timestamp = datetime.datetime.now()
    
    # Send a header message
    await ctx.send("**✨ `S E L F   R O L E S` ✨**")
    
    # Send the embed message
    message = await ctx.send(embed=embed)
    
    # Add reactions
    for emoji in standard_emoji_map.keys():
        if ctx.guild.get_role(standard_emoji_map[emoji]):
            try:
                await message.add_reaction(emoji)
            except Exception as e:
                await ctx.send(f"❌ Failed to add reaction {emoji}: {e}")
    
    # Store the message ID for reaction handling
    global REACTION_MESSAGE_ID
    REACTION_MESSAGE_ID = message.id
    
    # We also need to update our global EMOJI_ROLE_MAP to use these standard emojis
    global EMOJI_ROLE_MAP
    EMOJI_ROLE_MAP = standard_emoji_map
    
    await ctx.send(f"✅ Simple reaction roles set up! Message ID: {REACTION_MESSAGE_ID}")
    print(f"🎮 Simple reaction roles message created. ID: {REACTION_MESSAGE_ID}")

# Run the bot
if __name__ == "__main__":
    try:
        # Start HTTP server for Render in a separate thread
        server_thread = Thread(target=start_http_server)
        server_thread.daemon = True
        server_thread.start()
        print(f"🌐 HTTP server started on port {PORT}")
        
        # Start the bot
        print('='*50)
        print("🚀 Starting GKR Discord Bot...")
        print(f"⚙️ Configured for Guild ID: {GUILD_ID}")
        if REACTION_CHANNEL_ID != 0:
            print(f"🎮 Reaction roles channel ID: {REACTION_CHANNEL_ID}")
        else:
            print("⚠️ Reaction roles channel not set. Use REACTION_CHANNEL_ID in .env")
        
        # Load FiveM cog
        # bot.load_extension("fivem")
        # print("🎮 FiveM integration loaded")
        
        print('='*50)
        
        # Run the bot
        bot.run(TOKEN)
    except discord.PrivilegedIntentsRequired as e:
        print('='*50)
        print("❌ ERROR: Privileged Intents Required")
        print("🔍 This bot requires privileged intents that are not enabled.")
        print("\n📋 To fix this issue:")
        print("1. Go to https://discord.com/developers/applications/")
        print("2. Select your bot application")
        print("3. Go to the 'Bot' section")
        print("4. Enable 'SERVER MEMBERS INTENT' and 'MESSAGE CONTENT INTENT'")
        print("5. Save changes and restart the bot")
        print('='*50)
    except discord.LoginFailure:
        print('='*50)
        print("❌ ERROR: Invalid Token")
        print("🔑 The Discord token is invalid or expired.")
        print("\n📋 To fix this issue:")
        print("1. Check your .env file and ensure DISCORD_TOKEN is correct")
        print("2. Generate a new token if necessary at https://discord.com/developers/applications/")
        print('='*50)
    except Exception as e:
        print('='*50)
        print(f"❌ ERROR: An unexpected error occurred: {e}")
        print('='*50)