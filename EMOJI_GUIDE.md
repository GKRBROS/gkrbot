# How to Set Up Custom Emojis for Your GKR Bot

This guide will help you upload custom emoji images to your Discord server and configure your bot to use them.

## Step 1: Upload Images as Custom Emojis

1. In Discord, go to your server where the bot will run
2. Click on the server name dropdown menu in the top left
3. Select "Server Settings"
4. Click on "Emoji" in the left sidebar
5. Click on the "Upload Emoji" button
6. Upload each of your images:
   - `valo.jpeg` (for Valorant)
   - `gta5.jpeg` (for GTA V)
   - `other.jpeg` (for Other Games)
7. Give each emoji a recognizable name (e.g., "valo", "gta5", "other")
8. Click "Save" to add the emojis to your server

## Step 2: Get the Emoji IDs

There are two ways to get emoji IDs:

### Method 1: Developer Mode
1. In Discord settings, enable "Developer Mode" under Advanced settings
2. Right-click on your custom emoji in chat and select "Copy ID"

### Method 2: Using a Backslash
1. Type `\` followed by the emoji name in Discord chat (e.g., `\:valo:`)
2. Send the message, and it will show the emoji in the format `<:emoji_name:emoji_id>`
3. Copy this format exactly

## Step 3: Update Your Bot's Configuration

1. Open your bot's code (`main.py`)
2. Find the `EMOJI_ROLE_MAP` section
3. Replace the placeholder emoji IDs with your actual emoji data:

```python
EMOJI_ROLE_MAP = {
    "<:valo:YOUR_EMOJI_ID_HERE>": int(os.getenv('VALORANT_ROLE_ID', '0')),    # Valorant
    "<:gta5:YOUR_EMOJI_ID_HERE>": int(os.getenv('GTA_ROLE_ID', '0')),         # GTA V
    "<:other:YOUR_EMOJI_ID_HERE>": int(os.getenv('OTHER_ROLE_ID', '0')),      # Other
}
```

## Example

If your emoji ID for "valo" is 987654321098765432, your code should look like:

```python
"<:valo:987654321098765432>": int(os.getenv('VALORANT_ROLE_ID', '0')),    # Valorant
```

## Important Notes

1. Make sure your bot is a member of the server with the custom emojis
2. The bot needs the "Use External Emojis" permission
3. If emojis are animated, use `<a:emoji_name:emoji_id>` format instead

Once you've updated the emoji IDs, run the `/reactionroles` command in your designated channel to create the reaction role message with your custom emojis!