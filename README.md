# GKR Discord Bot

A feature-rich Discord bot for managing server roles, nicknames, reaction roles, and guild font synchronization.

## 🚀 Features

- **Automatic Nickname Management**: Changes nicknames to "GKR" for members with a specific role
- **Dynamic Bot Status**: Continuously rotating activities showing member counts, games, and vibes
- **Reaction Roles**: Users can self-assign game roles by reacting to a message
- **Role Statistics**: Track and display member counts for each role
- **Font Sync**: Automatically applies a chosen Unicode font style to synced channel names across the server, selected categories, or selected channels

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

## 🎨 Font Sync Setup

Font Sync stores its configuration in a local SQLite database named `font_sync.sqlite3` in the bot directory.

1. Make sure the bot has `Manage Channels` permission
2. Run `/font-sync enable`
3. Choose a font style
4. Choose the sync scope:
   - Entire server
   - Specific categories
   - Specific channels
5. Save the configuration and the bot will resync matching channels immediately

The bot also listens for channel creates and channel updates so matching names stay synchronized automatically.

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

### Slash Commands (/)

| Command              | Description                                         | Permission      |
| -------------------- | --------------------------------------------------- | --------------- |
| `/reactionroles`     | Create the reaction roles message                   | Manage Roles    |
| `/font`              | Open the Font Sync settings panel                   | Manage Channels |
| `/sync-commands`     | Force a slash command resync for the current server | Manage Guild    |
| `/font-sync enable`  | Open the Font Sync settings panel                   | Manage Channels |
| `/font-sync disable` | Disable Font Sync for the server                    | Manage Channels |
| `/font-sync status`  | Show the current Font Sync configuration            | Manage Channels |
| `/font-sync font`    | Choose a Unicode font style                         | Manage Channels |
| `/font-sync scope`   | Choose the sync scope                               | Manage Channels |
| `/font-sync resync`  | Reapply the configured font to matching channels    | Manage Channels |

### Prefix Commands (!)

| Command                 | Description                                    | Permission       |
| ----------------------- | ---------------------------------------------- | ---------------- |
| `!setnick [member]`     | Set your own or another user's nickname to GKR | Manage Nicknames |
| `!setallnicks`          | Set all members with the specified role to GKR | Manage Nicknames |
| `!syncnicks`            | Manually sync nicknames for role members       | Manage Nicknames |
| `!checkrole`            | View statistics for configured roles           | None             |
| `!stats`                | Display server statistics                      | None             |
| `!rroles`               | Create reaction roles message (legacy command) | Manage Roles     |
| `!setrolemenugif [url]` | Set custom GIF for role menu                   | Manage Roles     |
| `!debugroles`           | Debug reaction roles setup                     | Manage Roles     |
| `!simpleroles`          | Create simple reaction roles message           | Manage Roles     |

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
