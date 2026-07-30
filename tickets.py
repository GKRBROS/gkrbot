"""
tickets.py — Advanced per-server Ticket System.
Features customizable categories, ping roles, embed layouts matching user requests.
"""

import os
import sqlite3
import datetime
from dataclasses import dataclass
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands


DB_PATH = os.path.join(os.path.dirname(__file__), "tickets.sqlite3")

# ---------------------------------------------------------------------------
# Database Models
# ---------------------------------------------------------------------------

@dataclass
class TicketCategory:
    id: int
    guild_id: int
    name: str                   # e.g., "Event Application"
    button_label: str           # e.g., "Create Event Ticket"
    button_emoji: str           # e.g., "🎫"
    ping_roles: str             # comma-separated role IDs
    admin_roles: str            # roles that can close the ticket without pinging
    custom_buttons: str         # JSON map of custom buttons
    embed_title: str
    embed_description: str
    ticket_counter: int

@dataclass
class ActiveTicket:
    channel_id: int
    guild_id: int
    owner_id: int
    category_id: int
    ticket_number: int


class TicketDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    button_label TEXT NOT NULL,
                    button_emoji TEXT NOT NULL,
                    ping_roles TEXT NOT NULL DEFAULT '',
                    admin_roles TEXT NOT NULL DEFAULT '',
                    custom_buttons TEXT NOT NULL DEFAULT '{}',
                    embed_title TEXT NOT NULL,
                    embed_description TEXT NOT NULL DEFAULT '',
                    ticket_counter INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            # Migration logic for existing tables
            cursor = conn.execute("PRAGMA table_info(ticket_categories)")
            columns = [info["name"] for info in cursor.fetchall()]
            if "admin_roles" not in columns:
                conn.execute("ALTER TABLE ticket_categories ADD COLUMN admin_roles TEXT NOT NULL DEFAULT ''")
            if "custom_buttons" not in columns:
                conn.execute("ALTER TABLE ticket_categories ADD COLUMN custom_buttons TEXT NOT NULL DEFAULT '{}'")
                
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_panels (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    category_id INTEGER NOT NULL,
                    FOREIGN KEY(category_id) REFERENCES ticket_categories(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS active_tickets (
                    channel_id TEXT PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    category_id INTEGER NOT NULL,
                    ticket_number INTEGER NOT NULL,
                    FOREIGN KEY(category_id) REFERENCES ticket_categories(id) ON DELETE CASCADE
                )
            """)
            # Per-guild settings table (log channel, etc.)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_settings (
                    guild_id TEXT PRIMARY KEY,
                    log_channel_id TEXT
                )
            """)
            conn.commit()

    def add_category(self, guild_id: int, name: str, button_label: str, button_emoji: str, 
                     ping_roles: str, admin_roles: str, embed_title: str, embed_desc: str) -> int:
        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO ticket_categories 
                (guild_id, name, button_label, button_emoji, ping_roles, admin_roles, embed_title, embed_description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(guild_id), name, button_label, button_emoji, ping_roles, admin_roles, embed_title, embed_desc))
            conn.commit()
            return cur.lastrowid

    def update_category(self, guild_id: int, category_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        
        valid_keys = {"name", "button_label", "button_emoji", "ping_roles", "admin_roles", "embed_title", "embed_description"}
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in valid_keys:
                updates.append(f"{k} = ?")
                params.append(v)
                
        if not updates:
            return False
            
        params.extend([category_id, str(guild_id)])
        query = f"UPDATE ticket_categories SET {', '.join(updates)} WHERE id = ? AND guild_id = ?"
        
        with self._conn() as conn:
            cur = conn.execute(query, tuple(params))
            conn.commit()
            return cur.rowcount > 0

    def get_categories(self, guild_id: int) -> List[TicketCategory]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM ticket_categories WHERE guild_id = ?", (str(guild_id),)).fetchall()
        return [self._row_to_cat(r) for r in rows]
        
    def get_category(self, category_id: int) -> Optional[TicketCategory]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM ticket_categories WHERE id = ?", (category_id,)).fetchone()
        if row:
            return self._row_to_cat(row)
        return None

    def delete_category(self, guild_id: int, category_id: int) -> bool:
        with self._conn() as conn:
            # Also delete associated panels
            conn.execute("DELETE FROM ticket_panels WHERE guild_id = ? AND category_id = ?", (str(guild_id), category_id))
            cur = conn.execute("DELETE FROM ticket_categories WHERE id = ? AND guild_id = ?", (category_id, str(guild_id)))
            conn.commit()
            return cur.rowcount > 0

    def get_next_ticket_number(self, category_id: int) -> int:
        with self._conn() as conn:
            conn.execute("UPDATE ticket_categories SET ticket_counter = ticket_counter + 1 WHERE id = ?", (category_id,))
            row = conn.execute("SELECT ticket_counter FROM ticket_categories WHERE id = ?", (category_id,)).fetchone()
            conn.commit()
            return row["ticket_counter"]

    def add_panel(self, message_id: int, channel_id: int, guild_id: int, category_id: int) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO ticket_panels (message_id, channel_id, guild_id, category_id)
                VALUES (?, ?, ?, ?)
            """, (str(message_id), str(channel_id), str(guild_id), category_id))
            conn.commit()

    def get_panels_by_category(self, category_id: int) -> list:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM ticket_panels WHERE category_id = ?", (category_id,)).fetchall()

    def add_active_ticket(self, channel_id: int, guild_id: int, owner_id: int, category_id: int, ticket_number: int) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO active_tickets (channel_id, guild_id, owner_id, category_id, ticket_number)
                VALUES (?, ?, ?, ?, ?)
            """, (str(channel_id), str(guild_id), str(owner_id), category_id, ticket_number))
            conn.commit()
            
    def add_custom_button(self, category_id: int, label: str, response_text: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT custom_buttons FROM ticket_categories WHERE id = ?", (category_id,)).fetchone()
            if not row: return False
            import json
            btns = json.loads(row["custom_buttons"] or "{}")
            btns[label] = response_text
            conn.execute("UPDATE ticket_categories SET custom_buttons = ? WHERE id = ?", (json.dumps(btns), category_id))
            conn.commit()
            return True

    def get_active_ticket(self, channel_id: int) -> Optional[ActiveTicket]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM active_tickets WHERE channel_id = ?", (str(channel_id),)).fetchone()
        if row:
            return ActiveTicket(
                channel_id=int(row["channel_id"]),
                guild_id=int(row["guild_id"]),
                owner_id=int(row["owner_id"]),
                category_id=row["category_id"],
                ticket_number=row["ticket_number"]
            )
        return None

    def remove_active_ticket(self, channel_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM active_tickets WHERE channel_id = ?", (str(channel_id),))
            conn.commit()

    def set_log_channel(self, guild_id: int, channel_id: int) -> None:
        """Set or update the ticket log channel for a guild."""
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO ticket_settings (guild_id, log_channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET log_channel_id=excluded.log_channel_id
            """, (str(guild_id), str(channel_id)))
            conn.commit()

    def get_log_channel(self, guild_id: int) -> Optional[int]:
        """Get the ticket log channel ID for a guild, or None if not set."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT log_channel_id FROM ticket_settings WHERE guild_id = ?",
                (str(guild_id),)
            ).fetchone()
        if row and row["log_channel_id"]:
            return int(row["log_channel_id"])
        return None

    def _row_to_cat(self, row: sqlite3.Row) -> TicketCategory:
        return TicketCategory(
            id=row["id"],
            guild_id=int(row["guild_id"]),
            name=row["name"],
            button_label=row["button_label"],
            button_emoji=row["button_emoji"],
            ping_roles=row["ping_roles"],
            admin_roles=row.keys().count("admin_roles") and row["admin_roles"] or "",
            custom_buttons=row.keys().count("custom_buttons") and row["custom_buttons"] or "{}",
            embed_title=row["embed_title"],
            embed_description=row["embed_description"],
            ticket_counter=row["ticket_counter"]
        )

# ---------------------------------------------------------------------------
# UI Views (Persistent)
# ---------------------------------------------------------------------------

class TicketCreateModal(discord.ui.Modal, title="Create Ticket"):
    issue_category = discord.ui.TextInput(
        label="Issue Category / Topic",
        style=discord.TextStyle.short,
        placeholder="e.g. Account Help, Report Player, Bug...",
        required=True,
        max_length=50
    )
    issue_details = discord.ui.TextInput(
        label="Issue Details",
        style=discord.TextStyle.long,
        placeholder="Please describe your issue in detail...",
        required=True,
        max_length=1000
    )
    attachment_link = discord.ui.TextInput(
        label="Attachment Link (Optional)",
        style=discord.TextStyle.short,
        placeholder="Paste image/file link OR upload later",
        required=False,
        max_length=200
    )

    def __init__(self, category_id: int):
        super().__init__()
        self.category_id = category_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        db = TicketDatabase()
        category = db.get_category(self.category_id)
        if not category:
            await interaction.followup.send("❌ This ticket category no longer exists.", ephemeral=True)
            return

        category_channel = interaction.channel.category
        ticket_num = db.get_next_ticket_number(category.id)
        
        safe_name = category.name.lower().replace(' ', '-')
        channel_name = f"{safe_name}-{ticket_num}"

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        roles_to_ping = []
        if category.ping_roles:
            for rid in category.ping_roles.split(','):
                rid = rid.strip()
                if rid:
                    try:
                        role = interaction.guild.get_role(int(rid))
                        if role:
                            roles_to_ping.append(role)
                            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    except ValueError:
                        pass

        try:
            ticket_channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category_channel,
                overwrites=overwrites,
                topic=f"Ticket {ticket_num} for {interaction.user.id}"
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ I lack permissions to create channels here.", ephemeral=True)
            return

        db.add_active_ticket(ticket_channel.id, interaction.guild.id, interaction.user.id, category.id, ticket_num)

        ping_text = " ".join([r.mention for r in roles_to_ping])
        outside_content = f"{interaction.user.mention} Please be patient. Our staffs will reach your shortly. {ping_text}"

        embed = discord.Embed(
            title=category.embed_title or category.name,
            description=category.embed_description if category.embed_description else None,
            color=0x2b2d31
        )
        
        embed.add_field(name="Ticket Creater", value=interaction.user.mention, inline=True)
        embed.add_field(name="Ticket Creater ID", value=str(interaction.user.id), inline=True)
        embed.add_field(name="Ticket Number", value=str(ticket_num), inline=True)
        
        embed.add_field(name="Topic / Category", value=self.issue_category.value, inline=False)
        embed.add_field(name="Issue Details", value=self.issue_details.value, inline=False)
        if self.attachment_link.value:
            embed.add_field(name="Attachment Link", value=self.attachment_link.value, inline=False)
        else:
            embed.add_field(name="Attachments", value="*If you have images or files, please upload them to this channel now.*", inline=False)
        
        now = datetime.datetime.now(datetime.timezone.utc)
        time_str = f"{discord.utils.format_dt(now, 'F')}\n{discord.utils.format_dt(now, 'R')}"
        embed.add_field(name="Ticket Create Time", value=time_str, inline=False)

        control_view = TicketControlView(category)
        await ticket_channel.send(content=outside_content, embed=embed, view=control_view)

        await interaction.followup.send(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

class TicketPanelView(discord.ui.View):
    """The persistent view attached to a panel message, with dynamic buttons based on category."""
    def __init__(self, category_id: int, button_label: str, button_emoji: str):
        super().__init__(timeout=None)
        self.category_id = category_id
        
        btn = discord.ui.Button(
            label=button_label,
            emoji=button_emoji if button_emoji else None,
            style=discord.ButtonStyle.primary,
            custom_id=f"ticket_open_{category_id}"
        )
        btn.callback = self.open_ticket
        self.add_item(btn)

    async def open_ticket(self, interaction: discord.Interaction):
        # We must NOT defer the interaction because modals must be sent immediately
        await interaction.response.send_modal(TicketCreateModal(self.category_id))


class TicketControlView(discord.ui.View):
    """The persistent view inside a ticket."""
    def __init__(self, category: TicketCategory = None):
        super().__init__(timeout=None)
        self.category = category
        if category:
            self._build_buttons()
            
    def _build_buttons(self):
        btn_close = discord.ui.Button(label="Close Request", style=discord.ButtonStyle.danger, custom_id=f"ticket_close_{self.category.id}")
        btn_close.callback = self.close_request
        self.add_item(btn_close)
        
        btn_attach = discord.ui.Button(label="Attach Proof", style=discord.ButtonStyle.primary, custom_id=f"ticket_attach_{self.category.id}")
        btn_attach.callback = self.attach_proof
        self.add_item(btn_attach)
        
        import json
        custom_btns = json.loads(self.category.custom_buttons) if self.category.custom_buttons else {}
        for btn_label, response_text in custom_btns.items():
            cbtn = discord.ui.Button(label=btn_label, style=discord.ButtonStyle.secondary, custom_id=f"ticket_custom_{self.category.id}_{btn_label}")
            async def make_callback(rt=response_text):
                async def custom_callback(interaction: discord.Interaction):
                    await interaction.response.send_message(rt, ephemeral=True)
                return custom_callback
            
            # Python loop closure binding trick is needed for async callbacks in loops
            import asyncio
            cbtn.callback = asyncio.run_coroutine_threadsafe(make_callback(), asyncio.get_event_loop()).result() if asyncio.get_event_loop().is_running() else None
            # Actually, standard default param binding works:
            async def bind(i: discord.Interaction, r=response_text):
                await i.response.send_message(r, ephemeral=True)
            cbtn.callback = bind
            self.add_item(cbtn)

    async def close_request(self, interaction: discord.Interaction):
        db = TicketDatabase()
        active = db.get_active_ticket(interaction.channel.id)
        if not active:
            await interaction.response.send_message("❌ This doesn't seem to be an active ticket.", ephemeral=True)
            return
            
        cat = db.get_category(active.category_id)
        is_admin = False
        
        if interaction.user.guild_permissions.manage_channels:
            is_admin = True
            
        if cat and cat.admin_roles:
            admin_roles = [int(r.strip()) for r in cat.admin_roles.split(',') if r.strip()]
            if any(r.id in admin_roles for r in interaction.user.roles):
                is_admin = True
                
        if is_admin:
            await interaction.response.send_modal(TicketCloseModal())
        else:
            ping_text = ""
            if cat and cat.admin_roles:
                ping_text = " ".join([f"<@&{r.strip()}>" for r in cat.admin_roles.split(',') if r.strip()])
            if not ping_text:
                ping_text = "Admins"
            await interaction.response.send_message(f"🔔 {ping_text} The ticket creator {interaction.user.mention} has requested to close this ticket.", ephemeral=False)

    async def attach_proof(self, interaction: discord.Interaction):
        await interaction.response.send_message("Please upload your proof image or document as a normal message in this channel.", ephemeral=True)


class TicketCloseModal(discord.ui.Modal, title="Close Ticket"):
    reason = discord.ui.TextInput(
        label="Reason for closing",
        style=discord.TextStyle.long,
        placeholder="e.g., Issue resolved, Duplicate ticket...",
        required=True,
        max_length=500
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        channel = interaction.channel
        db = TicketDatabase()
        db.remove_active_ticket(channel.id)

        # Generate HTML transcript using chat_exporter
        transcript_file = None
        try:
            import chat_exporter
            import io
            
            # Export the channel to HTML string
            transcript = await chat_exporter.export(channel)
            if transcript:
                transcript_file = discord.File(
                    io.BytesIO(transcript.encode('utf-8')),
                    filename=f"transcript-{channel.name}.html"
                )
        except Exception as e:
            print(f"Failed to generate transcript: {e}")

        # Look up per-guild log channel from DB first, then fall back to env var
        import os
        db = TicketDatabase()
        log_channel_id = db.get_log_channel(interaction.guild.id)
        if not log_channel_id:
            env_val = os.getenv("TICKET_LOG_CHANNEL_ID")
            log_channel_id = int(env_val) if env_val else None
        
        # Scrape original ticket details from the first message
        topic_val = "Unknown"
        details_val = "Unknown"
        async for message in channel.history(limit=50, oldest_first=True):
            if message.embeds and message.author == interaction.client.user:
                first_embed = message.embeds[0]
                for field in first_embed.fields:
                    if field.name == "Topic / Category":
                        topic_val = field.value
                    elif field.name == "Issue Details":
                        details_val = field.value
                if topic_val != "Unknown":
                    break

        embed = discord.Embed(title="🎫 Ticket Closed", color=0xFF0000, timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.add_field(name="Closed By", value=f"{interaction.user.mention} ({interaction.user.id})", inline=True)
        embed.add_field(name="Channel", value=f"{channel.name}", inline=True)
        embed.add_field(name="Topic / Category", value=topic_val, inline=False)
        embed.add_field(name="Original Issue", value=details_val, inline=False)
        embed.add_field(name="Closing Reason", value=self.reason.value, inline=False)
        
        log_channel = None
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            
        if log_channel:
            await log_channel.send(embed=embed)
            if transcript_file:
                await log_channel.send("📄 **Ticket Transcript Attached:**", file=transcript_file)
        else:
            # Fallback to ServerLogsCog
            cog = interaction.client.get_cog("ServerLogsCog")
            if cog:
                import asyncio
                # Recreate file object if it was already read or if we need to pass it
                if transcript_file:
                    transcript_file.seek(0)
                    embed.description = "Transcript attached."
                    await cog.logger._send(interaction.guild, "channel_delete", embed)
                    # For safety, ServerLogsCog doesn't take files easily through _send, so just send directly to log channel if it exists
                    server_log_channel = cog.logger.db.get_channel(interaction.guild.id)
                    if server_log_channel:
                        log_ch = interaction.guild.get_channel(server_log_channel)
                        if log_ch:
                            await log_ch.send(file=transcript_file)
                else:
                    asyncio.create_task(cog.logger._send(interaction.guild, "channel_delete", embed))

        await channel.send(f"Ticket is closing in 5 seconds...\n**Reason:** {self.reason.value}")
        import asyncio
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user.display_name}: {self.reason.value}")
        except discord.Forbidden:
            pass


class TicketSetupConfigView(discord.ui.View):
    def __init__(self, bot: commands.Bot, db: TicketDatabase, category_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.category_id = category_id

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select Ping Roles (who to ping when opened)", min_values=0, max_values=10, row=0)
    async def select_ping_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role_ids = [str(r.id) for r in select.values]
        self.db.update_category(interaction.guild.id, self.category_id, ping_roles=",".join(role_ids))
        await interaction.response.send_message("✅ Ping roles updated.", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select Admin Roles (who can close tickets)", min_values=0, max_values=10, row=1)
    async def select_admin_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role_ids = [str(r.id) for r in select.values]
        self.db.update_category(interaction.guild.id, self.category_id, admin_roles=",".join(role_ids))
        await interaction.response.send_message("✅ Admin roles updated.", ephemeral=True)

    @discord.ui.button(label="Spawn Panel Here", style=discord.ButtonStyle.success, row=2)
    async def spawn_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        cat = self.db.get_category(self.category_id)
        if not cat:
            await interaction.response.send_message("❌ Category not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Open a Ticket: {cat.name}",
            description="Click the button below to open a ticket.",
            color=0x2b2d31
        )
        # Register view dynamically
        view = TicketPanelView(category_id=cat.id, button_label=cat.button_label, button_emoji=cat.button_emoji)
        self.bot.add_view(view)
        
        msg = await interaction.channel.send(embed=embed, view=view)
        self.db.add_panel(msg.id, interaction.channel.id, interaction.guild.id, cat.id)
        await interaction.response.send_message("✅ Panel spawned successfully!", ephemeral=True)


class TicketSetupModal(discord.ui.Modal, title="Create Ticket Category"):
    cat_name = discord.ui.TextInput(label="Category Name", placeholder="e.g. Support, Applications", required=True)
    btn_label = discord.ui.TextInput(label="Button Label", placeholder="e.g. Open Support Ticket", required=True)
    btn_emoji = discord.ui.TextInput(label="Button Emoji", placeholder="e.g. 🎫", required=False, default="🎫")
    emb_title = discord.ui.TextInput(label="Embed Title inside Ticket", placeholder="e.g. Welcome to Support", required=True)
    emb_desc = discord.ui.TextInput(label="Embed Description inside Ticket", style=discord.TextStyle.paragraph, placeholder="Describe your issue below.", required=False)

    def __init__(self, bot: commands.Bot, db: TicketDatabase):
        super().__init__()
        self.bot = bot
        self.db = db

    async def on_submit(self, interaction: discord.Interaction):
        # Create category with empty roles
        cat_id = self.db.add_category(
            interaction.guild.id,
            self.cat_name.value,
            self.btn_label.value,
            self.btn_emoji.value,
            "", "",  # empty ping and admin roles initially
            self.emb_title.value,
            self.emb_desc.value
        )
        
        # Add the control view to bot so buttons inside work
        cat = self.db.get_category(cat_id)
        self.bot.add_view(TicketControlView(cat))

        embed = discord.Embed(
            title="⚙️ Ticket Category Configured",
            description=f"Category **{self.cat_name.value}** created!\n\nNow, select the Ping Roles and Admin Roles below, then click **Spawn Panel Here** when you're ready.",
            color=0x3498DB
        )
        view = TicketSetupConfigView(self.bot, self.db, cat_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = TicketDatabase()
        self.db.initialize()

    async def cog_load(self):
        # We need to re-register all persistent panel views so buttons work after restart
        categories = self.db.get_all_categories_global()
        for cat in categories:
            self.bot.add_view(TicketPanelView(category_id=cat.id, button_label=cat.button_label, button_emoji=cat.button_emoji))
            self.bot.add_view(TicketControlView(cat))

    ticket_group = app_commands.Group(name="ticket", description="Ticket system commands")

    @ticket_group.command(name="setup", description="Start the interactive ticket setup UI")
    @app_commands.default_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketSetupModal(self.bot, self.db))

    @ticket_group.command(name="panel", description="Spawn a ticket creation panel here")
    @app_commands.describe(category_id="The ID of the category to spawn a panel for (use /ticket category_list)")
    @app_commands.default_permissions(manage_guild=True)
    async def spawn_panel(self, interaction: discord.Interaction, category_id: int):
        cat = self.db.get_category(category_id)
        if not cat or cat.guild_id != interaction.guild.id:
            await interaction.response.send_message("❌ Category not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Open a Ticket: {cat.name}",
            description="Click the button below to open a ticket.",
            color=0x2b2d31
        )
        view = TicketPanelView(category_id=cat.id, button_label=cat.button_label, button_emoji=cat.button_emoji)
        
        msg = await interaction.channel.send(embed=embed, view=view)
        self.db.add_panel(msg.id, interaction.channel.id, interaction.guild.id, cat.id)
        await interaction.response.send_message("✅ Panel created.", ephemeral=True)

    @ticket_group.command(name="button_add", description="Add a custom button to a ticket category")
    @app_commands.default_permissions(manage_guild=True)
    async def button_add(self, interaction: discord.Interaction, category_id: int, button_label: str, response_text: str):
        cat = self.db.get_category(category_id)
        if not cat or cat.guild_id != interaction.guild.id:
            await interaction.response.send_message("❌ Category not found.", ephemeral=True)
            return
            
        self.db.add_custom_button(category_id, button_label, response_text)
        self.bot.add_view(TicketControlView(self.db.get_category(category_id)))
        await interaction.response.send_message(f"✅ Custom button **{button_label}** added to category {cat.name}!", ephemeral=True)

    @ticket_group.command(name="user_add", description="Add a user to the current ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def user_add(self, interaction: discord.Interaction, user: discord.Member):
        active = self.db.get_active_ticket(interaction.channel.id)
        if not active:
            await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
            return
        await interaction.channel.set_permissions(user, read_messages=True, send_messages=True, attach_files=True)
        await interaction.response.send_message(f"✅ Added {user.mention} to the ticket.")

    @ticket_group.command(name="user_remove", description="Remove a user from the current ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def user_remove(self, interaction: discord.Interaction, user: discord.Member):
        active = self.db.get_active_ticket(interaction.channel.id)
        if not active:
            await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
            return
        await interaction.channel.set_permissions(user, read_messages=False, send_messages=False)
        await interaction.response.send_message(f"✅ Removed {user.mention} from the ticket.")

    @ticket_group.command(name="setlogchannel", description="Set the channel where closed ticket logs and transcripts are sent")
    @app_commands.describe(channel="The channel to send ticket logs and transcripts to")
    @app_commands.default_permissions(manage_guild=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.db.set_log_channel(interaction.guild.id, channel.id)
        embed = discord.Embed(
            title="✅ Ticket Log Channel Set",
            description=f"Closed ticket logs and HTML transcripts will now be sent to {channel.mention}.",
            color=0x00CC66
        )
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Channel ID", value=str(channel.id), inline=True)
        embed.set_footer(text="Use /ticket setlogchannel again to change it at any time.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Extended Database method needed
def get_all_categories_global(self):
    with self._conn() as conn:
        rows = conn.execute("SELECT * FROM ticket_categories").fetchall()
    return [self._row_to_cat(r) for r in rows]

TicketDatabase.get_all_categories_global = get_all_categories_global


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
    print("🎫 Ticket system loaded!")
