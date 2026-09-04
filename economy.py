"""
economy.py — Centralized Economy System for GKR Bot.

Features:
  • Global Wallet & Bank balances
  • Work, Crime, Rob, Daily, Weekly
  • Interactive Shop and User Inventories
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import datetime
import random
from typing import Optional, List, Dict

import discord
from discord import app_commands
from discord.ext import commands
from gkr_ui import C, embed_error, embed_success, embed_info, embed_warning, Paginator, paginate_leaderboard, medal

# ---------------------------------------------------------------------------
# Constants & DB Path
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), "economy.sqlite3")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class EconomyDatabase:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS balances (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    wallet INTEGER DEFAULT 0,
                    bank INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS shop_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    role_id TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    quantity INTEGER DEFAULT 1,
                    FOREIGN KEY(item_id) REFERENCES shop_items(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cooldowns (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    command TEXT NOT NULL,
                    last_used TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id, command)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS eco_settings (
                    guild_id TEXT PRIMARY KEY,
                    rob_enabled INTEGER DEFAULT 1,
                    crime_enabled INTEGER DEFAULT 1
                )
            """)
            conn.commit()

    # --- Balances ---

    def get_balance(self, guild_id: int, user_id: int) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT wallet, bank FROM balances WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id))
            ).fetchone()
            if row:
                return dict(row)
            return {"wallet": 0, "bank": 0}

    def add_wallet(self, guild_id: int, user_id: int, amount: int) -> dict:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO balances (guild_id, user_id, wallet, bank)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET wallet = wallet + ?
            """, (str(guild_id), str(user_id), amount, amount))
            conn.commit()
            return self.get_balance(guild_id, user_id)

    def add_bank(self, guild_id: int, user_id: int, amount: int) -> dict:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO balances (guild_id, user_id, wallet, bank)
                VALUES (?, ?, 0, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET bank = bank + ?
            """, (str(guild_id), str(user_id), amount, amount))
            conn.commit()
            return self.get_balance(guild_id, user_id)

    def move_to_bank(self, guild_id: int, user_id: int, amount: int) -> bool:
        bal = self.get_balance(guild_id, user_id)
        if bal["wallet"] < amount or amount <= 0:
            return False
        with self._conn() as conn:
            conn.execute(
                "UPDATE balances SET wallet = wallet - ?, bank = bank + ? WHERE guild_id = ? AND user_id = ?",
                (amount, amount, str(guild_id), str(user_id))
            )
            conn.commit()
            return True

    def move_to_wallet(self, guild_id: int, user_id: int, amount: int) -> bool:
        bal = self.get_balance(guild_id, user_id)
        if bal["bank"] < amount or amount <= 0:
            return False
        with self._conn() as conn:
            conn.execute(
                "UPDATE balances SET bank = bank - ?, wallet = wallet + ? WHERE guild_id = ? AND user_id = ?",
                (amount, amount, str(guild_id), str(user_id))
            )
            conn.commit()
            return True

    def get_leaderboard(self, guild_id: int, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT user_id, wallet, bank, (wallet + bank) as total FROM balances WHERE guild_id = ? ORDER BY total DESC LIMIT ?",
                (str(guild_id), limit)
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Cooldowns ---

    def get_cooldown(self, guild_id: int, user_id: int, command: str) -> Optional[datetime.datetime]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT last_used FROM cooldowns WHERE guild_id = ? AND user_id = ? AND command = ?",
                (str(guild_id), str(user_id), command)
            ).fetchone()
            if row:
                return datetime.datetime.fromisoformat(row["last_used"])
            return None

    def set_cooldown(self, guild_id: int, user_id: int, command: str) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cooldowns (guild_id, user_id, command, last_used)
                VALUES (?, ?, ?, ?)
            """, (str(guild_id), str(user_id), command, datetime.datetime.utcnow().isoformat()))
            conn.commit()

    # --- Shop & Inventory ---

    def add_shop_item(self, guild_id: int, name: str, description: str, price: int, role_id: Optional[int]) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO shop_items (guild_id, name, description, price, role_id) VALUES (?, ?, ?, ?, ?)",
                (str(guild_id), name, description, price, str(role_id) if role_id else None)
            )
            conn.commit()
            return cur.lastrowid

    def get_shop_items(self, guild_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM shop_items WHERE guild_id = ?", (str(guild_id),)).fetchall()
            return [dict(r) for r in rows]

    def get_shop_item(self, item_id: int) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM shop_items WHERE id = ?", (item_id,)).fetchone()
            return dict(row) if row else None

    def remove_shop_item(self, guild_id: int, item_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM shop_items WHERE id = ? AND guild_id = ?", (item_id, str(guild_id)))
            conn.commit()
            return cur.rowcount > 0

    def add_to_inventory(self, guild_id: int, user_id: int, item_id: int, quantity: int = 1) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO inventory (guild_id, user_id, item_id, quantity)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id, item_id) DO UPDATE SET quantity = quantity + ?
            """, (str(guild_id), str(user_id), item_id, quantity, quantity))
            conn.commit()

    def get_inventory(self, guild_id: int, user_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT i.id as inv_id, i.quantity, s.id as item_id, s.name, s.description, s.role_id
                FROM inventory i
                JOIN shop_items s ON i.item_id = s.id
                WHERE i.guild_id = ? AND i.user_id = ?
            """, (str(guild_id), str(user_id))).fetchall()
            return [dict(r) for r in rows]

    def remove_from_inventory(self, guild_id: int, user_id: int, item_id: int, quantity: int = 1) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT quantity FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?",
                (str(guild_id), str(user_id), item_id)
            ).fetchone()
            if not row or row["quantity"] < quantity:
                return False
            if row["quantity"] == quantity:
                conn.execute("DELETE FROM inventory WHERE guild_id = ? AND user_id = ? AND item_id = ?",
                             (str(guild_id), str(user_id), item_id))
            else:
                conn.execute("UPDATE inventory SET quantity = quantity - ? WHERE guild_id = ? AND user_id = ? AND item_id = ?",
                             (quantity, str(guild_id), str(user_id), item_id))
            conn.commit()
            return True


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class EconomyCog(commands.GroupCog, group_name="eco"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = EconomyDatabase()
        self.db.initialize()

    # ── Core ───────────────────────────────────────────────────────────────

    @app_commands.command(name="balance", description="Check your or someone else's balance")
    @app_commands.describe(user="The user to check (default: yourself)")
    async def balance(self, interaction: discord.Interaction, user: Optional[discord.Member] = None) -> None:
        target = user or interaction.user
        if target.bot:
            await interaction.response.send_message(embed=embed_error("Bots don't have wallets."), ephemeral=True)
            return
        bal = self.db.get_balance(interaction.guild.id, target.id)
        total = bal["wallet"] + bal["bank"]
        embed = discord.Embed(title=f"💰  {target.display_name}", color=C.GOLD)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Wallet",    value=f"🪙 **{bal['wallet']:,}**", inline=True)
        embed.add_field(name="Bank",      value=f"🏦 **{bal['bank']:,}**",   inline=True)
        embed.add_field(name="Net Worth", value=f"💎 **{total:,}**",         inline=True)
        embed.set_footer(text="GKR Economy  •  /eco deposit | /eco withdraw")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="deposit", description="Move coins from your wallet into the bank")
    @app_commands.describe(amount="Amount to deposit, or 'all'")
    async def deposit(self, interaction: discord.Interaction, amount: str) -> None:
        bal = self.db.get_balance(interaction.guild.id, interaction.user.id)
        if bal["wallet"] <= 0:
            await interaction.response.send_message(embed=embed_error("Your wallet is empty."), ephemeral=True)
            return
        dep = bal["wallet"] if amount.lower() == "all" else None
        if dep is None:
            try:
                dep = int(amount)
            except ValueError:
                await interaction.response.send_message(embed=embed_error("Enter a number or `all`."), ephemeral=True)
                return
        if dep <= 0:
            await interaction.response.send_message(embed=embed_error("Amount must be greater than zero."), ephemeral=True)
            return
        if not self.db.move_to_bank(interaction.guild.id, interaction.user.id, dep):
            await interaction.response.send_message(embed=embed_error("You don't have that many coins in your wallet."), ephemeral=True)
            return
        new = self.db.get_balance(interaction.guild.id, interaction.user.id)
        e = embed_success("Deposited", f"**🪙 {dep:,}** moved to your bank.")
        e.add_field(name="Wallet", value=f"🪙 {new['wallet']:,}", inline=True)
        e.add_field(name="Bank",   value=f"🏦 {new['bank']:,}",   inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="withdraw", description="Move coins from the bank to your wallet")
    @app_commands.describe(amount="Amount to withdraw, or 'all'")
    async def withdraw(self, interaction: discord.Interaction, amount: str) -> None:
        bal = self.db.get_balance(interaction.guild.id, interaction.user.id)
        if bal["bank"] <= 0:
            await interaction.response.send_message(embed=embed_error("Your bank is empty."), ephemeral=True)
            return
        wd = bal["bank"] if amount.lower() == "all" else None
        if wd is None:
            try:
                wd = int(amount)
            except ValueError:
                await interaction.response.send_message(embed=embed_error("Enter a number or `all`."), ephemeral=True)
                return
        if wd <= 0:
            await interaction.response.send_message(embed=embed_error("Amount must be greater than zero."), ephemeral=True)
            return
        if not self.db.move_to_wallet(interaction.guild.id, interaction.user.id, wd):
            await interaction.response.send_message(embed=embed_error("You don't have that many coins in your bank."), ephemeral=True)
            return
        new = self.db.get_balance(interaction.guild.id, interaction.user.id)
        e = embed_success("Withdrawn", f"**🪙 {wd:,}** moved to your wallet.")
        e.add_field(name="Wallet", value=f"🪙 {new['wallet']:,}", inline=True)
        e.add_field(name="Bank",   value=f"🏦 {new['bank']:,}",   inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="pay", description="Send coins to another member")
    @app_commands.describe(user="Who to pay", amount="Amount to send")
    async def pay(self, interaction: discord.Interaction, user: discord.Member, amount: int) -> None:
        if user.bot or user.id == interaction.user.id:
            await interaction.response.send_message(embed=embed_error("You cannot pay this user."), ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message(embed=embed_error("Amount must be greater than zero."), ephemeral=True)
            return
        bal = self.db.get_balance(interaction.guild.id, interaction.user.id)
        if bal["wallet"] < amount:
            await interaction.response.send_message(embed=embed_error(f"You only have **🪙 {bal['wallet']:,}** in your wallet."), ephemeral=True)
            return
        self.db.add_wallet(interaction.guild.id, interaction.user.id, -amount)
        self.db.add_wallet(interaction.guild.id, user.id, amount)
        embed = discord.Embed(title="💸  Payment Sent", description=f"**🪙 {amount:,}** sent to {user.mention}", color=C.SUCCESS)
        embed.set_footer(text="GKR Economy")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="View the richest members")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        lb = self.db.get_leaderboard(interaction.guild.id, limit=50)

        def fmt(i: int, row: dict) -> str:
            total = row["wallet"] + row["bank"]
            return f"{medal(i)}  <@{row['user_id']}> — 🪙 **{total:,}**"

        pages = paginate_leaderboard("🏆  Economy Leaderboard", lb, fmt, color=C.GOLD, footer="GKR Economy")
        await interaction.followup.send(embed=pages[0], view=Paginator(pages, interaction.user.id))

    # ── Earning ─────────────────────────────────────────────────────────────

    def _check_cooldown(self, guild_id: int, user_id: int, command: str, hours: int) -> tuple[bool, str]:
        last_used = self.db.get_cooldown(guild_id, user_id, command)
        if last_used:
            now = datetime.datetime.utcnow()
            diff = now - last_used
            if diff.total_seconds() < (hours * 3600):
                rem = (hours * 3600) - diff.total_seconds()
                h, r = divmod(rem, 3600)
                m, s = divmod(r, 60)
                parts = []
                if h: parts.append(f"{int(h)}h")
                if m: parts.append(f"{int(m)}m")
                parts.append(f"{int(s)}s")
                return False, " ".join(parts)
        return True, ""

    @app_commands.command(name="daily", description="Claim your daily reward")
    async def daily(self, interaction: discord.Interaction) -> None:
        can_use, time_left = self._check_cooldown(interaction.guild.id, interaction.user.id, "daily", 24)
        if not can_use:
            await interaction.response.send_message(embed=embed_warning(f"Already claimed today. Come back in **{time_left}**.", title="On Cooldown"), ephemeral=True)
            return
        reward = random.randint(500, 1500)
        self.db.add_wallet(interaction.guild.id, interaction.user.id, reward)
        self.db.set_cooldown(interaction.guild.id, interaction.user.id, "daily")
        new = self.db.get_balance(interaction.guild.id, interaction.user.id)
        embed = discord.Embed(title="🎁  Daily Reward", description=f"You received **🪙 {reward:,}**!", color=C.GOLD)
        embed.add_field(name="New Wallet", value=f"🪙 {new['wallet']:,}", inline=True)
        embed.set_footer(text="GKR Economy  •  Come back tomorrow for another reward")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="work", description="Work a shift to earn coins")
    async def work(self, interaction: discord.Interaction) -> None:
        can_use, time_left = self._check_cooldown(interaction.guild.id, interaction.user.id, "work", 1)
        if not can_use:
            await interaction.response.send_message(embed=embed_warning(f"You need to rest. Next shift in **{time_left}**.", title="On Cooldown"), ephemeral=True)
            return
        jobs = [
            ("🍔", "Flipped burgers at McDonald's",    100, 300),
            ("🤖", "Fixed bugs in GKR Bot",            300, 800),
            ("🌿", "Mowed the neighbor's lawn",         50, 150),
            ("🎮", "Streamed games on Twitch",         200, 600),
            ("🏆", "Won a gaming tournament",          500, 1000),
            ("📈", "Invested in crypto and got lucky", 400,  900),
            ("🚗", "Delivered packages as a courier",  150,  400),
            ("🎵", "Performed at a local show",        200,  700),
        ]
        icon, desc, min_r, max_r = random.choice(jobs)
        reward = random.randint(min_r, max_r)
        self.db.add_wallet(interaction.guild.id, interaction.user.id, reward)
        self.db.set_cooldown(interaction.guild.id, interaction.user.id, "work")
        embed = discord.Embed(title=f"{icon}  Work Complete", description=desc, color=C.SUCCESS)
        embed.add_field(name="Earned", value=f"🪙 **{reward:,}**", inline=True)
        embed.set_footer(text="GKR Economy  •  Next shift in 1h")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="rob", description="Attempt to rob another user's wallet")
    @app_commands.describe(user="Target user")
    async def rob(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if user.bot or user.id == interaction.user.id:
            await interaction.response.send_message(embed=embed_error("You cannot rob this user."), ephemeral=True)
            return
        can_use, time_left = self._check_cooldown(interaction.guild.id, interaction.user.id, "rob", 2)
        if not can_use:
            await interaction.response.send_message(embed=embed_warning(f"The cops are watching. Lay low for **{time_left}**.", title="On Cooldown"), ephemeral=True)
            return
        target_bal = self.db.get_balance(interaction.guild.id, user.id)
        if target_bal["wallet"] < 250:
            await interaction.response.send_message(embed=embed_error(f"{user.display_name} needs at least 🪙 250 in their wallet."), ephemeral=True)
            return
        self.db.set_cooldown(interaction.guild.id, interaction.user.id, "rob")
        if random.random() < 0.4:
            pct = random.uniform(0.1, 0.4)
            stolen = int(target_bal["wallet"] * pct)
            self.db.add_wallet(interaction.guild.id, user.id, -stolen)
            self.db.add_wallet(interaction.guild.id, interaction.user.id, stolen)
            embed = discord.Embed(title="🥷  Heist Successful", description=f"You got away with **🪙 {stolen:,}** from {user.mention}'s wallet.", color=C.SUCCESS)
            embed.set_footer(text="GKR Economy  •  Don't get too greedy")
        else:
            my_bal = self.db.get_balance(interaction.guild.id, interaction.user.id)
            fine = max(500, int(my_bal["wallet"] * 0.1))
            self.db.add_wallet(interaction.guild.id, interaction.user.id, -fine)
            embed = discord.Embed(title="🚓  Caught!", description=f"You were caught trying to rob {user.mention} and fined **🪙 {fine:,}**.", color=C.DANGER)
            embed.set_footer(text="GKR Economy  •  Next attempt in 2h")
        await interaction.response.send_message(embed=embed)

    # ── Shop & Inventory ────────────────────────────────────────────────────

    @app_commands.command(name="shop", description="Browse the server shop")
    async def shop(self, interaction: discord.Interaction) -> None:
        items = self.db.get_shop_items(interaction.guild.id)
        if not items:
            await interaction.response.send_message(embed=embed_info("🛒  Shop Empty", "No items yet. Admins can add items with `/eco additem`.", color=C.NEUTRAL), ephemeral=True)
            return
        chunks = [items[i:i+5] for i in range(0, len(items), 5)]
        pages = []
        for pn, chunk in enumerate(chunks):
            embed = discord.Embed(title=f"🛒  {interaction.guild.name} Shop", color=C.BRAND)
            for item in chunk:
                role_line = ""
                if item["role_id"]:
                    role = interaction.guild.get_role(int(item["role_id"]))
                    role_line = f"\n> Grants: {role.mention if role else 'a role'}"
                embed.add_field(
                    name=f"`ID {item['id']}`  {item['name']}",
                    value=f"🪙 **{item['price']:,}**\n{item['description']}{role_line}",
                    inline=False
                )
            embed.set_footer(text=f"GKR Economy  •  /eco buy <ID>  •  Page {pn+1}/{len(chunks)}")
            pages.append(embed)
        await interaction.response.send_message(embed=pages[0], view=Paginator(pages, interaction.user.id), ephemeral=True)

    @app_commands.command(name="buy", description="Purchase an item from the shop")
    @app_commands.describe(item_id="The item ID shown in /eco shop")
    async def buy(self, interaction: discord.Interaction, item_id: int) -> None:
        item = self.db.get_shop_item(item_id)
        if not item or item["guild_id"] != str(interaction.guild.id):
            await interaction.response.send_message(embed=embed_error(f"Item `#{item_id}` not found."), ephemeral=True)
            return
        bal = self.db.get_balance(interaction.guild.id, interaction.user.id)
        if bal["wallet"] < item["price"]:
            shortage = item["price"] - bal["wallet"]
            await interaction.response.send_message(embed=embed_error(f"You need **🪙 {shortage:,}** more to afford **{item['name']}**."), ephemeral=True)
            return
        self.db.add_wallet(interaction.guild.id, interaction.user.id, -item["price"])
        self.db.add_to_inventory(interaction.guild.id, interaction.user.id, item["id"])
        e = embed_success("Purchase Complete", f"You bought **{item['name']}** for 🪙 {item['price']:,}.")
        if item["role_id"]:
            role = interaction.guild.get_role(int(item["role_id"]))
            if role:
                try:
                    await interaction.user.add_roles(role, reason=f"Shop purchase #{item_id}")
                    e.add_field(name="Role Granted", value=role.mention, inline=True)
                except discord.Forbidden:
                    e.add_field(name="⚠️ Role Error", value="I couldn't grant the role — contact an admin.", inline=False)
        new = self.db.get_balance(interaction.guild.id, interaction.user.id)
        e.add_field(name="Remaining", value=f"🪙 {new['wallet']:,}", inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="inventory", description="View your purchased items")
    async def inventory(self, interaction: discord.Interaction) -> None:
        inv = self.db.get_inventory(interaction.guild.id, interaction.user.id)
        if not inv:
            await interaction.response.send_message(embed=embed_info("🎒  Inventory Empty", "You haven't purchased anything yet. Browse `/eco shop`.", color=C.NEUTRAL), ephemeral=True)
            return
        embed = discord.Embed(title=f"🎒  {interaction.user.display_name}'s Inventory", color=C.PURPLE)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        for item in inv:
            embed.add_field(name=f"{item['name']}  ×{item['quantity']}", value=item["description"], inline=False)
        embed.set_footer(text="GKR Economy")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Admin ───────────────────────────────────────────────────────────────

    @app_commands.command(name="additem", description="Add a new item to the shop")
    @app_commands.describe(name="Item name", description="Short description", price="Price in coins", role="Role granted on purchase")
    @app_commands.default_permissions(manage_guild=True)
    async def additem(self, interaction: discord.Interaction, name: str, description: str, price: int, role: Optional[discord.Role] = None) -> None:
        if price <= 0:
            await interaction.response.send_message(embed=embed_error("Price must be greater than zero."), ephemeral=True)
            return
        item_id = self.db.add_shop_item(interaction.guild.id, name, description, price, role.id if role else None)
        e = embed_success("Item Added", f"**{name}** added to the shop for 🪙 {price:,}.")
        e.add_field(name="Item ID", value=f"`{item_id}`", inline=True)
        if role:
            e.add_field(name="Grants Role", value=role.mention, inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="removeitem", description="Remove an item from the shop")
    @app_commands.describe(item_id="The item ID to remove")
    @app_commands.default_permissions(manage_guild=True)
    async def removeitem(self, interaction: discord.Interaction, item_id: int) -> None:
        if self.db.remove_shop_item(interaction.guild.id, item_id):
            await interaction.response.send_message(embed=embed_success("Item Removed", f"Item `#{item_id}` removed."), ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed_error(f"Item `#{item_id}` not found."), ephemeral=True)

    @app_commands.command(name="addcoins", description="Give or remove coins from a user")
    @app_commands.describe(user="Target user", amount="Coins to add (negative to remove)")
    @app_commands.default_permissions(manage_guild=True)
    async def addcoins(self, interaction: discord.Interaction, user: discord.Member, amount: int) -> None:
        if amount == 0:
            await interaction.response.send_message(embed=embed_error("Amount cannot be zero."), ephemeral=True)
            return
        self.db.add_wallet(interaction.guild.id, user.id, amount)
        verb = "given to" if amount > 0 else "removed from"
        await interaction.response.send_message(embed=embed_success("Balance Updated", f"**🪙 {abs(amount):,}** {verb} {user.mention}."), ephemeral=True)


# ---------------------------------------------------------------------------
# Extension setup
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
