# GKR Discord Bot

A feature-rich Discord bot for managing server roles, nicknames, and reaction roles.

## 🚀 Features

- **Automatic Nickname Management**: Changes nicknames to "GKR" for members with a specific role
- **Dynamic Bot Status**: Continuously rotating activities showing member counts, games, and vibes
- **Reaction Roles**: Users can self-assign game roles by reacting to a message
- **Role Statistics**: Track and display member counts for each role

## 🔧 Setup Instructions

### Prerequisites

- Python 3.8 or higher
- Discord Bot Token
- Discord Server with admin permissions

### Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install discord.py python-dotenv
   ```
3. Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```
4. Edit the `.env` file with your Discord bot token and server IDs

### Configuration

In your `.env` file:
1. Set `DISCORD_TOKEN` to your bot token
2. Set `DISCORD_GUILD_ID` to your server ID
3. Set `BOT_ROLE_ID` to the role ID for nickname management
4. Set `memeber_role_id` to the role ID for member count watching
5. Set `REACTION_CHANNEL_ID` to the channel where you want reaction roles to appear
6. Set the game role IDs for each game

## 🎮 Reaction Roles Setup

1. Make sure `REACTION_CHANNEL_ID` is set in your `.env` file
2. Set up game role IDs for each emoji in your `.env` file
3. Ensure your bot has the following permissions:
   - Manage Roles
   - Manage Messages
   - Read Messages
   - Send Messages
   - Add Reactions
4. Run the bot and use the command `/reactionroles` in the designated channel
5. The bot will create a message with reactions for each game role

## 📋 Commands

| Command | Description | Permission |
|---------|-------------|------------|
| `/reactionroles` | Create the reaction roles message | Manage Roles |
| `/setnick` | Set your own or another user's nickname to GKR | Manage Nicknames |
| `/setallnicks` | Set all members with the specified role to GKR | Manage Nicknames |
| `/syncnicks` | Manually sync nicknames for role members | Manage Nicknames |
| `/checkrole` | View statistics for configured roles | None |
| `/stats` | Display server statistics | None |

## 🔒 Security

- Never share your `.env` file or bot token
- Configure appropriate permissions for the bot
- Ensure the bot's role is placed above any roles it should manage

## 🌟 Deployment on Render

This bot includes a simple HTTP server for deployment on Render:

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Set the build command: `pip install -r requirements.txt`
4. Set the start command: `python main.py`
5. Add all environment variables from your `.env` file
6. Deploy!
