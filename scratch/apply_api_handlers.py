HANDLERS_CODE = r'''

# ---------------------------------------------------------------------------
# Overview Handlers
# ---------------------------------------------------------------------------

async def handle_overview_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)

    # Server Info
    server_info = {
        "id": str(guild_id),
        "name": guild.name if guild else f"Guild {guild_id}",
        "icon": str(guild.icon.url) if (guild and guild.icon) else None,
        "member_count": guild.member_count if guild else 0,
        "channel_count": len(guild.channels) if guild else 0,
        "role_count": len(guild.roles) if guild else 0,
        "owner_id": str(guild.owner_id) if guild else None,
    }

    # Bot Info
    bot_info = {
        "name": BOT_NAME,
        "latency_ms": round(bot.latency * 1000, 1) if bot.latency else 0,
        "status": "online",
        "guilds_count": len(bot.guilds),
        "user_id": str(bot.user.id) if bot.user else None,
        "avatar": str(bot.user.avatar.url) if bot.user and bot.user.avatar else None,
    }

    # Feature Statuses
    features = {}

    # Welcome
    try:
        from welcome import WelcomeDatabase
        w_cfg = WelcomeDatabase().get_config(guild_id)
        features["welcome"] = bool(w_cfg and w_cfg.enabled)
    except Exception:
        features["welcome"] = False

    # Tickets
    try:
        from tickets import TicketDatabase
        t_db = TicketDatabase()
        cats = t_db.get_categories(guild_id)
        features["tickets"] = len(cats) > 0
        features["tickets_count"] = len(cats)
    except Exception:
        features["tickets"] = False
        features["tickets_count"] = 0

    # Stream Alerts
    try:
        from stream_alerts import StreamAlertDatabase
        alerts = StreamAlertDatabase().get_all_alerts(guild_id)
        features["stream_alerts"] = len(alerts) > 0
        features["stream_alerts_count"] = len(alerts)
    except Exception:
        features["stream_alerts"] = False
        features["stream_alerts_count"] = 0

    # Registration
    try:
        from registration import RegistrationDatabase
        forms = RegistrationDatabase().get_forms(guild_id)
        features["registration"] = len(forms) > 0
        features["registration_count"] = len(forms)
    except Exception:
        features["registration"] = False
        features["registration_count"] = 0

    # Security
    try:
        import security
        s_db = security.SecurityDatabase()
        with s_db._conn() as conn:
            row = conn.execute("SELECT anti_spam_enabled FROM security_config WHERE guild_id = ?", (str(guild_id),)).fetchone()
            features["security"] = bool(row and row["anti_spam_enabled"])
    except Exception:
        features["security"] = False

    # Giveaways
    try:
        import giveaways
        g_db = giveaways.GiveawayDatabase()
        active_gw = g_db.get_active(guild_id)
        features["giveaways"] = len(active_gw) > 0
        features["active_giveaways_count"] = len(active_gw)
    except Exception:
        features["giveaways"] = False
        features["active_giveaways_count"] = 0

    # Polls
    try:
        import poll
        with poll._db() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM polls WHERE guild_id = ? AND ended = 0", (guild_id,)).fetchone()
            cnt = row["cnt"] if row else 0
            features["polls"] = cnt > 0
            features["active_polls_count"] = cnt
    except Exception:
        features["polls"] = False
        features["active_polls_count"] = 0

    # Self Roles
    try:
        import self_roles
        sr_db = self_roles.SelfRolesDB()
        with sr_db._conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM role_menus WHERE guild_id = ?", (str(guild_id),)).fetchone()
            cnt = row["cnt"] if row else 0
            features["self_roles"] = cnt > 0
            features["self_roles_count"] = cnt
    except Exception:
        features["self_roles"] = False
        features["self_roles_count"] = 0

    # Birthdays
    try:
        import birthdays
        b_db = birthdays.BirthdayDatabase()
        with b_db._conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM birthdays WHERE guild_id = ?", (guild_id,)).fetchone()
            cnt = row["cnt"] if row else 0
            features["birthdays"] = cnt > 0
            features["birthdays_count"] = cnt
    except Exception:
        features["birthdays"] = False
        features["birthdays_count"] = 0

    # AI System
    try:
        from ai_system import AISystemDB
        ai_cfg = AISystemDB().get_config(guild_id)
        features["ai"] = bool(ai_cfg and ai_cfg.get("enabled", True))
    except Exception:
        features["ai"] = False

    # Radio 24/7
    try:
        from radio import RadioCog
        radio_cog = bot.get_cog("RadioCog")
        vc = guild.voice_client if guild else None
        features["radio"] = bool(vc and vc.is_connected())
    except Exception:
        features["radio"] = False

    return web.json_response({
        "guild": server_info,
        "bot": bot_info,
        "features": features,
    })


# ---------------------------------------------------------------------------
# Tickets Stats, List, Hub
# ---------------------------------------------------------------------------

async def handle_tickets_stats_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import tickets
    db = tickets.TicketDatabase()
    cats = db.get_categories(guild_id)
    total_tickets = sum(c.ticket_counter for c in cats)
    with db._conn() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM active_tickets WHERE guild_id = ?", (str(guild_id),)).fetchone()
        open_tickets = row["cnt"] if row else 0
    closed_tickets = max(0, total_tickets - open_tickets)
    hubs = db.get_hubs_by_guild(guild_id)
    return web.json_response({
        "categories_count": len(cats),
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "closed_tickets": closed_tickets,
        "hubs_count": len(hubs),
    })

async def handle_tickets_list_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    import tickets
    db = tickets.TicketDatabase()
    cats = {c.id: c for c in db.get_categories(guild_id)}
    
    ticket_list = []
    with db._conn() as conn:
        rows = conn.execute("SELECT * FROM active_tickets WHERE guild_id = ?", (str(guild_id),)).fetchall()
        for r in rows:
            cat = cats.get(r["category_id"])
            channel_id = int(r["channel_id"])
            ch = guild.get_channel(channel_id) if guild else None
            owner_id = int(r["owner_id"])
            owner = guild.get_member(owner_id) if guild else None
            ticket_list.append({
                "channel_id": str(channel_id),
                "channel_name": ch.name if ch else f"ticket-{r['ticket_number']}",
                "category_id": r["category_id"],
                "category_name": cat.name if cat else "General Support",
                "owner_id": str(owner_id),
                "owner_name": owner.display_name if owner else f"User {owner_id}",
                "ticket_number": r["ticket_number"],
                "status": "open",
            })
    return web.json_response({"tickets": ticket_list})

async def handle_tickets_hub_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    if not guild: return web.json_response({"error": "Guild not found"}, status=404)

    data = await request.json()
    channel_id = data.get("channel_id")
    if not channel_id:
        return web.json_response({"error": "Target channel is required"}, status=400)
    channel = guild.get_channel(int(channel_id))
    if not channel or not isinstance(channel, discord.TextChannel):
        return web.json_response({"error": "Invalid text channel"}, status=400)

    category_ids = data.get("category_ids", [])
    if not category_ids:
        return web.json_response({"error": "At least one category is required for a hub"}, status=400)

    import tickets
    db = tickets.TicketDatabase()
    all_cats = {c.id: c for c in db.get_categories(guild_id)}
    selected_cats = [all_cats[int(cid)] for cid in category_ids if int(cid) in all_cats]
    if not selected_cats:
        return web.json_response({"error": "No valid categories selected"}, status=400)

    title = data.get("title", "🎫 Support Tickets Hub").strip()
    description = data.get("description", "Please click the button below corresponding to your inquiry to create a private support ticket.").strip()
    color_hex = str(data.get("embed_color", "5865F2")).replace("#", "").replace("0x", "")
    try:
        color = int(color_hex, 16)
    except Exception:
        color = 0x5865F2

    embed = discord.Embed(title=title, description=description, color=color)
    if data.get("footer"):
        embed.set_footer(text=data["footer"])
    if data.get("image_url"):
        embed.set_image(url=data["image_url"])

    view = tickets.TicketHubView(selected_cats)
    try:
        msg = await channel.send(embed=embed, view=view)
        db.add_hub(msg.id, channel.id, guild.id, [c.id for c in selected_cats])
        return web.json_response({"success": True, "message_id": str(msg.id)})
    except Exception as e:
        return web.json_response({"error": f"Failed to post ticket hub: {e}"}, status=500)


# ---------------------------------------------------------------------------
# Giveaways Endpoints
# ---------------------------------------------------------------------------

async def handle_giveaways_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import giveaways
    db = giveaways.GiveawayDatabase()
    db.initialize()
    with db._conn() as conn:
        rows = conn.execute("SELECT * FROM giveaways WHERE guild_id = ? ORDER BY id DESC LIMIT 50", (str(guild_id),)).fetchall()
        result = []
        for r in rows:
            entry_row = conn.execute("SELECT COUNT(*) as count FROM giveaway_entries WHERE giveaway_id = ?", (r["id"],)).fetchone()
            entry_count = entry_row["count"] if entry_row else 0
            result.append({
                "id": r["id"],
                "channel_id": str(r["channel_id"]),
                "message_id": str(r["message_id"]) if r["message_id"] else None,
                "prize": r["prize"],
                "winners": r["winners"],
                "host_id": str(r["host_id"]),
                "ends_at": r["ends_at"],
                "ended": bool(r["ended"]),
                "required_role_id": str(r["required_role_id"]) if r["required_role_id"] else None,
                "winner_ids": r["winner_ids"].split(",") if r["winner_ids"] else [],
                "entries_count": entry_count,
            })
    return web.json_response({"giveaways": result})

async def handle_giveaways_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    if not guild: return web.json_response({"error": "Guild not found"}, status=404)

    data = await request.json()
    prize = data.get("prize", "").strip()
    channel_id = data.get("channel_id")
    if not prize or not channel_id:
        return web.json_response({"error": "Prize and Channel are required"}, status=400)

    channel = guild.get_channel(int(channel_id))
    if not channel or not isinstance(channel, discord.TextChannel):
        return web.json_response({"error": "Invalid text channel"}, status=400)

    winners = max(1, min(20, int(data.get("winners", 1))))
    duration_minutes = max(1, int(data.get("duration_minutes", 60)))
    ends_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=duration_minutes)

    required_role_id = data.get("required_role_id")
    host_id = sess.get("user_id") or str(guild.owner_id)

    import giveaways
    cog = bot.get_cog("GiveawayCog")
    db = giveaways.GiveawayDatabase()
    db.initialize()
    gw_id = db.create(
        guild_id, int(channel_id), int(host_id), prize, winners, ends_at,
        int(required_role_id) if required_role_id else None, 0
    )
    gw = db.get(gw_id)

    if cog:
        embed = cog.build_embed(gw, 0)
        view = giveaways.GiveawayView(cog, gw_id)
    else:
        embed = discord.Embed(
            title=f"🎉 GIVEAWAY: {prize} 🎉",
            description=f"Click the button below to enter!\n**Winners:** {winners}\n**Ends:** <t:{int(ends_at.timestamp())}:R>",
            color=0x5865F2
        )
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="Enter Giveaway", emoji="🎉", style=discord.ButtonStyle.primary, custom_id=f"gw_enter_{gw_id}"))

    try:
        msg = await channel.send(embed=embed, view=view)
        db.update_message_id(gw_id, msg.id)
        return web.json_response({"success": True, "id": gw_id, "message_id": str(msg.id)})
    except Exception as e:
        return web.json_response({"error": f"Failed to post giveaway: {e}"}, status=500)

async def handle_giveaway_end_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    giveaway_id = int(request.match_info["giveaway_id"])
    bot: commands.Bot = request.app["bot"]
    cog = bot.get_cog("GiveawayCog")
    if not cog:
        return web.json_response({"error": "Giveaway module not loaded"}, status=500)
    gw = cog.db.get(giveaway_id)
    if not gw:
        return web.json_response({"error": "Giveaway not found"}, status=404)
    if gw["ended"]:
        return web.json_response({"error": "Giveaway already ended"}, status=400)
    try:
        await cog.conclude_giveaway(gw)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": f"Failed to end giveaway: {e}"}, status=500)

async def handle_giveaway_reroll_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    giveaway_id = int(request.match_info["giveaway_id"])
    import giveaways, random
    db = giveaways.GiveawayDatabase()
    gw = db.get(giveaway_id)
    if not gw:
        return web.json_response({"error": "Giveaway not found"}, status=404)
    with db._conn() as conn:
        rows = conn.execute("SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?", (giveaway_id,)).fetchall()
        entries = [r["user_id"] for r in rows]
    if not entries:
        return web.json_response({"error": "No entries to reroll"}, status=400)
    winners = random.sample(entries, min(gw["winners"], len(entries)))
    with db._conn() as conn:
        conn.execute("UPDATE giveaways SET winner_ids = ? WHERE id = ?", (",".join(winners), giveaway_id))
        conn.commit()
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(int(gw["guild_id"]))
    if guild and gw.get("channel_id"):
        ch = guild.get_channel(int(gw["channel_id"]))
        if ch and isinstance(ch, discord.TextChannel):
            mentions = " ".join([f"<@{w}>" for w in winners])
            try:
                await ch.send(f"🎉 **Giveaway Reroll!** Congratulations to the new winner(s): {mentions}! You won **{gw['prize']}**!")
            except Exception:
                pass
    return web.json_response({"success": True, "winners": winners})


# ---------------------------------------------------------------------------
# Polls Endpoints
# ---------------------------------------------------------------------------

async def handle_polls_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import poll
    poll._init_db()
    with poll._db() as conn:
        rows = conn.execute("SELECT * FROM polls WHERE guild_id = ? ORDER BY message_id DESC LIMIT 50", (guild_id,)).fetchall()
        polls_list = []
        for r in rows:
            options = json.loads(r["options_json"])
            votes = json.loads(r["votes_json"])
            total_votes = len(votes)
            distribution = {opt: 0 for opt in options}
            for user_id, user_choice in votes.items():
                if isinstance(user_choice, list):
                    for c in user_choice:
                        if c in distribution: distribution[c] += 1
                elif user_choice in distribution:
                    distribution[user_choice] += 1

            polls_list.append({
                "message_id": str(r["message_id"]),
                "channel_id": str(r["channel_id"]),
                "question": r["question"],
                "options": options,
                "multi_choice": bool(r["multi_choice"]),
                "anonymous": bool(r["anonymous"]),
                "expires_at": r["expires_at"],
                "ended": bool(r["ended"]),
                "total_votes": total_votes,
                "distribution": distribution,
            })
    return web.json_response({"polls": polls_list})

async def handle_polls_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    if not guild: return web.json_response({"error": "Guild not found"}, status=404)

    data = await request.json()
    question = data.get("question", "").strip()
    channel_id = data.get("channel_id")
    options = [o.strip() for o in data.get("options", []) if o and o.strip()]
    if not question or not channel_id or len(options) < 2:
        return web.json_response({"error": "Question, channel, and at least 2 options are required"}, status=400)

    channel = guild.get_channel(int(channel_id))
    if not channel or not isinstance(channel, discord.TextChannel):
        return web.json_response({"error": "Invalid text channel"}, status=400)

    multi_choice = bool(data.get("multi_choice", False))
    anonymous = bool(data.get("anonymous", False))
    duration_mins = int(data.get("duration_minutes", 0))
    expires_at = (datetime.datetime.now(datetime.timezone.utc).timestamp() + (duration_mins * 60)) if duration_mins > 0 else None

    import poll
    poll_data = {
        "question": question,
        "options": options,
        "votes": {},
        "multi_choice": multi_choice,
        "anonymous": anonymous,
        "expires_at": expires_at,
        "author_id": int(sess.get("user_id", guild.owner_id)),
    }
    embed = poll.build_poll_embed(poll_data, is_closed=False)
    view = poll.PollVoteView(options, multi_choice, anonymous, poll_data["author_id"], expires_at)

    try:
        msg = await channel.send(embed=embed, view=view)
        poll.save_poll(
            msg.id, channel.id, guild_id, poll_data["author_id"],
            question, options, multi_choice, anonymous, expires_at
        )
        return web.json_response({"success": True, "message_id": str(msg.id)})
    except Exception as e:
        return web.json_response({"error": f"Failed to post poll: {e}"}, status=500)

async def handle_poll_close_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    message_id = int(request.match_info["message_id"])
    import poll
    poll.close_poll_in_db(message_id)
    p = poll.get_poll(message_id)
    if not p: return web.json_response({"error": "Poll not found"}, status=404)
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(p["guild_id"])
    if guild:
        ch = guild.get_channel(p["channel_id"])
        if ch and isinstance(ch, discord.TextChannel):
            try:
                msg = await ch.fetch_message(message_id)
                embed = poll.build_poll_embed(p, is_closed=True)
                await msg.edit(embed=embed, view=None)
            except Exception:
                pass
    return web.json_response({"success": True})


# ---------------------------------------------------------------------------
# Self Roles Endpoints
# ---------------------------------------------------------------------------

async def handle_self_roles_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import self_roles
    db = self_roles.SelfRolesDB()
    db.initialize()
    with db._conn() as conn:
        menus = conn.execute("SELECT * FROM role_menus WHERE guild_id = ?", (str(guild_id),)).fetchall()
        result = []
        for m in menus:
            opts = conn.execute("SELECT * FROM role_options WHERE message_id = ?", (m["message_id"],)).fetchall()
            result.append({
                "message_id": m["message_id"],
                "channel_id": m["channel_id"],
                "title": m["title"],
                "description": m["description"],
                "image_url": m["image_url"],
                "embed_color": m["embed_color"],
                "options": [
                    {"id": o["id"], "role_id": o["role_id"], "label": o["label"], "emoji": o["emoji"], "color": o["color"]}
                    for o in opts
                ]
            })
    return web.json_response({"menus": result})

async def handle_self_roles_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)
    if not guild: return web.json_response({"error": "Guild not found"}, status=404)

    data = await request.json()
    title = data.get("title", "Select Your Roles").strip()
    description = data.get("description", "Click the buttons or select options below to receive roles.").strip()
    channel_id = data.get("channel_id")
    options = data.get("options", [])
    if not channel_id or not options:
        return web.json_response({"error": "Channel and at least one role option are required"}, status=400)

    channel = guild.get_channel(int(channel_id))
    if not channel or not isinstance(channel, discord.TextChannel):
        return web.json_response({"error": "Invalid text channel"}, status=400)

    import self_roles
    db = self_roles.SelfRolesDB()
    db.initialize()

    embed_color = data.get("embed_color", "0x2b2d31")
    try:
        color_val = int(str(embed_color).replace("#", "").replace("0x", ""), 16)
    except Exception:
        color_val = 0x2b2d31

    embed = discord.Embed(title=title, description=description, color=color_val)
    if data.get("image_url"):
        embed.set_image(url=data["image_url"])

    view = self_roles.RoleMenuView(options)
    try:
        msg = await channel.send(embed=embed, view=view)
        db.create_menu(msg.id, channel.id, guild_id, title, description, data.get("image_url"), embed_color)
        for opt in options:
            db.add_role_option(msg.id, int(opt["role_id"]), opt.get("label"), opt.get("emoji"), opt.get("color", "primary"))
        return web.json_response({"success": True, "message_id": str(msg.id)})
    except Exception as e:
        return web.json_response({"error": f"Failed to publish self roles: {e}"}, status=500)

async def handle_self_roles_delete(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    message_id = request.match_info["message_id"]
    import self_roles
    db = self_roles.SelfRolesDB()
    db.delete_menu(int(message_id))
    return web.json_response({"success": True})


# ---------------------------------------------------------------------------
# Server Logs Endpoints
# ---------------------------------------------------------------------------

async def handle_server_logs_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import server_logs
    db = server_logs.LogsDB()
    db.initialize()
    cfg = db.get(guild_id)
    return web.json_response({
        "config": cfg,
        "categories": [
            {"key": c[0], "channel_name": c[1], "title": c[2], "desc": c[3]}
            for c in server_logs.CATEGORY_SPECS
        ],
        "all_events": server_logs.ALL_EVENTS,
        "event_categories": server_logs.EVENT_CATEGORIES,
    })

async def handle_server_logs_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    import server_logs
    db = server_logs.LogsDB()
    db.initialize()
    cfg = {
        "guild_id": guild_id,
        "log_channel_id": int(data["log_channel_id"]) if data.get("log_channel_id") else None,
        "enabled": bool(data.get("enabled", True)),
        "enabled_events": data.get("enabled_events", server_logs.ALL_EVENTS),
        "category_channels": data.get("category_channels", {}),
    }
    db.save(cfg)
    return web.json_response({"success": True})


# ---------------------------------------------------------------------------
# Birthdays Endpoints
# ---------------------------------------------------------------------------

async def handle_birthdays_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import birthdays
    db = birthdays.BirthdayDatabase()
    channel_id = db.get_channel(guild_id)
    b_list = db.get_birthdays_for_guild(guild_id)
    return web.json_response({
        "channel_id": str(channel_id) if channel_id else None,
        "birthdays": [
            {
                "user_id": str(b[0]),
                "username": b[1],
                "birth_day": b[2],
                "birth_month": b[3],
                "month_name": birthdays.MONTH_NAMES[b[3]] if 1 <= b[3] <= 12 else "",
            }
            for b in b_list
        ],
        "months": birthdays.MONTH_NAMES[1:],
    })

async def handle_birthdays_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    user_id = data.get("user_id")
    username = data.get("username", "Member").strip()
    day = int(data.get("birth_day", 1))
    month = int(data.get("birth_month", 1))
    if not user_id or day < 1 or day > 31 or month < 1 or month > 12:
        return web.json_response({"error": "Invalid birthday details"}, status=400)
    import birthdays
    db = birthdays.BirthdayDatabase()
    db.set_birthday(guild_id, int(user_id), username, day, month)
    return web.json_response({"success": True})

async def handle_birthdays_channel_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    channel_id = data.get("channel_id")
    import birthdays
    db = birthdays.BirthdayDatabase()
    if channel_id:
        db.set_channel(guild_id, int(channel_id))
    return web.json_response({"success": True})

async def handle_birthdays_delete(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    user_id = int(request.match_info["user_id"])
    import birthdays
    db = birthdays.BirthdayDatabase()
    db.remove_birthday(guild_id, user_id)
    return web.json_response({"success": True})


# ---------------------------------------------------------------------------
# Leaderboard (Voice, Economy, Invites)
# ---------------------------------------------------------------------------

async def handle_leaderboard_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    bot: commands.Bot = request.app["bot"]
    guild = bot.get_guild(guild_id)

    # Voice Leaderboard
    voice_leaders = []
    try:
        import voice_analytics
        db = voice_analytics.VoiceDatabase()
        db.initialize()
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT user_id, total_minutes, xp, coins, level FROM voice_stats WHERE guild_id = ? ORDER BY xp DESC LIMIT 20",
                (str(guild_id),)
            ).fetchall()
            for r in rows:
                uid = int(r["user_id"])
                m = guild.get_member(uid) if guild else None
                voice_leaders.append({
                    "user_id": str(uid),
                    "username": m.display_name if m else f"User {uid}",
                    "avatar": str(m.display_avatar.url) if m else None,
                    "total_minutes": r["total_minutes"],
                    "xp": r["xp"],
                    "coins": r["coins"],
                    "level": r["level"],
                })
    except Exception as e:
        print(f"[DashboardAPI] Voice leaderboard error: {e}")

    # Economy Leaderboard
    economy_leaders = []
    try:
        import economy
        e_db = economy.EconomyDatabase()
        e_db.initialize()
        with e_db._conn() as conn:
            rows = conn.execute(
                "SELECT user_id, wallet, bank, (wallet + bank) as total FROM balances WHERE guild_id = ? ORDER BY total DESC LIMIT 20",
                (str(guild_id),)
            ).fetchall()
            for r in rows:
                uid = int(r["user_id"])
                m = guild.get_member(uid) if guild else None
                economy_leaders.append({
                    "user_id": str(uid),
                    "username": m.display_name if m else f"User {uid}",
                    "avatar": str(m.display_avatar.url) if m else None,
                    "wallet": r["wallet"],
                    "bank": r["bank"],
                    "total": r["total"],
                })
    except Exception as e:
        print(f"[DashboardAPI] Economy leaderboard error: {e}")

    return web.json_response({
        "voice": voice_leaders,
        "economy": economy_leaders,
    })


# ---------------------------------------------------------------------------
# Community (Verification & Suggestions)
# ---------------------------------------------------------------------------

async def handle_community_get(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    import community
    db = community.CommunityDatabase()
    db.initialize()
    v_cfg = db.get_verify_config(guild_id)
    with db._conn() as conn:
        rows = conn.execute("SELECT * FROM suggestions WHERE guild_id = ? ORDER BY id DESC LIMIT 50", (str(guild_id),)).fetchall()
        suggestions = [
            {
                "id": r["id"],
                "channel_id": str(r["channel_id"]),
                "author_id": str(r["author_id"]),
                "content": r["content"],
                "status": r["status"],
                "staff_note": r["staff_note"],
                "upvotes": r["upvotes"],
                "downvotes": r["downvotes"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    return web.json_response({
        "verify_config": v_cfg,
        "suggestions": suggestions,
    })

async def handle_community_verify_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    import community
    db = community.CommunityDatabase()
    db.initialize()
    db.set_verify_config(
        guild_id,
        verified_role_id=str(data["verified_role_id"]) if data.get("verified_role_id") else None,
        log_channel_id=str(data["log_channel_id"]) if data.get("log_channel_id") else None,
        min_account_days=int(data.get("min_account_days", 0)),
    )
    return web.json_response({"success": True})

async def handle_community_suggestion_status_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    suggestion_id = int(request.match_info["id"])
    data = await request.json()
    status = data.get("status", "pending")
    staff_note = data.get("staff_note", "")
    import community
    db = community.CommunityDatabase()
    db.initialize()
    with db._conn() as conn:
        conn.execute("UPDATE suggestions SET status = ?, staff_note = ? WHERE id = ?", (status, staff_note, suggestion_id))
        conn.commit()
    return web.json_response({"success": True})


# ---------------------------------------------------------------------------
# Economy Balance Adjustment
# ---------------------------------------------------------------------------

async def handle_economy_balance_post(request: web.Request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Unauthorized"}, status=401)
    guild_id = int(request.match_info["guild_id"])
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        return web.json_response({"error": "User ID is required"}, status=400)
    action = data.get("action", "add")
    target = data.get("target", "wallet")
    amount = int(data.get("amount", 0))

    import economy
    db = economy.EconomyDatabase()
    db.initialize()
    bal = db.get_balance(guild_id, int(user_id))
    cur_wallet = bal["wallet"]
    cur_bank = bal["bank"]

    if target == "wallet":
        if action == "add": new_wallet = cur_wallet + amount
        elif action == "remove": new_wallet = max(0, cur_wallet - amount)
        else: new_wallet = max(0, amount)
        new_bank = cur_bank
    else:
        if action == "add": new_bank = cur_bank + amount
        elif action == "remove": new_bank = max(0, cur_bank - amount)
        else: new_bank = max(0, amount)
        new_wallet = cur_wallet

    db.set_balance(guild_id, int(user_id), new_wallet, new_bank)
    return web.json_response({"success": True, "wallet": new_wallet, "bank": new_bank})
'''

ROUTES_CODE = r'''            # Overview
            web.get("/api/guilds/{guild_id}/overview", handle_overview_get),

            # Tickets Extensions (Stats, List, Hub)
            web.get("/api/guilds/{guild_id}/tickets/stats", handle_tickets_stats_get),
            web.get("/api/guilds/{guild_id}/tickets/list", handle_tickets_list_get),
            web.post("/api/guilds/{guild_id}/tickets/hub", handle_tickets_hub_post),

            # Giveaways
            web.get("/api/guilds/{guild_id}/giveaways", handle_giveaways_get),
            web.post("/api/guilds/{guild_id}/giveaways", handle_giveaways_post),
            web.post("/api/guilds/{guild_id}/giveaways/{giveaway_id}/end", handle_giveaway_end_post),
            web.post("/api/guilds/{guild_id}/giveaways/{giveaway_id}/reroll", handle_giveaway_reroll_post),

            # Polls
            web.get("/api/guilds/{guild_id}/polls", handle_polls_get),
            web.post("/api/guilds/{guild_id}/polls", handle_polls_post),
            web.post("/api/guilds/{guild_id}/polls/{message_id}/close", handle_poll_close_post),

            # Self Roles
            web.get("/api/guilds/{guild_id}/self-roles", handle_self_roles_get),
            web.post("/api/guilds/{guild_id}/self-roles", handle_self_roles_post),
            web.delete("/api/guilds/{guild_id}/self-roles/{message_id}", handle_self_roles_delete),

            # Server Logs
            web.get("/api/guilds/{guild_id}/server-logs", handle_server_logs_get),
            web.post("/api/guilds/{guild_id}/server-logs", handle_server_logs_post),

            # Birthdays
            web.get("/api/guilds/{guild_id}/birthdays", handle_birthdays_get),
            web.post("/api/guilds/{guild_id}/birthdays", handle_birthdays_post),
            web.post("/api/guilds/{guild_id}/birthdays/channel", handle_birthdays_channel_post),
            web.delete("/api/guilds/{guild_id}/birthdays/{user_id}", handle_birthdays_delete),

            # Leaderboard (Voice, Economy)
            web.get("/api/guilds/{guild_id}/leaderboard", handle_leaderboard_get),

            # Community (Verification & Suggestions)
            web.get("/api/guilds/{guild_id}/community", handle_community_get),
            web.post("/api/guilds/{guild_id}/community/verify", handle_community_verify_post),
            web.post("/api/guilds/{guild_id}/community/suggestions/{id}/status", handle_community_suggestion_status_post),

            # Economy Balance Adjust
            web.post("/api/guilds/{guild_id}/economy/balance", handle_economy_balance_post),
'''

import os, py_compile

target_path = os.path.join(os.path.dirname(__file__), "..", "dashboard_api.py")
with open(target_path, "r", encoding="utf-8") as f:
    orig = f.read()

anchor_handler = "class DashboardAPI(commands.Cog):"
if anchor_handler not in orig:
    raise RuntimeError("Anchor handler not found!")

anchor_routes = 'web.delete("/api/guilds/{guild_id}/registration/submissions/{sub_id}", handle_registration_submission_delete),'
if anchor_routes not in orig:
    raise RuntimeError("Anchor routes not found!")

new_content = orig.replace(anchor_handler, HANDLERS_CODE + "\n\n" + anchor_handler)
new_content = new_content.replace(anchor_routes, anchor_routes + "\n" + ROUTES_CODE)

with open(target_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Updated dashboard_api.py successfully! Verifying compilation...")
py_compile.compile(target_path, doraise=True)
print("✅ dashboard_api.py compiled without errors!")
