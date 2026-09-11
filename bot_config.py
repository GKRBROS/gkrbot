import os

# Single centralized source of truth for the bot name
BOT_NAME = (os.getenv("BOT_NAME") or "Bot").strip() or "Bot"
