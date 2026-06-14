# import os
# import json
# import discord
# from discord.ext import commands
# import datetime
# from typing import Dict, Optional

# # FiveM player names storage
# FIVEM_NAMES_FILE = os.path.join(os.path.dirname(__file__), 'fivem_names.json')
# FIVEM_API_KEY = os.getenv('FIVEM_API_KEY', 'default_key_change_this')  # Add this to your .env file

# def load_fivem_names() -> Dict[str, str]:
#     """Load saved FiveM player names from JSON file"""
#     if os.path.exists(FIVEM_NAMES_FILE):
#         try:
#             with open(FIVEM_NAMES_FILE, 'r') as f:
#                 return json.load(f)
#         except Exception as e:
#             print(f"❌ Error loading FiveM names: {e}")
#     return {}  # Return empty dict if file doesn't exist or has an error

# def save_fivem_names(names_dict: Dict[str, str]) -> bool:
#     """Save FiveM player names to JSON file"""
#     try:
#         with open(FIVEM_NAMES_FILE, 'w') as f:
#             json.dump(names_dict, f, indent=2)
#         return True
#     except Exception as e:
#         print(f"❌ Error saving FiveM names: {e}")
#         return False

# class FiveM(commands.Cog):
#     def __init__(self, bot):
#         self.bot = bot
#         self.port = int(os.getenv('PORT', 8080))
    
#     @commands.command(name='fp')
#     async def set_fivem_player(self, ctx, *, fivem_name=None):
#         """Set your FiveM in-game player name
        
#         Args:
#             fivem_name: The name you use in FiveM. If not provided, shows your current name.
            
#         Example:
#             /fp John_Doe
#         """
#         # Check if we're in a server or DM
#         if not ctx.guild:
#             await ctx.send("❌ This command can only be used in a server.")
#             return
        
#         # Get current FiveM names
#         fivem_names = load_fivem_names()
#         user_id = str(ctx.author.id)
        
#         # If no name provided, show current name
#         if fivem_name is None:
#             if user_id in fivem_names:
#                 embed = discord.Embed(
#                     title="Your FiveM Player Name", 
#                     description=f"Your current FiveM name is set to: **{fivem_names[user_id]}**",
#                     color=0x00FF00
#                 )
#                 embed.set_footer(text="Use /fp [new name] to change it")
                
#                 # Add instruction on how this works with FiveM
#                 embed.add_field(
#                     name="How to use in FiveM", 
#                     value="This name will be used by FiveM servers that are connected to this Discord bot. "
#                           "Server admins can verify your identity using your Discord ID.",
#                     inline=False
#                 )
                
#                 # Add Discord ID for reference
#                 embed.add_field(
#                     name="Your Discord ID",
#                     value=f"`{user_id}`",
#                     inline=False
#                 )
                
#                 await ctx.send(embed=embed)
#             else:
#                 embed = discord.Embed(
#                     title="FiveM Player Name Not Set",
#                     description="❓ You don't have a FiveM name set yet. Use `/fp [your name]` to set one.",
#                     color=0xFFAA00
#                 )
                
#                 embed.add_field(
#                     name="What is this for?",
#                     value="Setting your FiveM name allows server admins to verify your identity between Discord and FiveM servers "
#                           "that are connected to this bot.",
#                     inline=False
#                 )
                
#                 await ctx.send(embed=embed)
#             return
        
#         # Check if name is valid (basic validation)
#         if len(fivem_name) < 3:
#             await ctx.send("❌ FiveM name must be at least 3 characters long.")
#             return
        
#         if len(fivem_name) > 32:
#             await ctx.send("❌ FiveM name must be less than 32 characters long.")
#             return
        
#         # Update the name in our dictionary
#         fivem_names[user_id] = fivem_name
        
#         # Save back to file
#         if save_fivem_names(fivem_names):
#             embed = discord.Embed(
#                 title="FiveM Name Updated",
#                 description=f"✅ Your FiveM player name has been set to:\n**{fivem_name}**",
#                 color=0x00FF00
#             )
            
#             # Add info about how this works
#             embed.add_field(
#                 name="How This Works",
#                 value="Your name is now stored in the bot's database. FiveM servers that are integrated "
#                       "with this bot can verify your identity using your Discord ID.",
#                 inline=False
#             )
            
#             # Add instruction for server owners
#             embed.add_field(
#                 name="For Server Owners",
#                 value="FiveM server owners can access the API to verify names at:\n"
#                       f"`http://your-bot-url:{self.port}/fivem/player/{user_id}`",
#                 inline=False
#             )
            
#             embed.set_footer(text="Note: This doesn't automatically change your name in FiveM")
#             await ctx.send(embed=embed)
#         else:
#             await ctx.send("❌ There was an error saving your FiveM name. Please try again later.")

#     @commands.command(name='getfp')
#     async def get_fivem_name(self, ctx, member: discord.Member = None):
#         """Look up someone's FiveM player name
        
#         Args:
#             member: The Discord member to look up. If not provided, shows your own name.
            
#         Example:
#             /getfp @username
#         """
#         if member is None:
#             member = ctx.author
        
#         # Get FiveM names
#         fivem_names = load_fivem_names()
#         user_id = str(member.id)
        
#         if user_id in fivem_names:
#             embed = discord.Embed(
#                 title="FiveM Player Name",
#                 description=f"{member.mention}'s FiveM name is: **{fivem_names[user_id]}**",
#                 color=0x00FF00
#             )
#             await ctx.send(embed=embed)
#         else:
#             await ctx.send(f"❓ {member.display_name} doesn't have a FiveM name set.")

#     @commands.command(name='fplist')
#     @commands.has_permissions(manage_messages=True)
#     async def fivem_list(self, ctx):
#         """List all registered FiveM player names (admin only)"""
#         fivem_names = load_fivem_names()
        
#         if not fivem_names:
#             await ctx.send("❓ No FiveM names have been registered yet.")
#             return
        
#         # Create a nice looking embed with all names
#         embed = discord.Embed(
#             title="Registered FiveM Player Names",
#             description="List of all members with registered FiveM names",
#             color=0x00AAFF
#         )
        
#         # Group entries into chunks to avoid hitting Discord's field limit
#         count = 0
#         entries = []
#         current_field = ""
        
#         # Process all entries
#         for user_id, name in fivem_names.items():
#             try:
#                 # Try to get member info
#                 member = ctx.guild.get_member(int(user_id))
#                 member_name = member.display_name if member else "Unknown User"
                
#                 entry = f"**{member_name}**: {name}\n"
#                 current_field += entry
                
#                 count += 1
#                 # Split into multiple fields after 10 entries
#                 if count % 10 == 0:
#                     entries.append(current_field)
#                     current_field = ""
#             except:
#                 # Skip entries that cause errors
#                 continue
        
#         # Add the last field if it has entries
#         if current_field:
#             entries.append(current_field)
        
#         # Add fields to embed
#         for i, field_content in enumerate(entries):
#             embed.add_field(
#                 name=f"Players {i*10+1}-{i*10+10}" if len(entries) > 1 else "Players",
#                 value=field_content,
#                 inline=False
#             )
        
#         # Add total count in footer
#         embed.set_footer(text=f"Total registered players: {count}")
        
#         await ctx.send(embed=embed)

#     @commands.command(name='clearfp')
#     @commands.has_permissions(administrator=True)
#     async def clear_fivem_name(self, ctx, member: discord.Member):
#         """Clear someone's FiveM player name (admin only)
        
#         Args:
#             member: The Discord member whose FiveM name should be cleared
            
#         Example:
#             /clearfp @username
#         """
#         fivem_names = load_fivem_names()
#         user_id = str(member.id)
        
#         if user_id in fivem_names:
#             old_name = fivem_names[user_id]
#             del fivem_names[user_id]
            
#             if save_fivem_names(fivem_names):
#                 await ctx.send(f"✅ Cleared {member.mention}'s FiveM name (was: **{old_name}**).")
#             else:
#                 await ctx.send("❌ There was an error saving the FiveM names. Please try again later.")
#         else:
#             await ctx.send(f"❓ {member.display_name} doesn't have a FiveM name set.")

#     @commands.command(name='fpexport')
#     @commands.has_permissions(administrator=True)
#     async def fivem_export(self, ctx):
#         """Export FiveM player names in a format suitable for server integration (admin only)"""
#         fivem_names = load_fivem_names()
        
#         if not fivem_names:
#             await ctx.send("❓ No FiveM names have been registered yet.")
#             return
        
#         # Create a nice looking embed with information
#         embed = discord.Embed(
#             title="FiveM Integration Guide",
#             description="Here's how to integrate this Discord bot with your FiveM server",
#             color=0x00AAFF
#         )
        
#         # Add API information
#         embed.add_field(
#             name="API Endpoint - Single Player",
#             value=f"GET `http://your-bot-url:{self.port}/fivem/player/DISCORD_ID`\n"
#                   f"Example: `http://your-bot-url:{self.port}/fivem/player/123456789012345678`",
#             inline=False
#         )
        
#         embed.add_field(
#             name="API Endpoint - All Players",
#             value=f"GET `http://your-bot-url:{self.port}/fivem/players`\n"
#                   f"**Requires:** Header `Authorization: Bearer {FIVEM_API_KEY}`",
#             inline=False
#         )
        
#         embed.add_field(
#             name="Response Format",
#             value="```json\n"
#                   '{\n'
#                   '  "discord_id": "123456789012345678",\n'
#                   '  "fivem_name": "Player_Name",\n'
#                   '  "found": true\n'
#                   '}\n'
#                   "```",
#             inline=False
#         )
        
#         embed.add_field(
#             name="FiveM Script Example",
#             value="```lua\n"
#                   'local function GetPlayerDiscordName(discord_id)\n'
#                   '    local apiUrl = "http://your-bot-url:' + str(self.port) + '/fivem/player/" .. discord_id\n'
#                   '    PerformHttpRequest(apiUrl, function(statusCode, response, headers)\n'
#                   '        if statusCode == 200 then\n'
#                   '            local data = json.decode(response)\n'
#                   '            print("Player Discord name: " .. data.fivem_name)\n'
#                   '            -- Use data.fivem_name here\n'
#                   '        else\n'
#                   '            print("Player not found or error")\n'
#                   '        end\n'
#                   '    end, "GET")\n'
#                   'end\n'
#                   "```",
#             inline=False
#         )
        
#         embed.add_field(
#             name="Verifying Players",
#             value="Use the Discord API to get a player's Discord ID from their FiveM identity, "
#                   "then use the above endpoint to verify their registered name.",
#             inline=False
#         )
        
#         # Add note about API key
#         embed.add_field(
#             name="⚠️ Security Note",
#             value=f"The API key used to access all players is `{FIVEM_API_KEY}`. "
#                   f"Set this in your .env file using `FIVEM_API_KEY=your_secure_key_here`",
#             inline=False
#         )
        
#         embed.set_footer(text=f"Total registered players: {len(fivem_names)}")
        
#         # Send export instructions via DM to avoid leaking to public
#         try:
#             await ctx.author.send(embed=embed)
#             await ctx.send("✅ FiveM integration guide has been sent to your DMs!")
#         except discord.Forbidden:
#             await ctx.send("❌ I couldn't send you a DM. Please enable DMs from server members.")
#             await ctx.send(embed=embed)

#     @commands.command(name='fphelp')
#     async def fivem_help(self, ctx):
#         """Shows help on how the FiveM name integration works"""
#         embed = discord.Embed(
#             title="FiveM Name Integration - How It Works",
#             description="Understanding how the Discord FiveM name system works",
#             color=0x4B0082  # Indigo
#         )
        
#         # Add explanations
#         embed.add_field(
#             name="What this does",
#             value="This bot stores your preferred FiveM name and links it to your Discord ID. "
#                   "FiveM servers that are connected to this bot can look up your registered name.",
#             inline=False
#         )
        
#         embed.add_field(
#             name="What this does NOT do",
#             value="• This does **NOT** automatically change your name in FiveM\n"
#                   "• FiveM names are set within the FiveM client itself\n"
#                   "• This is a verification system, not an automatic name changer",
#             inline=False
#         )
        
#         embed.add_field(
#             name="How to use it",
#             value="1. Set your name using `/fp YourFiveMName`\n"
#                   "2. Make sure your FiveM name matches what you registered\n"
#                   "3. Server admins can verify your identity",
#             inline=False
#         )
        
#         embed.add_field(
#             name="For server owners",
#             value="Server owners can use the bot's API to verify player identities. "
#                   "Admin can get integration details using the `/fpexport` command.",
#             inline=False
#         )
        
#         await ctx.send(embed=embed)

# def setup(bot):
#     bot.add_cog(FiveM(bot))
