import sys
import subprocess

clients = [
    "default",
    "web",
    "android",
    "ios",
    "tv",
    "mweb",
    "android,ios",
    "tv,mweb"
]

for c in clients:
    print(f"\n--- Testing client: {c} ---")
    cmd = [
        sys.executable, "-m", "yt_dlp", 
        "--cookies", "cookies.txt",
        "--extractor-args", f"youtube:player_client={c}",
        "-F", "https://www.youtube.com/watch?v=WR8PyAhn6tQ"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        out = res.stdout + res.stderr
        
        if "Requested format is not available" in out or "Only images are available" in out or "Signature solving failed" in out:
            print(f"❌ Client {c} failed.")
        elif "ID  EXT   RESOLUTION" in out:
            print(f"✅ Client {c} WORKED! Formats available.")
            # print top 5 formats
            lines = [l for l in out.split('\n') if l.strip()]
            print('\n'.join(lines[-5:]))
        else:
            print(f"❓ Unknown result for {c}:\n" + out[:500])
    except Exception as e:
        print(f"Error: {e}")
