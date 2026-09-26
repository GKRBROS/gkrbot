"""
devnews_api.py — "Dev News": a changelog feed for the marketing website.

    GET    /api/public/devnews         list published entries (newest first)
    POST   /api/admin/devnews          create an entry            (admin only)
    DELETE /api/admin/devnews/{id}     delete an entry             (admin only)

Managed entirely from the dashboard's Admin Panel — no direct database editing
needed. Storage: dev_news.sqlite3, next to this file (created automatically).

Wire-up (added to dashboard_api.py's cog_load, alongside the other route
registrations):

    from devnews_api import register_devnews_routes
    register_devnews_routes(app, get_user_id)
"""
import os
import re
import sqlite3
import time
from pathlib import Path

from aiohttp import web

DB_PATH = Path(__file__).resolve().parent / "dev_news.sqlite3"

MAX_TITLE = 100
MAX_BODY = 1000
MAX_ENTRIES_RETURNED = 50


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dev_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                media_url TEXT NOT NULL DEFAULT '',
                link_url TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.commit()


_init_db()


def _clean(value, limit: int) -> str:
    if value is None:
        return ""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value)).strip()
    return text[:limit]


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "media_url": row["media_url"],
        "link_url": row["link_url"],
        "created_at": row["created_at"],
    }


def _err(message: str, status: int = 400):
    return web.json_response({"error": message}, status=status)


async def handle_public_list(request: web.Request):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM dev_news ORDER BY created_at DESC LIMIT ?",
            (MAX_ENTRIES_RETURNED,),
        ).fetchall()
    return web.json_response({"entries": [_row_to_dict(r) for r in rows]})


def make_create_handler(is_admin_check):
    async def handle_create(request: web.Request):
        if not await is_admin_check(request):
            return _err("Forbidden", 403)
        try:
            data = await request.json()
        except Exception:
            return _err("Invalid request.")

        title = _clean((data or {}).get("title"), MAX_TITLE)
        body = _clean((data or {}).get("body"), MAX_BODY)
        media_url = _clean((data or {}).get("media_url"), 500)
        link_url = _clean((data or {}).get("link_url"), 500)

        if len(title) < 3:
            return _err("Please add a title (at least 3 characters).")
        if media_url and not media_url.startswith(("http://", "https://")):
            return _err("Image/GIF URL must be a direct http(s) link.")
        if link_url and not link_url.startswith(("http://", "https://")):
            return _err("Link URL must be a direct http(s) link.")

        with _connect() as conn:
            cur = conn.execute(
                "INSERT INTO dev_news (title, body, media_url, link_url, created_at) VALUES (?, ?, ?, ?, ?)",
                (title, body, media_url, link_url, int(time.time())),
            )
            conn.commit()
            new_id = cur.lastrowid

        print(f"[DevNews] Entry #{new_id} published: {title!r}")
        return web.json_response({"success": True, "id": new_id})

    return handle_create


def make_delete_handler(is_admin_check):
    async def handle_delete(request: web.Request):
        if not await is_admin_check(request):
            return _err("Forbidden", 403)
        entry_id = request.match_info.get("id", "")
        if not entry_id.isdigit():
            return _err("Invalid entry id.")
        with _connect() as conn:
            cur = conn.execute("DELETE FROM dev_news WHERE id = ?", (int(entry_id),))
            conn.commit()
        if cur.rowcount == 0:
            return _err("Entry not found.", 404)
        return web.json_response({"success": True})

    return handle_delete


def register_devnews_routes(app: web.Application, get_user_id) -> None:
    # Reuse the same admin check as admin_api.py so "who counts as admin" stays
    # in exactly one place.
    from admin_api import _is_admin

    async def is_admin_check(request: web.Request) -> bool:
        return await _is_admin(request, get_user_id)

    app.add_routes([
        web.get("/api/public/devnews", handle_public_list),
        web.post("/api/admin/devnews", make_create_handler(is_admin_check)),
        web.delete("/api/admin/devnews/{id}", make_delete_handler(is_admin_check)),
    ])
