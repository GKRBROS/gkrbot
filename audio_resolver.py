"""Authenticated lightweight audio resolver for GKR/other clients.

This is a custom Python HTTP API, NOT the Lavalink protocol. It returns short-lived
source URLs resolved by yt-dlp; clients should request /v1/resolve shortly before play.
"""
import asyncio
import os
import secrets
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()
API_PASSWORD = os.getenv("JADE_AUDIO_PASSWORD", "").strip()
if len(API_PASSWORD) < 24:
    API_PASSWORD = secrets.token_urlsafe(32)
    print(f"[AudioResolver] Generated temporary JADE_AUDIO_PASSWORD: {API_PASSWORD}")

HOST = os.getenv("JADE_AUDIO_HOST", "0.0.0.0")
PORT = int(os.getenv("JADE_AUDIO_PORT", "8088"))

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "format_sort": ["abr", "asr", "ext"],
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "skip_download": True,
    "source_address": "0.0.0.0",
    "extractor_retries": 2,
    "socket_timeout": 15,
}

def extract(query: str) -> dict[str, Any]:
    opts = dict(YTDL_OPTIONS)
    url = urlparse(query)
    target = query if url.scheme in ("http", "https") and url.netloc else f"ytsearch1:{query}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        data = ydl.extract_info(target, download=False)
    if data and data.get("entries"):
        data = next((entry for entry in data["entries"] if entry), None)
    if not data or not data.get("url"):
        raise ValueError("No playable audio result found.")
    return {
        "title": data.get("title") or "Unknown title",
        "webpage_url": data.get("webpage_url") or data.get("original_url") or query,
        "stream_url": data["url"],
        "duration": data.get("duration"),
        "artist": data.get("artist") or data.get("uploader") or "",
        "thumbnail": data.get("thumbnail"),
        "http_headers": data.get("http_headers") or {},
        "expires_note": "Stream URLs may expire; resolve again shortly before playback.",
    }

@web.middleware
async def auth_middleware(request, handler):
    if request.path == "/health":
        return await handler(request)
    supplied = request.headers.get("Authorization", "")
    if supplied.startswith("Bearer "):
        supplied = supplied[7:].strip()
    else:
        supplied = request.headers.get("X-Jade-Password", "")
    if not secrets.compare_digest(supplied, API_PASSWORD):
        raise web.HTTPUnauthorized(text="Invalid audio service credentials.")
    return await handler(request)

async def health(_request):
    return web.json_response({"ok": True, "service": "jade-audio-resolver", "protocol": "custom-http-v1"})

async def resolve(request):
    try:
        body = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Expected JSON body with a 'query' string.")
    query = str(body.get("query", "")).strip() if isinstance(body, dict) else ""
    if not query or len(query) > 2000:
        raise web.HTTPBadRequest(text="query is required and must be <= 2000 characters.")
    try:
        result = await asyncio.to_thread(extract, query)
        return web.json_response({"load_type": "track", "track": result})
    except Exception as exc:
        raise web.HTTPUnprocessableEntity(text=f"Could not resolve query: {str(exc)[:300]}")

app = web.Application(middlewares=[auth_middleware], client_max_size=64 * 1024)
app.router.add_get("/health", health)
app.router.add_post("/v1/resolve", resolve)

if __name__ == "__main__":
    print(f"Starting Jade Audio Resolver on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT)
