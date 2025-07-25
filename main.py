import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import asyncio
import random
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

# Bot setup with intents
intents = discord.Intents.default()
intents.members = True  # Required for member events (privileged intent)
intents.guilds = True
intents.message_content = True  # Required for reading message content (privileged intent)

bot = commands.Bot(command_prefix='!', intents=intents)

# Activity rotation list - Cool and dynamic activities
base_activities = [
    # Watching activities
    {"type": discord.ActivityType.watching, "name": "the member count 👥"},
    {"type": discord.ActivityType.watching, "name": "{member_count} members online 🔥"},
    {"type": discord.ActivityType.watching, "name": "GKR members grow 📈"},
    {"type": discord.ActivityType.watching, "name": "over the server 👀"},
    {"type": discord.ActivityType.watching, "name": "you all vibe ✨"},
    
    # Playing games activities
    {"type": discord.ActivityType.playing, "name": "games with the crew 🎮"},
    {"type": discord.ActivityType.playing, "name": "hide and seek 🕵️"},
    {"type": discord.ActivityType.playing, "name": "with server stats 📊"},
    {"type": discord.ActivityType.playing, "name": "GKR Championship 🏆"},
    {"type": discord.ActivityType.playing, "name": "mind games 🧠"},
    
    # Chilling activities
    {"type": discord.ActivityType.listening, "name": "chill vibes 🎵"},
    {"type": discord.ActivityType.listening, "name": "to the community 💬"},
    {"type": discord.ActivityType.listening, "name": "GKR stories 📚"},
    {"type": discord.ActivityType.custom, "name": "😎 Chilling with GKR"},
    {"type": discord.ActivityType.custom, "name": "🌟 Vibing in the server"},
    {"type": discord.ActivityType.custom, "name": "💯 Living the GKR life"},
    {"type": discord.ActivityType.custom, "name": "🚀 Keeping it cool"},
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

@bot.event
async def on_member_join(member):
    """Handle when a member joins the server"""
    guild = member.guild
    
    # Check if this is the correct guild
    if guild.id != GUILD_ID:
        return
    
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
    """Rotate bot activities with cool and dynamic descriptions"""
    guild = bot.get_guild(GUILD_ID)
    
    if guild:
        # Create dynamic activities list
        current_activities = []
        
        for activity_data in base_activities:
            name = activity_data["name"]
            
            # Replace placeholders with actual data
            if "{member_count}" in name:
                name = name.replace("{member_count}", str(guild.member_count))
            
            # Create the activity object
            if activity_data["type"] == discord.ActivityType.custom:
                activity = discord.CustomActivity(name=name)
            else:
                activity = discord.Activity(type=activity_data["type"], name=name)
            
            current_activities.append(activity)
        
        # Add some special dynamic activities based on current stats
        bot_role = guild.get_role(BOT_ROLE_ID)
        member_role = guild.get_role(MEMBER_ROLE_ID)
        
        if bot_role and bot.intents.members:
            bot_role_count = len(bot_role.members)
            if bot_role_count > 0:
                current_activities.extend([
                    discord.Activity(type=discord.ActivityType.watching, name=f"{bot_role_count} members with {bot_role.name} role 👑"),
                    discord.Activity(type=discord.ActivityType.custom, name=f"🎯 Managing {bot_role_count} GKR members"),
                ])
        
        if member_role and bot.intents.members:
            member_role_count = len(member_role.members)
            if member_role_count > 0:
                current_activities.extend([
                    discord.Activity(type=discord.ActivityType.watching, name=f"{member_role_count} members with {member_role.name} role 👥"),
                    discord.Activity(type=discord.ActivityType.watching, name=f"both roles: {bot_role_count if bot_role else 0} + {member_role_count} members 🔥"),
                ])
        
        # Add time-based activities
        import datetime
        hour = datetime.datetime.now().hour
        
        if 6 <= hour < 12:
            current_activities.append(discord.Activity(type=discord.ActivityType.custom, name="🌅 Good morning GKR!"))
        elif 12 <= hour < 18:
            current_activities.append(discord.Activity(type=discord.ActivityType.custom, name="☀️ Afternoon vibes"))
        elif 18 <= hour < 22:
            current_activities.append(discord.Activity(type=discord.ActivityType.custom, name="🌆 Evening chill"))
        else:
            current_activities.append(discord.Activity(type=discord.ActivityType.custom, name="🌙 Night owl mode"))
        
        # Choose a random activity
        activity = random.choice(current_activities)
        
        await bot.change_presence(activity=activity)
        
        # Cool logging with emojis (reduced frequency to avoid spam)
        activity_name = activity.name if hasattr(activity, 'name') else str(activity)
        if random.randint(1, 12) == 1:  # Only log every ~12th change to reduce console spam
            print(f"🔄 Activity changed to: {activity_name}")

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
        print("Starting Discord bot...")
        print("Make sure you have enabled the following privileged intents in Discord Developer Portal:")
        print("- Server Members Intent")
        print("- Message Content Intent")
        print("You can enable these at: https://discord.com/developers/applications/")
        print()
        
        # Start HTTP server in background thread for Render
        http_thread = Thread(target=start_http_server, daemon=True)
        http_thread.start()
        
        # Start Discord bot
        bot.run(TOKEN)
    except discord.PrivilegedIntentsRequired as e:
        print("\n❌ PRIVILEGED INTENTS ERROR:")
        print("You need to enable privileged intents in the Discord Developer Portal.")
        print("1. Go to https://discord.com/developers/applications/")
        print("2. Select your bot application")
        print("3. Go to the 'Bot' section")
        print("4. Enable 'Server Members Intent' and 'Message Content Intent'")
        print("5. Save changes and restart the bot")
        print(f"\nDetailed error: {e}")
    except discord.LoginFailure:
        print("\n❌ LOGIN ERROR:")
        print("Invalid bot token. Please check your DISCORD_TOKEN in the .env file.")
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        print("Please check your configuration and try again.")