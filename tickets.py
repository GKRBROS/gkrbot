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
from gkr_ui import C, embed_error, embed_success, embed_info, embed_warning, embed_action  # noqa: E402


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
            
            # Hubs
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_hubs (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    category_ids TEXT NOT NULL
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

    def add_hub(self, message_id: int, channel_id: int, guild_id: int, category_ids: list[int]) -> None:
        import json
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO ticket_hubs (message_id, channel_id, guild_id, category_ids)
                VALUES (?, ?, ?, ?)
            """, (str(message_id), str(channel_id), str(guild_id), json.dumps(category_ids)))
            conn.commit()

    def get_all_hubs_global(self) -> list:
        import json
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM ticket_hubs").fetchall()
        
        results = []
        for row in rows:
            results.append({
                "message_id": int(row["message_id"]),
                "channel_id": int(row["channel_id"]),
                "category_ids": json.loads(row["category_ids"])
            })
        return results

    def get_hubs_by_guild(self, guild_id: int) -> list:
        import json
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM ticket_hubs WHERE guild_id = ?", (str(guild_id),)).fetchall()
        
        results = []
        for row in rows:
            results.append({
                "message_id": int(row["message_id"]),
                "channel_id": int(row["channel_id"]),
                "guild_id": int(row["guild_id"]),
                "category_ids": json.loads(row["category_ids"])
            })
        return results

    def remove_hub(self, message_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM ticket_hubs WHERE message_id = ?", (str(message_id),))
            conn.commit()

    def get_panels_by_guild(self, guild_id: int) -> list:
        with self._conn() as conn:
            return conn.execute("SELECT * FROM ticket_panels WHERE guild_id = ?", (str(guild_id),)).fetchall()

    def remove_panel(self, message_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM ticket_panels WHERE message_id = ?", (str(message_id),))
            conn.commit()

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
        keys = row.keys()
        return TicketCategory(
            id=row["id"],
            guild_id=int(row["guild_id"]),
            name=row["name"],
            button_label=row["button_label"],
            button_emoji=row["button_emoji"],
            ping_roles=row["ping_roles"] if "ping_roles" in keys else "",
            admin_roles=row["admin_roles"] if "admin_roles" in keys else "",
            custom_buttons=row["custom_buttons"] if "custom_buttons" in keys else "{}",
            embed_title=row["embed_title"],
            embed_description=row["embed_description"] if "embed_description" in keys else "",
            ticket_counter=row["ticket_counter"]
        )

    def get_all_categories_global(self) -> list:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM ticket_categories").fetchall()
        return [self._row_to_cat(r) for r in rows]

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
            await interaction.followup.send(embed=embed_error("This ticket category no longer exists."), ephemeral=True)
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
            await interaction.followup.send(embed=embed_error("I lack permissions to create channels here."), ephemeral=True)
            return

        db.add_active_ticket(ticket_channel.id, interaction.guild.id, interaction.user.id, category.id, ticket_num)

        ping_text = " ".join([r.mention for r in roles_to_ping])
        outside_content = f"{interaction.user.mention} Please be patient. Our staffs will reach your shortly. {ping_text}"

        embed = discord.Embed(
            title=category.embed_title or category.name,
            description=category.embed_description if category.embed_description else None,
            color=C.BRAND
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

        await interaction.followup.send(embed=embed_success("Ticket Created", f"Ticket created: {ticket_channel.mention}"), ephemeral=True)

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


class TicketHubView(discord.ui.View):
    """The persistent view attached to a hub message, with multiple category buttons."""
    def __init__(self, categories: list[TicketCategory]):
        super().__init__(timeout=None)
        self.categories = categories
        for cat in categories:
            btn = discord.ui.Button(
                label=cat.button_label,
                emoji=cat.button_emoji if cat.button_emoji else None,
                style=discord.ButtonStyle.secondary,
                custom_id=f"ticket_open_{cat.id}"
            )
            # Use default arg to capture cid at loop time (avoids late-binding closure bug)
            async def _callback(interaction: discord.Interaction, cid=cat.id):
                await interaction.response.send_modal(TicketCreateModal(cid))
            btn.callback = _callback
            self.add_item(btn)


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
            # Use default arg to capture response_text at loop time — avoids late-binding and asyncio deadlock
            async def _custom_callback(i: discord.Interaction, r=response_text):
                await i.response.send_message(r, ephemeral=True)
            cbtn.callback = _custom_callback
            self.add_item(cbtn)

    async def close_request(self, interaction: discord.Interaction):
        db = TicketDatabase()
        active = db.get_active_ticket(interaction.channel.id)
        if not active:
            await interaction.response.send_message(embed=embed_error("This doesn't seem to be an active ticket."), ephemeral=True)
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
        # Store raw bytes so we can create multiple discord.File objects from it
        transcript_bytes: bytes | None = None
        transcript_filename = f"transcript-{channel.name}.html"
        try:
            import chat_exporter
            transcript = await chat_exporter.export(channel)
            if transcript:
                transcript_bytes = transcript.encode('utf-8')
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

        embed = discord.Embed(title="🎫  Ticket Closed", color=C.DANGER, timestamp=datetime.datetime.now(datetime.timezone.utc))
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
            if transcript_bytes:
                import io
                # Create a fresh discord.File each time — do NOT reuse file objects
                await log_channel.send("📄 **Ticket Transcript Attached:**", file=discord.File(io.BytesIO(transcript_bytes), filename=transcript_filename))
        else:
            # Fallback: try ServerLogsCog's log channel
            cog = interaction.client.get_cog("ServerLogsCog")
            if cog:
                import asyncio
                asyncio.create_task(cog.logger._send(interaction.guild, "channel_delete", embed))
                if transcript_bytes:
                    import io
                    try:
                        server_log_channel_id = cog.logger.db.get_channel(interaction.guild.id)
                        if server_log_channel_id:
                            log_ch = interaction.guild.get_channel(server_log_channel_id)
                            if log_ch:
                                await log_ch.send("📄 **Ticket Transcript:**", file=discord.File(io.BytesIO(transcript_bytes), filename=transcript_filename))
                    except Exception as e:
                        print(f"[Tickets] Could not send transcript to server log: {e}")


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
        await interaction.response.send_message(embed=embed_success("Ping Roles Updated", "The ping roles have been saved."), ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select Admin Roles (who can close tickets)", min_values=0, max_values=10, row=1)
    async def select_admin_roles(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        role_ids = [str(r.id) for r in select.values]
        self.db.update_category(interaction.guild.id, self.category_id, admin_roles=",".join(role_ids))
        await interaction.response.send_message(embed=embed_success("Admin Roles Updated", "The admin roles have been saved."), ephemeral=True)

    @discord.ui.button(label="Spawn Basic Panel", style=discord.ButtonStyle.green, row=2)
    async def spawn_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        cat = self.db.get_category(self.category_id)
        if not cat:
            await interaction.response.send_message(embed=embed_error("Category not found."), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Open a Ticket: {cat.name}",
            description="Click the button below to open a ticket.",
            color=C.BRAND
        )
        # Register view dynamically
        view = TicketPanelView(category_id=cat.id, button_label=cat.button_label, button_emoji=cat.button_emoji)
        self.bot.add_view(view)
        
        msg = await interaction.channel.send(embed=embed, view=view)
        self.db.add_panel(msg.id, interaction.channel.id, interaction.guild.id, cat.id)
        await interaction.response.send_message(embed=embed_success("Panel Spawned", "Panel spawned successfully!"), ephemeral=True)


class TicketSetupModal(discord.ui.Modal):
    def __init__(self, bot: commands.Bot, db: TicketDatabase, category: TicketCategory = None):
        super().__init__(title="Edit Category" if category else "Create Ticket Category")
        self.bot = bot
        self.db = db
        self.category = category
        
        self.cat_name = discord.ui.TextInput(label="Category Name", placeholder="e.g. Support", required=True, default=category.name if category else "")
        self.btn_label = discord.ui.TextInput(label="Button Label", placeholder="e.g. Open Support Ticket", required=True, default=category.button_label if category else "")
        self.btn_emoji = discord.ui.TextInput(label="Button Emoji", placeholder="e.g. 🎫", required=False, default=category.button_emoji if category else "🎫")
        self.emb_title = discord.ui.TextInput(label="Embed Title inside Ticket", placeholder="e.g. Welcome to Support", required=True, default=category.embed_title if category else "")
        self.emb_desc = discord.ui.TextInput(label="Embed Description", style=discord.TextStyle.paragraph, placeholder="Describe your issue.", required=False, default=category.embed_description if category else "")
        
        self.add_item(self.cat_name)
        self.add_item(self.btn_label)
        self.add_item(self.btn_emoji)
        self.add_item(self.emb_title)
        self.add_item(self.emb_desc)

    async def on_submit(self, interaction: discord.Interaction):
        if self.category:
            self.db.update_category(
                interaction.guild.id, self.category.id,
                name=self.cat_name.value,
                button_label=self.btn_label.value,
                button_emoji=self.btn_emoji.value,
                embed_title=self.emb_title.value,
                embed_description=self.emb_desc.value
            )
            cat_id = self.category.id
            desc = f"Category **{self.cat_name.value}** updated!\n\n"
        else:
            cat_id = self.db.add_category(
                interaction.guild.id,
                self.cat_name.value,
                self.btn_label.value,
                self.btn_emoji.value,
                "", "",  # empty ping and admin roles initially
                self.emb_title.value,
                self.emb_desc.value
            )
            desc = f"Category **{self.cat_name.value}** created!\n\n"
            
        # Add the control view to bot so buttons inside work
        cat = self.db.get_category(cat_id)
        self.bot.add_view(TicketControlView(cat))

        embed = discord.Embed(
            title="⚙️  Ticket Category Configured",
            description=desc + 
                        f"**Next Steps:**\n"
                        f"1. Select the Ping Roles and Admin Roles below.\n"
                        f"2. To create a beautiful custom panel with your own text and banner image, click **Spawn Custom Panel** in the `/ticket setup` dashboard.\n"
                        f"3. Or, if you just want a simple basic button here, click **Spawn Basic Panel** below.",
            color=C.BRAND
        )
        view = TicketSetupConfigView(self.bot, self.db, cat_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class TicketHubSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, db: TicketDatabase, embed: discord.Embed, categories: list[TicketCategory]):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.embed = embed
        self.categories = categories
        
        # Create a select menu for categories
        options = []
        for cat in categories:
            options.append(discord.SelectOption(label=cat.name, description=cat.button_label, emoji=cat.button_emoji if cat.button_emoji else None, value=str(cat.id)))
        
        if not options:
            options.append(discord.SelectOption(label="No Categories", value="none", description="Create a category first!"))

        select = discord.ui.Select(placeholder="Select up to 5 categories to include in this hub", min_values=1, max_values=min(5, len(options) if options else 1), options=options, custom_id="hub_category_select")
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        select = self.children[0]
        if "none" in select.values:
            await interaction.response.send_message(embed=embed_error("You must create a ticket category first using `/ticket setup`."), ephemeral=True)
            return
            
        selected_cat_ids = [int(v) for v in select.values]
        selected_cats = [c for c in self.categories if c.id in selected_cat_ids]
        
        hub_view = TicketHubView(selected_cats)
        self.bot.add_view(hub_view)
        
        msg = await interaction.channel.send(embed=self.embed, view=hub_view)
        self.db.add_hub(msg.id, interaction.channel.id, interaction.guild.id, selected_cat_ids)
        
        await interaction.response.send_message(embed=embed_success("Hub Spawned", "Ticket Hub spawned successfully!"), ephemeral=True)


class TicketHubModal(discord.ui.Modal, title="Create Ticket Hub"):
    hub_title = discord.ui.TextInput(label="Hub Title", placeholder="e.g. Need Help?", required=True, default="Need Help?")
    hub_desc = discord.ui.TextInput(label="Hub Description", style=discord.TextStyle.paragraph, placeholder="Describe the support rules here...", required=True)
    hub_color = discord.ui.TextInput(label="Embed Color (Hex)", placeholder="e.g. #3498DB", required=False, default="#3498DB")
    hub_image = discord.ui.TextInput(label="Banner Image URL", placeholder="https://example.com/image.png", required=False)

    def __init__(self, bot: commands.Bot, db: TicketDatabase, categories: list[TicketCategory]):
        super().__init__()
        self.bot = bot
        self.db = db
        self.categories = categories

    async def on_submit(self, interaction: discord.Interaction):
        color_val = C.BRAND
        if self.hub_color.value:
            try:
                hex_str = self.hub_color.value.replace('#', '')
                color_val = int(hex_str, 16)
            except ValueError:
                pass
                
        embed = discord.Embed(
            title=self.hub_title.value,
            description=self.hub_desc.value,
            color=color_val
        )
        if self.hub_image.value:
            embed.set_image(url=self.hub_image.value)
            
        view = TicketHubSelectView(self.bot, self.db, embed, self.categories)
        await interaction.response.send_message("Select the categories you want to appear as buttons on this hub:", view=view, ephemeral=True)


class TicketCategoryManageView(discord.ui.View):
    def __init__(self, bot: commands.Bot, db: TicketDatabase, category: TicketCategory):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.category = category

    @discord.ui.button(label="Edit Category Info", style=discord.ButtonStyle.blurple, emoji="✏️")
    async def edit_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketSetupModal(self.bot, self.db, self.category))

    @discord.ui.button(label="Edit Ping/Admin Roles", style=discord.ButtonStyle.secondary, emoji="👥")
    async def edit_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"⚙️  Edit Roles: {self.category.name}",
            description="Select the Ping Roles and Admin Roles below.",
            color=C.BRAND
        )
        view = TicketSetupConfigView(self.bot, self.db, self.category.id)
        # Remove the spawn panel button for this context to avoid confusion
        view.remove_item(view.children[2])
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Delete Category", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_cat(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.db.delete_category(interaction.guild.id, self.category.id)
        await interaction.response.send_message(embed=embed_success("Category Deleted", f"Category **{self.category.name}** has been deleted."), ephemeral=True)


class TicketCategorySelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, db: TicketDatabase, categories: list[TicketCategory]):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.categories = categories

        options = [
            discord.SelectOption(label=cat.name, description=cat.button_label, value=str(cat.id))
            for cat in categories
        ]
        
        select = discord.ui.Select(placeholder="Select a category to manage", options=options, custom_id="manage_category_select")
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        cat_id = int(self.children[0].values[0])
        category = next((c for c in self.categories if c.id == cat_id), None)
        if not category:
            await interaction.response.send_message(embed=embed_error("Category not found."), ephemeral=True)
            return
            
        embed = discord.Embed(
            title=f"🛠️  Managing Category: {category.name}",
            description=f"**Button:** {category.button_emoji} {category.button_label}\n**Embed Title:** {category.embed_title}",
            color=C.BRAND
        )
        await interaction.response.send_message(embed=embed, view=TicketCategoryManageView(self.bot, self.db, category), ephemeral=True)


class TicketPanelSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, db: TicketDatabase, guild_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.guild_id = guild_id
        
        # Gather all panels and hubs
        self.panels = db.get_panels_by_guild(guild_id)
        self.hubs = db.get_hubs_by_guild(guild_id)
        
        options = []
        for p in self.panels:
            options.append(discord.SelectOption(label=f"Panel in #{p['channel_id']}", description=f"Single Category ID: {p['category_id']}", value=f"panel_{p['message_id']}"))
        for h in self.hubs:
            options.append(discord.SelectOption(label=f"Hub in #{h['channel_id']}", description=f"Multi-Category Hub", value=f"hub_{h['message_id']}"))
            
        if not options:
            options.append(discord.SelectOption(label="No Panels/Hubs Found", value="none"))

        select = discord.ui.Select(placeholder="Select a Panel or Hub to delete", options=options[:25], custom_id="manage_panel_select")
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        val = self.children[0].values[0]
        if val == "none":
            await interaction.response.send_message(embed=embed_error("Nothing to delete."), ephemeral=True)
            return
            
        ptype, msg_id = val.split('_', 1)
        
        # Try to delete the discord message
        # We need to find which channel it was in
        target_channel_id = None
        if ptype == "panel":
            target_channel_id = next((p["channel_id"] for p in self.panels if str(p["message_id"]) == msg_id), None)
        else:
            target_channel_id = next((h["channel_id"] for h in self.hubs if str(h["message_id"]) == msg_id), None)
            
        if target_channel_id:
            channel = interaction.guild.get_channel(int(target_channel_id))
            if channel:
                try:
                    msg = await channel.fetch_message(int(msg_id))
                    await msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass # Message already deleted or missing perms
                    
        # Delete from DB
        if ptype == "panel":
            self.db.remove_panel(msg_id)
            await interaction.response.send_message(embed=embed_success("Panel Deleted", "Panel deleted successfully."), ephemeral=True)
        else:
            self.db.remove_hub(msg_id)
            await interaction.response.send_message(embed=embed_success("Hub Deleted", "Hub deleted successfully."), ephemeral=True)


class PanelContentEditModal(discord.ui.Modal, title="Update Panel Content"):
    def __init__(self, bot: commands.Bot, db: TicketDatabase, message_id: int, target_channel_id: int, new_category_id: int):
        super().__init__()
        self.bot = bot
        self.db = db
        self.message_id = message_id
        self.target_channel_id = target_channel_id
        self.new_category_id = new_category_id
        
        self.emb_title = discord.ui.TextInput(
            label="New Embed Title",
            placeholder="e.g. Open a Ticket",
            required=True
        )
        self.emb_desc = discord.ui.TextInput(
            label="New Embed Description",
            style=discord.TextStyle.paragraph,
            placeholder="e.g. Choose a category below to open a ticket.",
            required=True
        )
        self.add_item(self.emb_title)
        self.add_item(self.emb_desc)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.guild.get_channel(self.target_channel_id)
        if not channel:
            await interaction.followup.send(embed=embed_error("Channel not found."), ephemeral=True)
            return
            
        try:
            msg = await channel.fetch_message(self.message_id)
        except Exception:
            await interaction.followup.send(embed=embed_error("Panel message not found. It may have been deleted."), ephemeral=True)
            return
            
        # Determine current categories
        panels = self.db.get_panels_by_guild(interaction.guild.id)
        hubs = self.db.get_hubs_by_guild(interaction.guild.id)
        
        current_cats = []
        is_hub = False
        
        for p in panels:
            if str(p["message_id"]) == str(self.message_id):
                current_cats.append(p["category_id"])
                break
        
        if not current_cats:
            for h in hubs:
                if str(h["message_id"]) == str(self.message_id):
                    current_cats = h["category_ids"]
                    is_hub = True
                    break
                    
        if not current_cats:
            await interaction.followup.send(embed=embed_error("Panel not found in database."), ephemeral=True)
            return
            
        if self.new_category_id in current_cats:
            await interaction.followup.send(embed=embed_error("This category is already on this panel."), ephemeral=True)
            return
            
        current_cats.append(self.new_category_id)
        
        # Update Database: if it was a panel, remove it and create a hub. If it was a hub, update it.
        if not is_hub:
            self.db.remove_panel(self.message_id)
            self.db.add_hub(self.message_id, self.target_channel_id, interaction.guild.id, current_cats)
        else:
            self.db.remove_hub(self.message_id)
            self.db.add_hub(self.message_id, self.target_channel_id, interaction.guild.id, current_cats)
            
        # Update Discord Message
        categories = []
        for cid in current_cats:
            cat = self.db.get_category(cid)
            if cat:
                categories.append(cat)
                
        embed = discord.Embed(
            title=self.emb_title.value,
            description=self.emb_desc.value,
            color=C.BRAND
        )
        
        view = TicketHubView(categories)
        self.bot.add_view(view)
        
        await msg.edit(embed=embed, view=view)
        await interaction.followup.send(embed=embed_success("Panel Updated", "Panel updated successfully! The new category button has been added."), ephemeral=True)


class CategoryToAddToPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot, db: TicketDatabase, categories: list, message_id: int, target_channel_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.message_id = message_id
        self.target_channel_id = target_channel_id
        
        options = [
            discord.SelectOption(label=cat.name, description=cat.button_label, value=str(cat.id))
            for cat in categories
        ]
        
        select = discord.ui.Select(placeholder="Select the category to add", options=options, custom_id="add_cat_to_panel_select")
        select.callback = self.on_select
        self.add_item(select)
        
    async def on_select(self, interaction: discord.Interaction):
        cat_id = int(self.children[0].values[0])
        await interaction.response.send_modal(PanelContentEditModal(self.bot, self.db, self.message_id, self.target_channel_id, cat_id))


class PanelAddCategorySelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, db: TicketDatabase, guild_id: int, guild: discord.Guild):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.guild = guild
        
        panels = db.get_panels_by_guild(guild_id)
        hubs = db.get_hubs_by_guild(guild_id)
        
        options = []
        for p in panels:
            ch = guild.get_channel(int(p['channel_id']))
            ch_name = f"#{ch.name}" if ch else f"#unknown ({p['channel_id']})"
            cat = db.get_category(p['category_id'])
            cat_name = cat.name if cat else f"ID {p['category_id']}"
            options.append(discord.SelectOption(
                label=f"Panel in {ch_name}",
                description=f"Category: {cat_name}",
                value=f"panel_{p['message_id']}"
            ))
        for h in hubs:
            ch = guild.get_channel(int(h['channel_id']))
            ch_name = f"#{ch.name}" if ch else f"#unknown ({h['channel_id']})"
            options.append(discord.SelectOption(
                label=f"Hub in {ch_name}",
                description=f"Multi-Category Hub ({len(h['category_ids'])} buttons)",
                value=f"hub_{h['message_id']}"
            ))
            
        if not options:
            options.append(discord.SelectOption(label="No Panels/Hubs Found", value="none"))

        select = discord.ui.Select(placeholder="Select a Panel to add a button to", options=options[:25], custom_id="append_panel_select")
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        val = self.children[0].values[0]
        if val == "none":
            await interaction.response.send_message(embed=embed_error("No panels to edit."), ephemeral=True)
            return
            
        ptype, msg_id = val.split('_', 1)
        
        # Get channel ID
        target_channel_id = None
        if ptype == "panel":
            panels = self.db.get_panels_by_guild(interaction.guild.id)
            target_channel_id = next((p["channel_id"] for p in panels if str(p["message_id"]) == msg_id), None)
        else:
            hubs = self.db.get_hubs_by_guild(interaction.guild.id)
            target_channel_id = next((h["channel_id"] for h in hubs if str(h["message_id"]) == msg_id), None)
            
        if not target_channel_id:
            await interaction.response.send_message(embed=embed_error("Could not locate the channel for this panel."), ephemeral=True)
            return
            
        categories = self.db.get_categories(interaction.guild.id)
        if not categories:
            await interaction.response.send_message(embed=embed_error("You have no categories to add."), ephemeral=True)
            return
            
        await interaction.response.send_message(
            "Select the new category you want to add as a button to this panel:", 
            view=CategoryToAddToPanelView(self.bot, self.db, categories, int(msg_id), int(target_channel_id)), 
            ephemeral=True
        )


class RespawnHubModal(discord.ui.Modal, title="Re-spawn Hub"):
    """Modal to set embed content when re-spawning an existing hub from DB."""
    def __init__(self, bot: commands.Bot, db: TicketDatabase, hub: dict, categories: list):
        super().__init__()
        self.bot = bot
        self.db = db
        self.hub = hub
        self.categories = categories

        self.emb_title = discord.ui.TextInput(
            label="Hub Embed Title",
            placeholder="e.g. Need Help? Open a Ticket!",
            required=True
        )
        self.emb_desc = discord.ui.TextInput(
            label="Hub Embed Description",
            style=discord.TextStyle.paragraph,
            placeholder="e.g. Click a button below to open a ticket.",
            required=True
        )
        self.emb_color = discord.ui.TextInput(
            label="Embed Color (Hex, optional)",
            placeholder="#2b2d31",
            required=False,
            default="#2b2d31"
        )
        self.add_item(self.emb_title)
        self.add_item(self.emb_desc)
        self.add_item(self.emb_color)

    async def on_submit(self, interaction: discord.Interaction):
        color_val = 0x2b2d31
        if self.emb_color.value:
            try:
                color_val = int(self.emb_color.value.replace('#', ''), 16)
            except ValueError:
                pass

        embed = discord.Embed(
            title=self.emb_title.value,
            description=self.emb_desc.value,
            color=color_val
        )

        view = TicketHubView(self.categories)
        self.bot.add_view(view)

        # Remove stale DB entry and post fresh message
        self.db.remove_hub(self.hub["message_id"])
        msg = await interaction.channel.send(embed=embed, view=view)
        self.db.add_hub(msg.id, interaction.channel.id, interaction.guild.id, self.hub["category_ids"])

        await interaction.response.send_message(
            f"✅ Hub re-spawned in {interaction.channel.mention} with {len(self.categories)} category buttons!",
            ephemeral=True
        )


class RespawnHubSelectView(discord.ui.View):
    """Shows all hubs in the DB so the user can pick one to re-spawn."""
    def __init__(self, bot: commands.Bot, db: TicketDatabase, guild_id: int, guild: discord.Guild):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db
        self.guild = guild

        hubs = db.get_hubs_by_guild(guild_id)
        categories_all = db.get_categories(guild_id)

        options = []
        self.hub_map = {}  # value -> (hub dict, [TicketCategory])
        for h in hubs:
            cats = [c for c in categories_all if c.id in h["category_ids"]]
            cat_names = ", ".join(c.name for c in cats) if cats else "Unknown"
            ch = guild.get_channel(int(h["channel_id"]))
            ch_name = f"#{ch.name}" if ch else f"#deleted ({h['channel_id']})"
            label = f"Hub in {ch_name}"
            desc = f"Buttons: {cat_names}"[:100]  # Discord limits description to 100 chars
            val = str(h["message_id"])
            self.hub_map[val] = (h, cats)
            options.append(discord.SelectOption(label=label, description=desc, value=val))

        if not options:
            options.append(discord.SelectOption(label="No Hubs Found in Database", value="none"))

        select = discord.ui.Select(
            placeholder="Select a hub to re-spawn in this channel",
            options=options[:25],
            custom_id="respawn_hub_select"
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        val = self.children[0].values[0]
        if val == "none":
            await interaction.response.send_message(embed=embed_error("No hubs found in the database."), ephemeral=True)
            return

        hub, cats = self.hub_map.get(val, (None, None))
        if not hub or not cats:
            await interaction.response.send_message(embed=embed_error("Hub data not found. The categories may have been deleted."), ephemeral=True)
            return

        await interaction.response.send_modal(RespawnHubModal(self.bot, self.db, hub, cats))


class TicketSetupDashboardView(discord.ui.View):
    def __init__(self, bot: commands.Bot, db: TicketDatabase):
        super().__init__(timeout=None)
        self.bot = bot
        self.db = db

    @discord.ui.button(label="Create New Category", style=discord.ButtonStyle.green, custom_id="setup_new_category", emoji="➕")
    async def new_category(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketSetupModal(self.bot, self.db))

    @discord.ui.button(label="Spawn Custom Panel", style=discord.ButtonStyle.blurple, custom_id="setup_spawn_panel", emoji="🎨")
    async def spawn_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        categories = self.db.get_categories(interaction.guild.id)
        if not categories:
            await interaction.response.send_message(embed=embed_error("You have no ticket categories yet. Create one first."), ephemeral=True)
            return
            
        # We reuse TicketCategorySelectView but we need a different callback to spawn a panel
        class SpawnPanelSelectView(discord.ui.View):
            def __init__(self, bot, db, categories):
                super().__init__(timeout=None)
                self.bot = bot
                self.db = db
                self.categories = categories
                
                options = [
                    discord.SelectOption(label=cat.name, description=cat.button_label, value=str(cat.id))
                    for cat in categories
                ]
                select = discord.ui.Select(placeholder="Select a category to spawn a panel for", options=options, custom_id="spawn_panel_select")
                select.callback = self.on_select
                self.add_item(select)
                
            async def on_select(self, interaction: discord.Interaction):
                cat_id = int(self.children[0].values[0])
                cat = next((c for c in self.categories if c.id == cat_id), None)
                if not cat:
                    await interaction.response.send_message(embed=embed_error("Category not found."), ephemeral=True)
                    return
                    
                embed = discord.Embed(
                    title=f"Open a Ticket: {cat.name}",
                    description="Click the button below to open a ticket.",
                    color=C.BRAND
                )
                view = TicketPanelView(category_id=cat.id, button_label=cat.button_label, button_emoji=cat.button_emoji)
                self.bot.add_view(view)
                
                msg = await interaction.channel.send(embed=embed, view=view)
                self.db.add_panel(msg.id, interaction.channel.id, interaction.guild.id, cat.id)
                await interaction.response.send_message(embed=embed_success("Panel Spawned", "Panel spawned in this channel."), ephemeral=True)
                
        await interaction.response.send_message("Select which category you want to spawn a panel for in this channel:", view=SpawnPanelSelectView(self.bot, self.db, categories), ephemeral=True)

    @discord.ui.button(label="Spawn Multi-Category Hub", style=discord.ButtonStyle.blurple, custom_id="setup_spawn_hub", emoji="🌐", row=1)
    async def spawn_hub(self, interaction: discord.Interaction, button: discord.ui.Button):
        categories = self.db.get_categories(interaction.guild.id)
        if not categories:
            await interaction.response.send_message(embed=embed_error("You have no ticket categories yet. Create one first."), ephemeral=True)
            return
        await interaction.response.send_modal(TicketHubModal(self.bot, self.db, categories))

    @discord.ui.button(label="Add Button to Panel/Hub", style=discord.ButtonStyle.primary, custom_id="setup_add_to_panel", emoji="🔗", row=1)
    async def add_to_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        panels = self.db.get_panels_by_guild(interaction.guild.id)
        hubs = self.db.get_hubs_by_guild(interaction.guild.id)
        if not panels and not hubs:
            await interaction.response.send_message(embed=embed_error("There are no active panels or hubs in this server. Create and spawn one first."), ephemeral=True)
            return
        await interaction.response.send_message(
            "Select an existing Panel or Hub to add a new category button to:",
            view=PanelAddCategorySelectView(self.bot, self.db, interaction.guild.id, interaction.guild),
            ephemeral=True
        )

    @discord.ui.button(label="Re-spawn Existing Hub", style=discord.ButtonStyle.secondary, custom_id="setup_respawn_hub", emoji="♻️", row=1)
    async def respawn_hub(self, interaction: discord.Interaction, button: discord.ui.Button):
        hubs = self.db.get_hubs_by_guild(interaction.guild.id)
        if not hubs:
            await interaction.response.send_message(embed=embed_error("There are no hubs in the database for this server."), ephemeral=True)
            return
        await interaction.response.send_message(
            "Select a hub to re-spawn in this channel:",
            view=RespawnHubSelectView(self.bot, self.db, interaction.guild.id, interaction.guild),
            ephemeral=True
        )

    @discord.ui.button(label="Manage Categories", style=discord.ButtonStyle.secondary, custom_id="setup_manage_categories", emoji="🛠️", row=2)
    async def manage_categories(self, interaction: discord.Interaction, button: discord.ui.Button):
        categories = self.db.get_categories(interaction.guild.id)
        if not categories:
            await interaction.response.send_message(embed=embed_error("You have no ticket categories yet."), ephemeral=True)
            return
        await interaction.response.send_message("Select a category to edit or delete:", view=TicketCategorySelectView(self.bot, self.db, categories), ephemeral=True)

    @discord.ui.button(label="Delete Panels / Hubs", style=discord.ButtonStyle.danger, custom_id="setup_manage_panels", emoji="🗑️", row=2)
    async def manage_panels(self, interaction: discord.Interaction, button: discord.ui.Button):
        panels = self.db.get_panels_by_guild(interaction.guild.id)
        hubs = self.db.get_hubs_by_guild(interaction.guild.id)
        if not panels and not hubs:
            await interaction.response.send_message(embed=embed_error("There are no active panels or hubs in this server."), ephemeral=True)
            return
        await interaction.response.send_message("Select a Panel or Hub to permanently delete:", view=TicketPanelSelectView(self.bot, self.db, interaction.guild.id), ephemeral=True)

# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = TicketDatabase()
        self.db.initialize()

    async def cog_load(self):
        # Re-register TicketControlView for every category (close/attach/custom buttons inside open tickets)
        # These use unique custom_ids per category so no conflict is possible.
        categories = self.db.get_all_categories_global()
        for cat in categories:
            self.bot.add_view(TicketControlView(cat))

        # NOTE: We do NOT register TicketPanelView or TicketHubView here.
        # Their ticket_open_{cat_id} buttons are handled universally by on_interaction().
        # Registering them would cause custom_id conflicts in discord.py's dispatcher.
        # The buttons remain visible (not greyed-out) on Discord without needing add_view.
                
        # Register dashboard persistent view
        self.bot.add_view(TicketSetupDashboardView(self.bot, self.db))

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Universal fallback handler for ticket_open_{cat_id} buttons.
        Handles both single-category panels and multi-category hubs without conflict.
        """
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("ticket_open_"):
            return
        try:
            cat_id = int(custom_id.split("ticket_open_")[1])
        except (IndexError, ValueError):
            return
        try:
            await interaction.response.send_modal(TicketCreateModal(cat_id))
        except discord.InteractionResponded:
            pass  # Already handled by a registered view — skip
        except Exception as e:
            print(f"[Tickets] Error in ticket_open handler for cat_id={cat_id}: {e}")
            try:
                await interaction.response.send_message(embed=embed_error("Something went wrong opening this ticket. Please try again."), ephemeral=True)
            except discord.InteractionResponded:
                pass

    ticket_group = app_commands.Group(name="ticket", description="Ticket system commands")

    @ticket_group.command(name="setup", description="Open the Ticket Setup Dashboard")
    @app_commands.default_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️  Ticket Setup Dashboard",
            description="Welcome to the Ticket Setup! Here you can create new ticket categories, or spawn a beautifully customized ticket panel in this channel.",
            color=C.BRAND
        )
        await interaction.response.send_message(embed=embed, view=TicketSetupDashboardView(self.bot, self.db), ephemeral=True)

    @ticket_group.command(name="category_list", description="List all ticket categories and their IDs")
    @app_commands.default_permissions(manage_guild=True)
    async def category_list(self, interaction: discord.Interaction):
        categories = self.db.get_categories(interaction.guild.id)
        if not categories:
            await interaction.response.send_message(embed=embed_error("There are no ticket categories. Create one using `/ticket setup`."), ephemeral=True)
            return
            
        desc = ""
        for cat in categories:
            desc += f"**ID:** `{cat.id}` | **Name:** {cat.name} | **Button:** {cat.button_emoji} {cat.button_label}\n"
            
        embed = discord.Embed(
            title="Ticket Categories",
            description=desc,
            color=C.BRAND
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ticket_group.command(name="panel", description="Spawn a ticket creation panel here")
    @app_commands.describe(category_id="The ID of the category to spawn a panel for (use /ticket category_list)")
    @app_commands.default_permissions(manage_guild=True)
    async def spawn_panel(self, interaction: discord.Interaction, category_id: int):
        cat = self.db.get_category(category_id)
        if not cat or cat.guild_id != interaction.guild.id:
            await interaction.response.send_message(embed=embed_error("Category not found."), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Open a Ticket: {cat.name}",
            description="Click the button below to open a ticket.",
            color=C.BRAND
        )
        view = TicketPanelView(category_id=cat.id, button_label=cat.button_label, button_emoji=cat.button_emoji)
        self.bot.add_view(view)  # Bug fix: was missing, buttons wouldn't work after restart
        
        msg = await interaction.channel.send(embed=embed, view=view)
        self.db.add_panel(msg.id, interaction.channel.id, interaction.guild.id, cat.id)
        await interaction.response.send_message(embed=embed_success("Panel Created", "Panel created."), ephemeral=True)

    @ticket_group.command(name="button_add", description="Add a custom button to a ticket category")
    @app_commands.default_permissions(manage_guild=True)
    async def button_add(self, interaction: discord.Interaction, category_id: int, button_label: str, response_text: str):
        cat = self.db.get_category(category_id)
        if not cat or cat.guild_id != interaction.guild.id:
            await interaction.response.send_message(embed=embed_error("Category not found."), ephemeral=True)
            return
            
        self.db.add_custom_button(category_id, button_label, response_text)
        self.bot.add_view(TicketControlView(self.db.get_category(category_id)))
        await interaction.response.send_message(embed=embed_success("Custom Button Added", f"Custom button **{button_label}** added to category {cat.name}!"), ephemeral=True)

    @ticket_group.command(name="user_add", description="Add a user to the current ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def user_add(self, interaction: discord.Interaction, user: discord.Member):
        active = self.db.get_active_ticket(interaction.channel.id)
        if not active:
            await interaction.response.send_message(embed=embed_error("This is not a ticket channel."), ephemeral=True)
            return
        await interaction.channel.set_permissions(user, read_messages=True, send_messages=True, attach_files=True)
        await interaction.response.send_message(embed=embed_success("User Added", f"Added {user.mention} to the ticket."))

    @ticket_group.command(name="user_remove", description="Remove a user from the current ticket")
    @app_commands.default_permissions(manage_channels=True)
    async def user_remove(self, interaction: discord.Interaction, user: discord.Member):
        active = self.db.get_active_ticket(interaction.channel.id)
        if not active:
            await interaction.response.send_message(embed=embed_error("This is not a ticket channel."), ephemeral=True)
            return
        await interaction.channel.set_permissions(user, read_messages=False, send_messages=False)
        await interaction.response.send_message(embed=embed_success("User Removed", f"Removed {user.mention} from the ticket."))

    @ticket_group.command(name="category_create", description="Create a new ticket category with custom button styling")
    @app_commands.describe(
        name="Category name (e.g. Billing, Support, Applications)",
        button_label="Text on the button (e.g. Open Billing Ticket)",
        button_emoji="Emoji on the button (e.g. 💳)",
        embed_title="Title of the welcome embed inside opened tickets",
        embed_description="Welcome description and instructions inside opened tickets",
        ping_role="Role to mention when a ticket is opened in this category",
        admin_role="Staff/Admin role with manage ticket access"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def category_create(
        self,
        interaction: discord.Interaction,
        name: str,
        button_label: str,
        button_emoji: str = "🎫",
        embed_title: str = "Support Ticket",
        embed_description: str = "Please describe your issue below. Our support team will assist you shortly.",
        ping_role: Optional[discord.Role] = None,
        admin_role: Optional[discord.Role] = None,
    ):
        ping_roles_str = str(ping_role.id) if ping_role else ""
        admin_roles_str = str(admin_role.id) if admin_role else ""
        cat_id = self.db.add_category(
            interaction.guild.id,
            name=name,
            button_label=button_label,
            button_emoji=button_emoji,
            ping_roles=ping_roles_str,
            admin_roles=admin_roles_str,
            embed_title=embed_title,
            embed_desc=embed_description
        )
        cat = self.db.get_category(cat_id)
        if cat:
            self.bot.add_view(TicketControlView(cat))

        embed = embed_success(
            "Ticket Category Created",
            f"**Category ID:** `{cat_id}`\n"
            f"**Name:** {name}\n"
            f"**Button Preview:** {button_emoji} {button_label}\n"
            f"**Ping Role:** {ping_role.mention if ping_role else '`None`'}\n\n"
            f"💡 *Use `/ticket panel_add_button` or `/ticket panel` to deploy this category.*"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ticket_group.command(name="panel_add_button", description="Add a new category button to an existing ticket panel message")
    @app_commands.describe(
        channel="The text channel where the panel message is located",
        message_id="The Message ID of the existing ticket panel",
        category_id="The Category ID to add as a button (use /ticket category_list)"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def panel_add_button(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: str,
        category_id: int
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            mid = int(message_id.strip())
        except ValueError:
            await interaction.followup.send(embed=embed_error("Invalid message ID format. Must be numeric."), ephemeral=True)
            return

        cat = self.db.get_category(category_id)
        if not cat or cat.guild_id != interaction.guild.id:
            await interaction.followup.send(embed=embed_error(f"Category with ID `{category_id}` not found."), ephemeral=True)
            return

        try:
            msg = await channel.fetch_message(mid)
        except discord.NotFound:
            await interaction.followup.send(embed=embed_error("Message not found in that channel."), ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(embed=embed_error(f"Failed to fetch message: {e}"), ephemeral=True)
            return

        # Find existing categories on this panel/hub
        panels = self.db.get_panels_by_guild(interaction.guild.id)
        hubs = self.db.get_hubs_by_guild(interaction.guild.id)
        
        current_cats = []
        is_hub = False
        
        for p in panels:
            if str(p["message_id"]) == str(mid):
                current_cats.append(p["category_id"])
                break
        
        if not current_cats:
            for h in hubs:
                if str(h["message_id"]) == str(mid):
                    current_cats = list(h["category_ids"])
                    is_hub = True
                    break

        if not current_cats:
            # First time registering this message as a hub
            current_cats = []

        if category_id in current_cats:
            await interaction.followup.send(embed=embed_warning(f"Category **{cat.name}** is already present on this panel."), ephemeral=True)
            return

        current_cats.append(category_id)

        # Update DB
        self.db.remove_panel(mid)
        self.db.remove_hub(mid)
        self.db.add_hub(mid, channel.id, interaction.guild.id, current_cats)

        # Update Discord message view
        categories_obj = []
        for cid in current_cats:
            c = self.db.get_category(cid)
            if c:
                categories_obj.append(c)

        view = TicketHubView(categories_obj)
        self.bot.add_view(view)

        await msg.edit(view=view)
        await interaction.followup.send(
            embed=embed_success(
                "Button Added to Panel",
                f"Successfully added **{cat.button_emoji} {cat.button_label}** (Category `{cat.name}`) to the panel in {channel.mention}!\n"
                f"Total buttons on panel: `{len(categories_obj)}`"
            ),
            ephemeral=True
        )

    @ticket_group.command(name="panel_remove_button", description="Remove a category button from an existing ticket panel message")
    @app_commands.describe(
        channel="The text channel where the panel message is located",
        message_id="The Message ID of the existing ticket panel",
        category_id="The Category ID to remove from the panel"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def panel_remove_button(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: str,
        category_id: int
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            mid = int(message_id.strip())
        except ValueError:
            await interaction.followup.send(embed=embed_error("Invalid message ID format. Must be numeric."), ephemeral=True)
            return

        try:
            msg = await channel.fetch_message(mid)
        except Exception as e:
            await interaction.followup.send(embed=embed_error(f"Failed to fetch message: {e}"), ephemeral=True)
            return

        hubs = self.db.get_hubs_by_guild(interaction.guild.id)
        current_cats = []
        for h in hubs:
            if str(h["message_id"]) == str(mid):
                current_cats = list(h["category_ids"])
                break

        if category_id not in current_cats:
            await interaction.followup.send(embed=embed_error(f"Category `{category_id}` is not on this panel."), ephemeral=True)
            return

        current_cats.remove(category_id)
        self.db.remove_hub(mid)

        if current_cats:
            self.db.add_hub(mid, channel.id, interaction.guild.id, current_cats)
            categories_obj = [self.db.get_category(cid) for cid in current_cats if self.db.get_category(cid)]
            view = TicketHubView(categories_obj)
            self.bot.add_view(view)
            await msg.edit(view=view)
        else:
            await msg.edit(view=None)

        await interaction.followup.send(
            embed=embed_success(
                "Button Removed",
                f"Removed category `{category_id}` from the panel in {channel.mention}."
            ),
            ephemeral=True
        )

    @ticket_group.command(name="setlogchannel", description="Set the channel where closed ticket logs and transcripts are sent")
    @app_commands.describe(channel="The channel to send ticket logs and transcripts to")
    @app_commands.default_permissions(manage_guild=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.db.set_log_channel(interaction.guild.id, channel.id)
        embed = discord.Embed(
            title="✅  Ticket Log Channel Set",
            description=f"Closed ticket logs and HTML transcripts will now be sent to {channel.mention}.",
            color=C.SUCCESS
        )
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Channel ID", value=str(channel.id), inline=True)
        embed.set_footer(text="Use /ticket setlogchannel again to change it at any time.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# get_all_categories_global is now defined as a proper method on TicketDatabase above


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
    print("🎫 Ticket system loaded!")
