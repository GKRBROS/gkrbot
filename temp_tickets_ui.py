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
