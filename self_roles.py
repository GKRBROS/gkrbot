"""
self_roles.py
─────────────
Advanced Self-Role Menu system.
  • /rolemenu setup  — full interactive wizard (one command, no message IDs needed)
  • /rolemenu manage — manage an existing menu (add/remove roles)
  • /rolemenu delete — delete a menu
"""
from __future__ import annotations

import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "self_roles.sqlite3")

# ─── Database ─────────────────────────────────────────────────────────────────

class SelfRolesDB:
    def __init__(self):
        self.db_path = DB_PATH
        
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS role_menus (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    image_url TEXT,
                    embed_color TEXT DEFAULT '0x2b2d31'
                )
            """)
            # Handle migration if embed_color is missing
            try:
                conn.execute("ALTER TABLE role_menus ADD COLUMN embed_color TEXT DEFAULT '0x2b2d31'")
            except sqlite3.OperationalError:
                pass # column already exists
                
            conn.execute("""
                CREATE TABLE IF NOT EXISTS role_options (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    label TEXT,
                    emoji TEXT,
                    color TEXT DEFAULT 'primary',
                    FOREIGN KEY(message_id) REFERENCES role_menus(message_id) ON DELETE CASCADE
                )
            """)
            
            # Handle migrations for older DB schemas
            for col, col_type in [("label", "TEXT"), ("emoji", "TEXT"), ("color", "TEXT DEFAULT 'primary'")]:
                try:
                    conn.execute(f"ALTER TABLE role_options ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass # column already exists
                    
            conn.commit()

    def create_menu(self, message_id: int, channel_id: int, guild_id: int,
                    title: str, description: str, image_url: str = None, embed_color: str = '0x2b2d31'):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO role_menus "
                "(message_id, channel_id, guild_id, title, description, image_url, embed_color) VALUES (?,?,?,?,?,?,?)",
                (str(message_id), str(channel_id), str(guild_id), title, description, image_url, embed_color)
            )
            conn.commit()

    def add_role_option(self, message_id: int, role_id: int,
                        label: str = None, emoji: str = None, color: str = 'primary'):
        with self._conn() as conn:
            # avoid duplicates
            conn.execute(
                "DELETE FROM role_options WHERE message_id = ? AND role_id = ?",
                (str(message_id), str(role_id))
            )
            conn.execute(
                "INSERT INTO role_options (message_id, role_id, label, emoji, color) VALUES (?,?,?,?,?)",
                (str(message_id), str(role_id), label, emoji, color)
            )
            conn.commit()

    def remove_role_option(self, message_id: int, role_id: int):
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM role_options WHERE message_id = ? AND role_id = ?",
                (str(message_id), str(role_id))
            )
            conn.commit()

    def get_menu(self, message_id: int) -> Optional[tuple[dict, list[dict]]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM role_menus WHERE message_id = ?", (str(message_id),)
            ).fetchone()
            if not row:
                return None
            options = conn.execute(
                "SELECT * FROM role_options WHERE message_id = ? ORDER BY id", (str(message_id),)
            ).fetchall()
            return dict(row), [dict(o) for o in options]

    def get_guild_menus(self, guild_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM role_menus WHERE guild_id = ?", (str(guild_id),)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_menus(self):
        with self._conn() as conn:
            return conn.execute("SELECT * FROM role_menus").fetchall()

    def delete_menu(self, message_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM role_menus WHERE message_id = ?", (str(message_id),))
            conn.commit()


# ─── Persistent Role Button ───────────────────────────────────────────────────

class RoleButton(discord.ui.Button):
    def __init__(self, role_id: int, label: Optional[str], emoji: Optional[str], color_str: str):
        style_map = {
            'success': discord.ButtonStyle.success,
            'danger': discord.ButtonStyle.danger,
            'secondary': discord.ButtonStyle.secondary,
        }
        style = style_map.get(color_str, discord.ButtonStyle.primary)

        # Discord requires at least a label OR emoji
        btn_label = label or None
        btn_emoji = None
        if emoji:
            try:
                btn_emoji = discord.PartialEmoji.from_str(emoji)
            except Exception:
                btn_emoji = None

        super().__init__(
            style=style,
            label=btn_label,
            emoji=btn_emoji,
            custom_id=f"selfrole_{role_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message(
                "❌ This role no longer exists.", ephemeral=True
            )
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="Self-role removed")
            await interaction.response.send_message(
                f"✅ Removed **{role.name}**.", ephemeral=True
            )
        else:
            await interaction.user.add_roles(role, reason="Self-role added")
            await interaction.response.send_message(
                f"✅ Got **{role.name}**!", ephemeral=True
            )


class RoleMenuView(discord.ui.View):
    def __init__(self, options: list[dict]):
        super().__init__(timeout=None)
        for opt in options:
            self.add_item(RoleButton(
                role_id=int(opt['role_id']),
                label=opt.get('label'),
                emoji=opt.get('emoji'),
                color_str=opt.get('color', 'primary'),
            ))


# ─── Setup Wizard ─────────────────────────────────────────────────────────────

def parse_hex_color(hex_str: str, default: int = 0x2b2d31) -> int:
    hex_str = hex_str.strip().lstrip('#')
    if not hex_str:
        return default
    try:
        return int(hex_str, 16)
    except ValueError:
        return default

class SetupModal(discord.ui.Modal, title="🎭 Create Self-Role Menu"):
    menu_title = discord.ui.TextInput(
        label="Menu Title",
        placeholder="e.g. Pick Your Roles",
        max_length=256,
        required=True,
    )
    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        placeholder="Describe the menu — what roles are for, etc.",
        max_length=2048,
        required=True,
    )
    embed_color = discord.ui.TextInput(
        label="Embed Color (Hex Code)",
        placeholder="e.g. #FF0000 or 2b2d31",
        required=False,
        max_length=10,
    )
    image_url = discord.ui.TextInput(
        label="Banner Image URL (optional)",
        placeholder="https://example.com/banner.gif",
        required=False,
        max_length=512,
    )

    def __init__(self, cog: "SelfRolesCog", channel: discord.TextChannel):
        super().__init__()
        self.cog = cog
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        title = str(self.menu_title)
        desc = str(self.description)
        img = str(self.image_url).strip() or None
        color_str = str(self.embed_color).strip() or "2b2d31"
        color_int = parse_hex_color(color_str)

        # Build and post the public role menu embed
        embed = discord.Embed(title=title, description=desc, color=color_int)
        embed.set_footer(text=f"{interaction.guild.name} • Self-Roles")
        if img:
            embed.set_image(url=img)

        pub_msg = await self.channel.send(embed=embed)
        self.cog.db.create_menu(pub_msg.id, self.channel.id, interaction.guild.id, title, desc, img, color_str)

        # Send ephemeral setup panel
        panel = SetupPanel(self.cog, pub_msg)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚙️ Setup Panel",
                description=(
                    f"Menu posted in {self.channel.mention}!\n\n"
                    "Use **Add Role** to attach role buttons one by one.\n"
                    "When done, press **✅ Finish**."
                ),
                color=0x2b2d31,
            ),
            view=panel,
            ephemeral=True,
        )


class AddRoleDetailsModal(discord.ui.Modal, title="📝 Button Details"):
    label_input = discord.ui.TextInput(
        label="Button Label (optional)",
        placeholder="e.g. Valorant  (leave empty to use role name)",
        required=False,
        max_length=80,
    )
    emoji_input = discord.ui.TextInput(
        label="Emoji (optional)",
        placeholder="e.g. 🎮 or :custom_name: or <:name:id>",
        required=False,
        max_length=64,
    )

    def __init__(self, cog: "SelfRolesCog", pub_msg: discord.Message, panel_view: "SetupPanel", selected_role: discord.Role, selected_color: str):
        super().__init__()
        self.cog = cog
        self.pub_msg = pub_msg
        self.panel_view = panel_view
        self.selected_role = selected_role
        self.selected_color = selected_color

    async def on_submit(self, interaction: discord.Interaction):
        label = str(self.label_input).strip() or self.selected_role.name
        emoji = str(self.emoji_input).strip() or None

        if emoji:
            # If the user typed :emoji_name:, try to resolve it from the server's custom emojis
            if emoji.startswith(":") and emoji.endswith(":") and len(emoji) > 2:
                emoji_name = emoji[1:-1]
                found_emoji = discord.utils.get(interaction.guild.emojis, name=emoji_name)
                if found_emoji:
                    emoji = str(found_emoji)

        self.cog.db.add_role_option(self.pub_msg.id, self.selected_role.id, label, emoji, self.selected_color)

        # Refresh public message
        _, options = self.cog.db.get_menu(self.pub_msg.id)
        view = RoleMenuView(options)
        await self.pub_msg.edit(view=view)
        self.cog.bot.add_view(view, message_id=self.pub_msg.id)

        # Return to main setup panel
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"✅ Added **{self.selected_role.name}** button to the menu!\nAdd more or press **✅ Finish** when done.",
                color=0x2ECC71,
            ),
            view=self.panel_view,
        )


class RoleColorDropdownView(discord.ui.View):
    """View providing Dropdowns for Role Selection and Button Color."""
    def __init__(self, cog: "SelfRolesCog", pub_msg: discord.Message, parent_panel: "SetupPanel"):
        super().__init__(timeout=300)
        self.cog = cog
        self.pub_msg = pub_msg
        self.parent_panel = parent_panel
        
        self.selected_role: Optional[discord.Role] = None
        self.selected_color: str = "primary"
        
        self.role_select = discord.ui.RoleSelect(placeholder="1️⃣ Select a Role to add...")
        self.role_select.callback = self.role_select_callback
        self.add_item(self.role_select)
        
        self.color_select = discord.ui.Select(
            placeholder="2️⃣ Select Button Color (Default: Blurple)",
            options=[
                discord.SelectOption(label="Blurple (Primary)", value="primary", description="Standard Discord Blurple"),
                discord.SelectOption(label="Green (Success)", value="success", description="Green Button"),
                discord.SelectOption(label="Red (Danger)", value="danger", description="Red Button"),
                discord.SelectOption(label="Grey (Secondary)", value="secondary", description="Grey Button"),
            ]
        )
        self.color_select.callback = self.color_select_callback
        self.add_item(self.color_select)

    async def role_select_callback(self, interaction: discord.Interaction):
        self.selected_role = self.role_select.values[0] if self.role_select.values else None
        await interaction.response.edit_message(view=self)

    async def color_select_callback(self, interaction: discord.Interaction):
        self.selected_color = self.color_select.values[0]
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="3️⃣ Set Label & Save", style=discord.ButtonStyle.success, row=2)
    async def save_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_role:
            await interaction.response.send_message("❌ Please select a role from the dropdown first!", ephemeral=True)
            return
            
        modal = AddRoleDetailsModal(self.cog, self.pub_msg, self.parent_panel, self.selected_role, self.selected_color)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=2)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="⚙️ Setup Panel",
                description="Menu setup returned. Use **➕ Add Role** to start adding again.",
                color=0x2b2d31,
            ),
            view=self.parent_panel,
        )


class SetupPanel(discord.ui.View):
    """Ephemeral control panel shown to the admin during setup."""

    def __init__(self, cog: "SelfRolesCog", pub_msg: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.pub_msg = pub_msg

    @discord.ui.button(label="➕ Add Role", style=discord.ButtonStyle.primary)
    async def add_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Swap to the Dropdown view
        dropdown_view = RoleColorDropdownView(self.cog, self.pub_msg, self)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="➕ Adding a Role Button",
                description="Use the dropdowns below to select the Role and the Button Color. Then click **Set Label & Save**.",
                color=0x3498DB
            ),
            view=dropdown_view
        )

    @discord.ui.button(label="✅ Finish", style=discord.ButtonStyle.success)
    async def finish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        _, options = self.cog.db.get_menu(self.pub_msg.id)
        count = len(options)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Setup Complete",
                description=f"Role menu is live with **{count}** role button(s).\nMembers can now click buttons to self-assign roles!",
                color=0x2ECC71,
            ),
            view=self,
        )
        self.stop()


# ─── Manage Panel ─────────────────────────────────────────────────────────────

class RemoveRoleSelect(discord.ui.Select):
    def __init__(self, cog: "SelfRolesCog", pub_msg: discord.Message,
                 options: list[dict], guild: discord.Guild):
        self.cog = cog
        self.pub_msg = pub_msg
        select_options = []
        for opt in options:
            role = guild.get_role(int(opt['role_id']))
            name = opt.get('label') or (role.name if role else f"ID {opt['role_id']}")
            select_options.append(discord.SelectOption(
                label=name[:100],
                value=opt['role_id'],
                emoji=opt.get('emoji') or None,
            ))
        super().__init__(
            placeholder="Select a role to remove…",
            options=select_options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        self.cog.db.remove_role_option(self.pub_msg.id, role_id)

        _, options = self.cog.db.get_menu(self.pub_msg.id)
        if options:
            view = RoleMenuView(options)
            await self.pub_msg.edit(view=view)
            self.cog.bot.add_view(view, message_id=self.pub_msg.id)
        else:
            await self.pub_msg.edit(view=None)

        role = interaction.guild.get_role(role_id)
        name = role.name if role else f"ID {role_id}"
        await interaction.response.send_message(
            f"✅ Removed **{name}** from the menu.", ephemeral=True
        )


class ManagePanel(discord.ui.View):
    def __init__(self, cog: "SelfRolesCog", pub_msg: discord.Message,
                 options: list[dict], guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.pub_msg = pub_msg
        self.add_item(RemoveRoleSelect(cog, pub_msg, options, guild))

    @discord.ui.button(label="➕ Add Role", style=discord.ButtonStyle.primary, row=1)
    async def add_role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        dropdown_view = RoleColorDropdownView(self.cog, self.pub_msg, self)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="➕ Adding a Role Button",
                description="Use the dropdowns below to select the Role and the Button Color. Then click **Set Label & Save**.",
                color=0x3498DB
            ),
            view=dropdown_view
        )


# ─── Cog ──────────────────────────────────────────────────────────────────────

class SelfRolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = SelfRolesDB()
        self.db.initialize()

        self.rolemenu_group = app_commands.Group(
            name="rolemenu", description="Self-Role Menu management"
        )
        self.rolemenu_group.add_command(app_commands.Command(
            name="setup",
            description="🪄 Full interactive wizard — create + add roles in one flow",
            callback=self.setup_menu,
        ))
        self.rolemenu_group.add_command(app_commands.Command(
            name="manage",
            description="Add or remove role buttons on an existing menu",
            callback=self.manage_menu,
        ))
        self.rolemenu_group.add_command(app_commands.Command(
            name="delete",
            description="Delete a role menu permanently",
            callback=self.delete_menu,
        ))
        self.bot.tree.add_command(self.rolemenu_group)

    async def cog_load(self):
        menus = self.db.get_all_menus()
        for m in menus:
            result = self.db.get_menu(int(m['message_id']))
            if result and result[1]:
                _, options = result
                self.bot.add_view(RoleMenuView(options), message_id=int(m['message_id']))

    async def cog_unload(self):
        self.bot.tree.remove_command(self.rolemenu_group.name)

    # ── /rolemenu setup ───────────────────────────────────────────────────────

    @app_commands.describe(channel="Channel where the role menu will be posted (default: current)")
    @app_commands.default_permissions(manage_guild=True)
    async def setup_menu(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
    ) -> None:
        target = channel or interaction.channel
        modal = SetupModal(self, target)
        await interaction.response.send_modal(modal)

    # ── /rolemenu manage ──────────────────────────────────────────────────────

    @app_commands.describe(message_id="The ID of an existing role menu message")
    @app_commands.default_permissions(manage_guild=True)
    async def manage_menu(
        self,
        interaction: discord.Interaction,
        message_id: str,
    ) -> None:
        try:
            msg_id = int(message_id)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid Message ID.", ephemeral=True)

        result = self.db.get_menu(msg_id)
        if not result:
            return await interaction.response.send_message(
                "❌ No role menu found with that ID.", ephemeral=True
            )
        menu, options = result
        channel = interaction.guild.get_channel(int(menu['channel_id']))
        try:
            pub_msg = await channel.fetch_message(msg_id)
        except Exception:
            return await interaction.response.send_message(
                "❌ Could not fetch the menu message — was it deleted?", ephemeral=True
            )

        if not options:
            # No roles yet — jump straight to add-role flow
            panel = SetupPanel(self, pub_msg)
            return await interaction.response.send_message(
                embed=discord.Embed(
                    title="⚙️ Manage Menu",
                    description="No roles added yet. Use **➕ Add Role** to start.",
                    color=0x2b2d31,
                ),
                view=panel,
                ephemeral=True,
            )

        manage_panel = ManagePanel(self, pub_msg, options, interaction.guild)
        role_lines = []
        for o in options:
            r = interaction.guild.get_role(int(o['role_id']))
            name = r.mention if r else f"`{o['role_id']}`"
            role_lines.append(f"• {name}")
        role_list = "\n".join(role_lines)
        
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚙️ Manage Role Menu",
                description=f"**Current roles ({len(options)}):**\n{role_list}\n\nUse the dropdown to remove a role or **➕ Add Role** to add one.",
                color=0x2b2d31,
            ),
            view=manage_panel,
            ephemeral=True,
        )

    # ── /rolemenu delete ──────────────────────────────────────────────────────

    @app_commands.describe(message_id="The ID of the role menu message to delete")
    @app_commands.default_permissions(manage_guild=True)
    async def delete_menu(
        self,
        interaction: discord.Interaction,
        message_id: str,
    ) -> None:
        try:
            msg_id = int(message_id)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid Message ID.", ephemeral=True)

        result = self.db.get_menu(msg_id)
        if not result:
            return await interaction.response.send_message(
                "❌ No role menu found with that ID.", ephemeral=True
            )
        menu, _ = result
        channel = interaction.guild.get_channel(int(menu['channel_id']))
        try:
            pub_msg = await channel.fetch_message(msg_id)
            await pub_msg.delete()
        except Exception:
            pass

        self.db.delete_menu(msg_id)
        await interaction.response.send_message("✅ Role menu deleted.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SelfRolesCog(bot))
