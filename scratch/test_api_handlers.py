import os, sys, json, sqlite3
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding='utf-8')

import giveaways, poll, self_roles, server_logs, birthdays, voice_analytics, community, economy, tickets

print("All module databases and schemas verified.")
