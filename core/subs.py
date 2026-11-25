"""Logique abonnements : activation de key, rôles, embeds."""
import secrets
import time

import discord

import config
from catalog import CATEGORIES, PLANS, plan_rank

DAY = 86400
KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O/1/I pour éviter les confusions


class RedeemError(Exception):
    pass


def generate_key() -> str:
    groups = ["".join(secrets.choice(KEY_ALPHABET) for _ in range(4)) for _ in range(4)]
    return "VNTD-" + "-".join(groups)


def fmt_ts(ts: float) -> str:
    return f"<t:{int(ts)}:F> (<t:{int(ts)}:R>)"


def fmt_eur(amount: float) -> str:
    return f"{amount:.2f} €".replace(".", ",")


async def plan_role(bot, guild: discord.Guild, plan_key: str) -> discord.Role | None:
    rid = await bot.db.get_setting(f"role:{plan_key}")
    return guild.get_role(int(rid)) if rid else None


async def apply_roles(bot, member: discord.Member, plan_key: str | None):
    """Donne le rôle du plan et retire les autres. plan_key=None retire tout."""
    to_remove, to_add = [], None
    for key in PLANS:
        role = await plan_role(bot, member.guild, key)
        if role is None:
            continue
        if key == plan_key:
            if role not in member.roles:
                to_add = role
        elif role in member.roles:
            to_remove.append(role)
    if to_remove:
        await member.remove_roles(*to_remove, reason="Abonnement")
    if to_add:
        await member.add_roles(to_add, reason="Abonnement")


async def redeem_key(bot, member: discord.Member, raw_key: str) -> tuple[str, float]:
    key = raw_key.strip().upper()
    row = await bot.db.get_key(key)
    if row is None or row["revoked"]:
        raise RedeemError("❌ Key invalide.")
    if row["redeemed_by"] is not None:
        if row["redeemed_by"] == member.id:
            raise RedeemError("ℹ️ Tu as déjà activé cette key.")
        raise RedeemError("❌ Cette key est déjà liée à un autre compte.")

    new_plan = row["plan"]
    if new_plan not in PLANS:
        raise RedeemError("❌ Offre inconnue, contacte un admin.")

    now = time.time()
    added = row["days"] * DAY
    sub = await bot.db.get_sub(member.id)

    if sub and sub["expires_at"] > now and sub["plan"] in PLANS:
        current = sub["plan"]
        if current == new_plan:
            expires = sub["expires_at"] + added  # prolongation
        elif plan_rank(new_plan) > plan_rank(current):
            # Upgrade : le temps restant est converti au pro-rata du prix
            remaining = sub["expires_at"] - now
            ratio = PLANS[current]["price"] / PLANS[new_plan]["price"]
            expires = now + added + remaining * ratio
        else:
            raise RedeemError(
                f"❌ Tu as déjà l'offre **{PLANS[current]['label']}** (supérieure) active jusqu'au "
                f"{fmt_ts(sub['expires_at'])}. Active cette key après son expiration."
            )
    else:
        expires = now + added

    if not await bot.db.claim_key(key, member.id):
        raise RedeemError("❌ Cette key vient d'être utilisée.")
    await bot.db.set_sub(member.id, new_plan, expires, key)
    await apply_roles(bot, member, new_plan)
    return new_plan, expires


def plans_embed() -> discord.Embed:
    e = discord.Embed(
        title="💎 Nos offres",
        description="Chaque offre débloque des salons de monitor Vinted en temps réel.",
        color=0x09B1BA,
    )
    for p in PLANS.values():
        cats = "\n".join(
            f"• {CATEGORIES[c]['label']} ({len(CATEGORIES[c]['subs'])} salons)" for c in p["categories"]
        )
        e.add_field(name=f"{p['emoji']} {p['label']} — {fmt_eur(p['price'])}/mois", value=cats, inline=True)
    if config.SHOP_URL:
        e.add_field(name="🛒 Acheter", value=config.SHOP_URL, inline=False)
    return e


async def status_embed(bot, user: discord.abc.User) -> discord.Embed:
    sub = await bot.db.get_sub(user.id)
    if not sub or sub["expires_at"] <= time.time() or sub["plan"] not in PLANS:
        e = discord.Embed(title="📊 Ton abonnement", description="Aucun abonnement actif.", color=0xED4245)
        if config.SHOP_URL:
            e.add_field(name="🛒 Acheter une key", value=config.SHOP_URL)
        return e
    p = PLANS[sub["plan"]]
    e = discord.Embed(title="📊 Ton abonnement", color=p["color"])
    e.add_field(name="Offre", value=f"{p['emoji']} **{p['label']}**", inline=True)
    e.add_field(name="Expire", value=fmt_ts(sub["expires_at"]), inline=True)
    e.add_field(
        name="Accès",
        value="\n".join(f"✅ {CATEGORIES[c]['label']}" for c in p["categories"]),
        inline=False,
    )
    return e


async def dm(bot, user_id: int, embed: discord.Embed):
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        await user.send(embed=embed)
    except discord.HTTPException:
        pass
