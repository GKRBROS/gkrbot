import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.stdout.reconfigure(encoding='utf-8')

print("Testing imports with project root on sys.path...")
for mod in ['giveaways', 'poll', 'self_roles', 'server_logs', 'birthdays', 'voice_analytics', 'community', 'economy', 'tickets']:
    try:
        __import__(mod)
        print(f"✅ {mod} imported successfully")
    except Exception as e:
        print(f"❌ {mod}: {e}")
