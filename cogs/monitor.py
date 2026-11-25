import asyncio
import logging

import discord
from discord.ext import commands

import config
from catalog import iter_feeds
from core.vinted import RateLimited, format_price

log = logging.getLogger("monitor")


class Monitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.seen: dict[str, set[int]] = {}
        self.task: asyncio.Task | None = None

    async def cog_load(self):
        self.task = asyncio.create_task(self.run())

    async def cog_unload(self):
        if self.task:
            self.task.cancel()

    async def run(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            channels = await self.bot.db.get_feed_channels()
            if not channels:
                await asyncio.sleep(30)  # pas encore de /admin setup
                continue
            for feed_key, _, sub in iter_feeds():
                channel = self.bot.get_channel(channels.get(feed_key, 0))
                if channel is None:
                    continue
                try:
                    items = await self.bot.vinted.search(sub["params"])
                    await self.handle(feed_key, sub, channel, items)
                except RateLimited:
                    log.warning("Rate limit Vinted, pause 60s")
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("Erreur feed %s", feed_key)
                await asyncio.sleep(config.POLL_DELAY)

    async def handle(self, feed_key, sub, channel: discord.TextChannel, items: list[dict]):
        ids = [it["id"] for it in items if "id" in it]
        if feed_key not in self.seen:
            self.seen[feed_key] = set(ids)  # 1er passage : on mémorise sans poster
            return
        seen = self.seen[feed_key]
        new = [it for it in items if it.get("id") not in seen]
        for it in reversed(new):  # du plus ancien au plus récent
            seen.add(it["id"])
            try:
                await channel.send(embed=self.item_embed(it, sub["label"]), view=self.item_view(it))
            except discord.HTTPException:
                log.exception("Envoi impossible dans #%s", channel)
        if len(seen) > 3000:
            self.seen[feed_key] = set(ids)

    def item_embed(self, it: dict, label: str) -> discord.Embed:
        e = discord.Embed(
            title=(it.get("title") or "Annonce")[:256],
            url=self.bot.vinted.item_url(it),
            color=0x09B1BA,
            timestamp=discord.utils.utcnow(),
        )
        price = format_price(it.get("price"))
        total = format_price(it.get("total_item_price"))
        if price:
            e.add_field(name="💰 Prix", value=f"**{price}**" + (f"\n({total} avec protection)" if total and total != price else ""))
        if it.get("size_title"):
            e.add_field(name="📏 Taille", value=it["size_title"])
        if it.get("brand_title"):
            e.add_field(name="🏷️ Marque", value=it["brand_title"])
        if it.get("status"):
            e.add_field(name="✨ État", value=str(it["status"]))
        seller = (it.get("user") or {}).get("login")
        if seller:
            e.add_field(name="👤 Vendeur", value=seller)
        photo = (it.get("photo") or {}).get("url")
        if photo:
            e.set_image(url=photo)
        e.set_footer(text=f"Vinted Monitor • {label}")
        return e

    def item_view(self, it: dict) -> discord.ui.View:
        v = discord.ui.View()
        v.add_item(discord.ui.Button(label="Voir l'annonce", emoji="🛍️", url=self.bot.vinted.item_url(it)))
        profile = self.bot.vinted.profile_url(it)
        if profile:
            v.add_item(discord.ui.Button(label="Profil vendeur", emoji="👤", url=profile))
        return v


async def setup(bot):
    await bot.add_cog(Monitor(bot))
