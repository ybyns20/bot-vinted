import logging

import discord
from discord.ext import commands

import config
from core.db import Database
from core.vinted import VintedClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class VintedBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  # à activer aussi dans le Developer Portal
        super().__init__(command_prefix="!", intents=intents)
        self.db = Database(config.DB_PATH)
        self.vinted = VintedClient(config.VINTED_DOMAIN)

    async def setup_hook(self):
        await self.db.connect()
        await self.vinted.start()
        for ext in ("cogs.subscriptions", "cogs.admin", "cogs.monitor"):
            await self.load_extension(ext)
        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        logging.info("%d commandes synchronisées", len(synced))

    async def on_ready(self):
        logging.info("Connecté en tant que %s", self.user)

    async def close(self):
        await self.vinted.close()
        await self.db.close()
        await super().close()


if __name__ == "__main__":
    if not config.DISCORD_TOKEN or not config.GUILD_ID:
        raise SystemExit("Remplis DISCORD_TOKEN et GUILD_ID dans le fichier .env")
    VintedBot().run(config.DISCORD_TOKEN, log_handler=None)
