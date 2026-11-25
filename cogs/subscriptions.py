import io
import logging
import re
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from catalog import PLANS
from core.invoice import build_invoice_pdf, send_invoice_email
from core.subs import (
    DAY, RedeemError, apply_roles, dm, fmt_ts, plans_embed, redeem_key, status_embed,
)

log = logging.getLogger("subs")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def do_redeem(bot, interaction: discord.Interaction, key: str):
    if not isinstance(interaction.user, discord.Member):
        return await interaction.response.send_message("Utilise ça sur le serveur.", ephemeral=True)
    try:
        plan, expires = await redeem_key(bot, interaction.user, key)
    except RedeemError as e:
        return await interaction.response.send_message(str(e), ephemeral=True)
    p = PLANS[plan]
    e = discord.Embed(
        title="✅ Key activée !",
        description=f"Offre {p['emoji']} **{p['label']}** active jusqu'au {fmt_ts(expires)}.\n"
        "La key est maintenant liée à **ton compte uniquement**.",
        color=p["color"],
    )
    e.set_footer(text="Tu peux demander ta facture avec le bouton 📄 du panel.")
    await interaction.response.send_message(embed=e, ephemeral=True)
    log.info("%s (%s) a activé une key %s", interaction.user, interaction.user.id, plan)


class RedeemModal(discord.ui.Modal, title="🔑 Activer une key"):
    key = discord.ui.TextInput(label="Ta key", placeholder="VNTD-XXXX-XXXX-XXXX-XXXX", min_length=10, max_length=40)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await do_redeem(self.bot, interaction, self.key.value)


class InvoiceModal(discord.ui.Modal, title="📄 Recevoir ma facture"):
    name = discord.ui.TextInput(label="Nom et prénom", max_length=80)
    email = discord.ui.TextInput(label="Adresse e-mail", placeholder="toi@exemple.fr", max_length=120)
    address = discord.ui.TextInput(label="Adresse", placeholder="12 rue de Paris", max_length=120)
    city = discord.ui.TextInput(label="Code postal et ville", placeholder="75001 Paris", max_length=80)
    company = discord.ui.TextInput(
        label="Entreprise / N° TVA (optionnel)", required=False, max_length=100
    )

    def __init__(self, bot, key_row):
        super().__init__()
        self.bot = bot
        self.key_row = key_row

    async def on_submit(self, interaction: discord.Interaction):
        email = self.email.value.strip()
        if not EMAIL_RE.match(email):
            return await interaction.response.send_message("❌ Adresse e-mail invalide.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)

        k = self.key_row
        inv = await self.bot.db.invoice_for_key(k["key"])
        already = inv is not None
        if not already:
            inv = await self.bot.db.create_invoice(
                user_id=interaction.user.id,
                key=k["key"],
                name=self.name.value.strip(),
                email=email,
                address=self.address.value.strip(),
                city=self.city.value.strip(),
                company=self.company.value.strip() or None,
                plan=k["plan"],
                days=k["days"],
                amount=k["price"],
            )
        await send_invoice(self.bot, interaction, inv, already)


async def send_invoice(bot, interaction: discord.Interaction, inv, already: bool):
    pdf = build_invoice_pdf(inv)
    from_name = await bot.db.get_setting("mail_from_name", config.MAIL_FROM_NAME)
    file = discord.File(io.BytesIO(pdf), filename=f"{inv['number']}.pdf")
    prefix = "ℹ️ Une facture existe déjà pour cet achat, je te la renvoie.\n" if already else ""
    if not config.SMTP_HOST:
        return await interaction.followup.send(f"{prefix}📄 Voici ta facture **{inv['number']}**.", file=file, ephemeral=True)
    try:
        await send_invoice_email(inv, pdf, from_name)
        msg = f"{prefix}✅ Facture **{inv['number']}** envoyée à **{inv['email']}** (pense à regarder les spams)."
    except Exception:
        log.exception("Envoi mail facture échoué")
        msg = f"{prefix}⚠️ L'envoi du mail a échoué, voici ta facture **{inv['number']}** en direct."
    await interaction.followup.send(msg, file=file, ephemeral=True)


class PanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        if config.SHOP_URL:
            self.add_item(discord.ui.Button(label="Acheter", emoji="🛒", url=config.SHOP_URL))

    @discord.ui.button(label="Activer une key", emoji="🔑", style=discord.ButtonStyle.success, custom_id="panel:redeem")
    async def redeem(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(RedeemModal(self.bot))

    @discord.ui.button(label="Mon abonnement", emoji="📊", style=discord.ButtonStyle.primary, custom_id="panel:status")
    async def status(self, interaction: discord.Interaction, _):
        await interaction.response.send_message(embed=await status_embed(self.bot, interaction.user), ephemeral=True)

    @discord.ui.button(label="Offres", emoji="💎", style=discord.ButtonStyle.secondary, custom_id="panel:plans")
    async def plans(self, interaction: discord.Interaction, _):
        await interaction.response.send_message(embed=plans_embed(), ephemeral=True)

    @discord.ui.button(label="Ma facture", emoji="📄", style=discord.ButtonStyle.secondary, custom_id="panel:invoice")
    async def invoice(self, interaction: discord.Interaction, _):
        key_row = await self.bot.db.last_key_for(interaction.user.id)
        if key_row is None:
            return await interaction.response.send_message(
                "❌ Aucun achat trouvé sur ton compte. Active d'abord une key.", ephemeral=True
            )
        inv = await self.bot.db.invoice_for_key(key_row["key"])
        if inv is not None:
            await interaction.response.defer(ephemeral=True, thinking=True)
            return await send_invoice(self.bot, interaction, inv, already=True)
        await interaction.response.send_modal(InvoiceModal(self.bot, key_row))


class Subscriptions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(PanelView(self.bot))
        self.expiry_loop.start()

    async def cog_unload(self):
        self.expiry_loop.cancel()

    @app_commands.command(name="redeem", description="Activer une key d'abonnement")
    @app_commands.guild_only()
    async def redeem(self, interaction: discord.Interaction, key: str):
        await do_redeem(self.bot, interaction, key)

    @app_commands.command(name="abonnement", description="Voir ton abonnement")
    async def abonnement(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=await status_embed(self.bot, interaction.user), ephemeral=True)

    @app_commands.command(name="offres", description="Voir les offres disponibles")
    async def offres(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=plans_embed(), ephemeral=True)

    @tasks.loop(minutes=2)
    async def expiry_loop(self):
        now = time.time()
        guild = self.bot.get_guild(config.GUILD_ID)

        for row in await self.bot.db.expired_subs(now):
            await self.bot.db.delete_sub(row["user_id"])
            member = guild.get_member(row["user_id"]) if guild else None
            if member:
                try:
                    await apply_roles(self.bot, member, None)
                except discord.HTTPException:
                    log.warning("Impossible de retirer les rôles de %s", row["user_id"])
            e = discord.Embed(
                title="⌛ Abonnement expiré",
                description="Ton abonnement est terminé, tu n'as plus accès aux salons de monitor.",
                color=0xED4245,
            )
            if config.SHOP_URL:
                e.add_field(name="🔁 Renouveler", value=config.SHOP_URL)
            await dm(self.bot, row["user_id"], e)
            log.info("Abonnement expiré : %s", row["user_id"])

        for row in await self.bot.db.subs_to_remind(now, now + 3 * DAY):
            e = discord.Embed(
                title="⏰ Ton abonnement expire bientôt",
                description=f"Ton offre **{PLANS.get(row['plan'], {}).get('label', row['plan'])}** expire {fmt_ts(row['expires_at'])}.",
                color=0xFEE75C,
            )
            if config.SHOP_URL:
                e.add_field(name="🔁 Renouveler", value=config.SHOP_URL)
            await dm(self.bot, row["user_id"], e)
            await self.bot.db.mark_reminded(row["user_id"])

    @expiry_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Remet le rôle si la personne quitte/revient pendant son abonnement."""
        sub = await self.bot.db.get_sub(member.id)
        if sub and sub["expires_at"] > time.time():
            try:
                await apply_roles(self.bot, member, sub["plan"])
            except discord.HTTPException:
                pass


async def setup(bot):
    await bot.add_cog(Subscriptions(bot))
