import io
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from catalog import CATEGORIES, PLANS, plans_for_category
from cogs.subscriptions import PanelView
from core.subs import DAY, apply_roles, fmt_eur, fmt_ts, generate_key, plan_role

PLAN_CHOICES = [app_commands.Choice(name=f"{p['label']} ({fmt_eur(p['price'])})", value=k) for k, p in PLANS.items()]


class Admin(commands.Cog):
    admin = app_commands.Group(
        name="admin",
        description="Commandes admin",
        default_permissions=discord.Permissions(administrator=True),
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot

    # ---------- setup serveur ----------
    @admin.command(name="setup", description="Crée/maj les rôles, catégories et salons de monitor")
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        created = []

        # Rôles par offre
        roles = {}
        for key, p in PLANS.items():
            role = await plan_role(self.bot, guild, key)
            if role is None:
                role = await guild.create_role(name=f"{p['emoji']} {p['label']}", colour=p["color"], reason="Setup bot")
                await self.bot.db.set_setting(f"role:{key}", str(role.id))
                created.append(f"rôle {role.name}")
            roles[key] = role

        feeds = await self.bot.db.get_feed_channels()
        for cat_key, cat in CATEGORIES.items():
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True),
            }
            for plan_key in plans_for_category(cat_key):
                overwrites[roles[plan_key]] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=False, read_message_history=True
                )

            cid = await self.bot.db.get_setting(f"cat:{cat_key}")
            category = guild.get_channel(int(cid)) if cid else None
            if category is None:
                category = await guild.create_category(cat["label"], overwrites=overwrites, reason="Setup bot")
                await self.bot.db.set_setting(f"cat:{cat_key}", str(category.id))
                created.append(f"catégorie {cat['label']}")
            else:
                await category.edit(overwrites=overwrites)

            for feed_key, sub in cat["subs"].items():
                channel = guild.get_channel(feeds[feed_key]) if feed_key in feeds else None
                if channel is None:
                    channel = await guild.create_text_channel(
                        feed_key, category=category, overwrites=overwrites, topic=f"Monitor Vinted — {sub['label']}"
                    )
                    await self.bot.db.set_feed_channel(feed_key, channel.id)
                    created.append(f"#{feed_key}")
                else:
                    await channel.edit(category=category, sync_permissions=True)

        txt = "\n".join(created[:40]) or "Rien de nouveau, permissions mises à jour."
        await interaction.followup.send(f"✅ Setup terminé.\n```\n{txt}\n```", ephemeral=True)

    @admin.command(name="panel", description="Poste le panel abonnés dans ce salon")
    async def panel(self, interaction: discord.Interaction):
        e = discord.Embed(
            title="🛍️ Vinted Monitor",
            description=(
                "Reçois les nouvelles annonces Vinted **en temps réel**, avant tout le monde.\n\n"
                "🔑 **Activer une key** — ta key sera liée à ton compte\n"
                "📊 **Mon abonnement** — offre et date d'expiration\n"
                "💎 **Offres** — ce que débloque chaque offre\n"
                "📄 **Ma facture** — reçue par e-mail en PDF"
            ),
            color=0x09B1BA,
        )
        await interaction.channel.send(embed=e, view=PanelView(self.bot))
        await interaction.response.send_message("✅ Panel posté.", ephemeral=True)

    # ---------- keys ----------
    @admin.command(name="genkey", description="Génère des keys d'abonnement")
    @app_commands.choices(plan=PLAN_CHOICES)
    @app_commands.describe(days="Durée en jours", quantity="Nombre de keys", price="Prix facturé (défaut : prix de l'offre au pro-rata)")
    async def genkey(
        self,
        interaction: discord.Interaction,
        plan: app_commands.Choice[str],
        days: app_commands.Range[int, 1, 3650] = 30,
        quantity: app_commands.Range[int, 1, 500] = 1,
        price: Optional[app_commands.Range[float, 0, 10000]] = None,
    ):
        if price is None:
            price = round(PLANS[plan.value]["price"] * days / 30, 2)
        keys = [generate_key() for _ in range(quantity)]
        await self.bot.db.create_keys(keys, plan.value, days, price, interaction.user.id)
        file = discord.File(io.BytesIO("\n".join(keys).encode()), filename=f"keys_{plan.value}_{days}j.txt")
        preview = "\n".join(keys[:15]) + ("\n..." if quantity > 15 else "")
        await interaction.response.send_message(
            f"✅ {quantity} key(s) **{plan.name}** — {days} jours — {fmt_eur(price)}\n```\n{preview}\n```",
            file=file,
            ephemeral=True,
        )

    @admin.command(name="revokekey", description="Désactive une key non utilisée")
    async def revokekey(self, interaction: discord.Interaction, key: str):
        ok = await self.bot.db.revoke_key(key.strip().upper())
        await interaction.response.send_message("✅ Key révoquée." if ok else "❌ Key introuvable.", ephemeral=True)

    # ---------- abonnements ----------
    @admin.command(name="give", description="Donne un abonnement sans key")
    @app_commands.choices(plan=PLAN_CHOICES)
    async def give(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        plan: app_commands.Choice[str],
        days: app_commands.Range[int, 1, 3650],
    ):
        now = time.time()
        sub = await self.bot.db.get_sub(member.id)
        base = sub["expires_at"] if sub and sub["plan"] == plan.value and sub["expires_at"] > now else now
        expires = base + days * DAY
        await self.bot.db.set_sub(member.id, plan.value, expires, None)
        await apply_roles(self.bot, member, plan.value)
        await interaction.response.send_message(
            f"✅ {member.mention} → **{plan.name}** jusqu'au {fmt_ts(expires)}", ephemeral=True
        )

    @admin.command(name="revoke", description="Retire l'abonnement d'un membre")
    async def revoke(self, interaction: discord.Interaction, member: discord.Member):
        await self.bot.db.delete_sub(member.id)
        await apply_roles(self.bot, member, None)
        await interaction.response.send_message(f"✅ Abonnement de {member.mention} retiré.", ephemeral=True)

    @admin.command(name="info", description="Infos abonnement + keys d'un membre")
    async def info(self, interaction: discord.Interaction, member: discord.Member):
        sub = await self.bot.db.get_sub(member.id)
        keys = await self.bot.db.keys_for(member.id)
        e = discord.Embed(title=f"👤 {member}", color=0x09B1BA)
        if sub:
            e.add_field(name="Offre", value=PLANS.get(sub["plan"], {}).get("label", sub["plan"]))
            e.add_field(name="Expire", value=fmt_ts(sub["expires_at"]))
        else:
            e.description = "Aucun abonnement."
        if keys:
            e.add_field(
                name=f"Keys ({len(keys)})",
                value="\n".join(f"`{k['key']}` — {k['plan']} {k['days']}j — <t:{k['redeemed_at']}:d>" for k in keys[:10]),
                inline=False,
            )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @admin.command(name="stats", description="Stats keys, abonnés et revenus")
    async def stats(self, interaction: discord.Interaction):
        e = discord.Embed(title="📈 Stats", color=0x09B1BA)
        active = {r["plan"]: r["n"] for r in await self.bot.db.active_counts(time.time())}
        total_rev = 0.0
        for r in await self.bot.db.key_stats():
            total_rev += r["revenu"] or 0
            e.add_field(
                name=PLANS.get(r["plan"], {}).get("label", r["plan"]),
                value=f"Abonnés actifs : **{active.get(r['plan'], 0)}**\nKeys dispo : {r['dispo']}/{r['total']}\nRevenu : {fmt_eur(r['revenu'] or 0)}",
            )
        e.set_footer(text=f"Revenu total (keys activées) : {fmt_eur(total_rev)}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ---------- mail ----------
    @admin.command(name="mailname", description="Change le nom d'expéditeur des mails de facture")
    async def mailname(self, interaction: discord.Interaction, nom: app_commands.Range[str, 1, 60]):
        await self.bot.db.set_setting("mail_from_name", nom)
        await interaction.response.send_message(f"✅ Les mails partiront au nom de **{nom}**.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
