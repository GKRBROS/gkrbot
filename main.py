import discord
from discord.ext import commands, tasks
import os
import datetime
import asyncio
import random
from dotenv import load_dotenv
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Load environment variables
load_dotenv()

# Bot configuration
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = int(os.getenv('DISCORD_GUILD_ID'))
BOT_ROLE_ID = int(os.getenv('BOT_ROLE_ID'))  # Role for bot nickname management
MEMBER_ROLE_ID = int(os.getenv('memeber_role_id'))  # Role for member count watching
PORT = int(os.getenv('PORT', 8080))

# Reaction roles configuration
REACTION_CHANNEL_ID = int(os.getenv('REACTION_CHANNEL_ID', '0'))  # Default to 0 if not set
REACTION_MESSAGE_ID = None  # Will be set when message is created

# Emoji to role mapping - Use custom emoji IDs from your server
# You must first upload gta5.jpeg, other.jpeg, and valo.jpeg as custom emojis in your Discord server
# Then replace these with your actual emoji IDs and names
EMOJI_ROLE_MAP = {
    # Format for custom emoji is either:
    # "<:emoji_name:emoji_id>" or "<a:emoji_name:emoji_id>" for animated emojis
    "<:valo:1416294130648088718>": int(os.getenv('VALORANT_ROLE_ID', '0')),    # Valorant
    "<:gta5:1416294123987669094>": int(os.getenv('GTA_ROLE_ID', '0')),         # GTA V
    "<:other:1416294127972384818>": int(os.getenv('OTHER_ROLE_ID', '0')),      # Other
}

# Bot setup with intents
intents = discord.Intents.default()
intents.members = True  # Required for member events (privileged intent)
intents.guilds = True
intents.message_content = True  # Required for reading message content (privileged intent)
intents.reactions = True  # Required for reaction events

bot = commands.Bot(command_prefix='/', intents=intents)

# Activity rotation list - Simple and focused activities
base_activities = [
    # Only two core activities
    {"type": discord.ActivityType.watching, "name": "all members �"},
    {"type": discord.ActivityType.playing, "name": "helping players 🤝"}
]

@bot.event
async def on_ready():
    print('='*50)
    print(f'🤖 {bot.user} is now ONLINE and ready to rock! 🚀')
    print(f'🌐 Connected to {len(bot.guilds)} guild(s)')
    print('='*50)
    
    # Check if we have the required intents
    if not bot.intents.members:
        print("⚠️  WARNING: Members intent not enabled. Member join/update events won't work.")
    
    # Start the activity rotation
    rotate_activity.start()
    print("🔄 Activity rotation started! (Every 5 seconds - Super Dynamic!)")
    
    # Start periodic nickname sync
    periodic_nickname_sync.start()
    print("🔄 Periodic nickname sync started! (Every hour)")
    
    # Update member count activity
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f'🏠 Guild: {guild.name}')
        print(f'👥 Members: {guild.member_count}')
        
        # Check if we can access member information
        try:
            # Try to get role information for both roles
            bot_role = guild.get_role(BOT_ROLE_ID)
            member_role = guild.get_role(MEMBER_ROLE_ID)
            
            if bot_role:
                print(f'🎯 Bot management role: {bot_role.name} (ID: {bot_role.id})')
                if bot.intents.members:
                    print(f'👑 Members with bot role: {len(bot_role.members)}')
                else:
                    print('⚠️  Cannot count bot role members without Members intent')
            else:
                print(f'❌ WARNING: Bot role with ID {BOT_ROLE_ID} not found in guild')
            
            if member_role:
                print(f'👥 Member watch role: {member_role.name} (ID: {member_role.id})')
                if bot.intents.members:
                    print(f'� Members with member role: {len(member_role.members)}')
                else:
                    print('⚠️  Cannot count member role members without Members intent')
            else:
                print(f'❌ WARNING: Member role with ID {MEMBER_ROLE_ID} not found in guild')
                
        except Exception as e:
            print(f'❌ Error checking role information: {e}')
    
    print('✅ Bot is ready to manage GKR nicknames!')
    print('='*50)
    
    # Sync nicknames for existing members with the role
    await sync_existing_nicknames()

async def sync_existing_nicknames():
    """Sync nicknames for all existing members with the specified role"""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("❌ Guild not found for nickname sync")
        return
    
    bot_role = guild.get_role(BOT_ROLE_ID)
    if not bot_role:
        print("❌ Bot role not found for nickname sync")
        return
    
    print(f"🔄 Starting nickname sync for {bot_role.name} role members...")
    
    changed = 0
    failed = 0
    
    for member in bot_role.members:
        if member.nick != "GKR":
            try:
                await member.edit(nick="GKR")
                changed += 1
                print(f"✅ Synced {member.display_name} → GKR")
            except discord.Forbidden:
                failed += 1
                print(f"❌ No permission to change {member.display_name}")
            except discord.HTTPException as e:
                failed += 1
                print(f"⚠️  Failed to change {member.display_name}: {e}")
    
    print(f"🎯 Nickname sync complete: {changed} changed, {failed} failed")
    print('='*50)

@bot.event
async def on_member_join(member):
    """Handle when a member joins the server"""
    guild = member.guild
    
    # Check if this is the correct guild
    if guild.id != GUILD_ID:
        return
    
    print(f"👋 New member joined: {member.display_name}")
    
    # Small delay to allow role assignment bots to work
    await asyncio.sleep(2)
    
    # Refresh member data to get updated roles
    try:
        member = await guild.fetch_member(member.id)
    except:
        pass
    
    try:
        # Check if the member has the specified role
        role = guild.get_role(BOT_ROLE_ID)
        if role and role in member.roles:
            # Change nickname to GKR
            await member.edit(nick="GKR")
            print(f"🎉 Welcome! Changed {member.display_name}'s nickname to GKR ✨")
            
            # Optional: Send a welcome message (you can uncomment if you want)
            # channel = discord.utils.get(guild.channels, name='general')
            # if channel:
            #     await channel.send(f"🔥 Welcome {member.mention}! You're now officially **GKR**! 👑")
        else:
            print(f"ℹ️  {member.display_name} doesn't have the required role yet")
            
    except discord.Forbidden:
        print(f"❌ No permission to change nickname for {member.display_name}")
    except discord.HTTPException as e:
        print(f"⚠️  Failed to change nickname for {member.display_name}: {e}")

@bot.event
async def on_member_update(before, after):
    """Handle when a member's roles are updated"""
    # Check if this is the correct guild
    if after.guild.id != GUILD_ID:
        return
    
    # Check if the specified role was added
    role = after.guild.get_role(BOT_ROLE_ID)
    if role:
        # If role was added and nickname isn't already GKR
        if role not in before.roles and role in after.roles:
            if after.nick != "GKR":
                try:
                    await after.edit(nick="GKR")
                    print(f"👑 Role upgrade! Changed {after.display_name} to GKR (role added) 🚀")
                except discord.Forbidden:
                    print(f"❌ No permission to change nickname for {after.display_name}")
                except discord.HTTPException as e:
                    print(f"⚠️  Failed to change nickname for {after.display_name}: {e}")

@tasks.loop(seconds=5)  # Changed to 5 seconds for continuous automatic rotation
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
    """Periodically sync nicknames to catch any missed changes"""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    
    bot_role = guild.get_role(BOT_ROLE_ID)
    if not bot_role:
        return
    
    changed = 0
    
    for member in bot_role.members:
        if member.nick != "GKR":
            try:
                await member.edit(nick="GKR")
                changed += 1
                print(f"🔄 Periodic sync: {member.display_name} → GKR")
            except (discord.Forbidden, discord.HTTPException):
                pass
    
    if changed > 0:
        print(f"🎯 Periodic sync complete: {changed} nicknames updated")

@periodic_nickname_sync.before_loop
async def before_periodic_sync():
    await bot.wait_until_ready()

@bot.command(name='setnick')
@commands.has_permissions(manage_nicknames=True)
async def set_nickname(ctx, member: discord.Member = None):
    """Command to manually set nickname to GKR for users with the specified role"""
    if member is None:
        member = ctx.author
    
    # Check if member has the specified role
    role = ctx.guild.get_role(BOT_ROLE_ID)
    if role and role in member.roles:
        try:
            await member.edit(nick="GKR")
            await ctx.send(f"✅ Changed {member.mention}'s nickname to GKR!")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to change that member's nickname.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to change nickname: {e}")
    else:
        await ctx.send("❌ That member doesn't have the required role.")

@bot.command(name='setallnicks')
@commands.has_permissions(manage_nicknames=True)
async def set_all_nicknames(ctx):
    """Command to set all members with the specified role to have GKR nickname"""
    role = ctx.guild.get_role(BOT_ROLE_ID)
    if not role:
        await ctx.send("❌ Specified role not found.")
        return
    
    changed = 0
    failed = 0
    
    await ctx.send(f"🔄 Processing members with {role.name} role...")
    
    for member in role.members:
        if member.nick != "GKR":
            try:
                await member.edit(nick="GKR")
                changed += 1
            except (discord.Forbidden, discord.HTTPException):
                failed += 1
    
    result_msg = f"✅ Changed {changed} nicknames to GKR"
    if failed > 0:
        result_msg += f" ({failed} failed due to permissions)"
    
    await ctx.send(result_msg)

@bot.command(name='syncnicks')
@commands.has_permissions(manage_nicknames=True)
async def sync_nicknames(ctx):
    """Manually sync all nicknames for members with the specified role"""
    role = ctx.guild.get_role(BOT_ROLE_ID)
    if not role:
        await ctx.send("❌ Specified role not found.")
        return
    
    changed = 0
    failed = 0
    
    await ctx.send(f"🔄 Syncing nicknames for all {role.name} role members...")
    
    for member in role.members:
        if member.nick != "GKR":
            try:
                await member.edit(nick="GKR")
                changed += 1
            except (discord.Forbidden, discord.HTTPException):
                failed += 1
    
    result_msg = f"✅ Sync complete: {changed} nicknames updated to GKR"
    if failed > 0:
        result_msg += f" ({failed} failed due to permissions)"
    
    await ctx.send(result_msg)

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

@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member not found.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Ignore unknown commands
    else:
        print(f"Unexpected error: {error}")

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

@bot.command(name='reactionroles')
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
            # Add the role to the user
            try:
                await member.add_roles(role)
                print(f"✅ Added role {role.name} to {member.display_name}")
                
                # Keep only this user's reaction for this emoji (count stays at 1)
                channel = guild.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)
                for reaction in message.reactions:
                    if str(reaction.emoji) == emoji:
                        async for user in reaction.users():
                            if user.id != payload.user_id and user.id != bot.user.id:
                                await message.remove_reaction(reaction.emoji, user)
                                
            except discord.Forbidden:
                print(f"❌ No permission to add role {role.name} to {member.display_name}")
            except discord.HTTPException as e:
                print(f"❌ Error adding role: {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    """Handle removing roles when users remove their reaction"""
    # Skip if reaction is not on the reaction roles message
    if payload.message_id != REACTION_MESSAGE_ID:
        return
        
    # Skip if not in the specified channel
    if payload.channel_id != REACTION_CHANNEL_ID:
        return
        
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