import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    return int(value) if value else default


# --- Discord ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = _int("GUILD_ID")
SHOP_URL = os.getenv("SHOP_URL", "")  # lien Sellix / SellAuth / Stripe où on achète les keys

# --- Vinted ---
VINTED_DOMAIN = os.getenv("VINTED_DOMAIN", "www.vinted.fr")
POLL_DELAY = float(os.getenv("POLL_DELAY", "2.0"))  # secondes entre 2 requêtes Vinted

# --- Base de données ---
DB_PATH = os.getenv("DB_PATH", "data/bot.db")

# --- Mail (SMTP) ---
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_SSL = os.getenv("SMTP_SSL", "false").lower() == "true"  # true = port 465, false = STARTTLS
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "Vinted Monitor")  # nom affiché de l'expéditeur
MAIL_FROM_ADDRESS = os.getenv("MAIL_FROM_ADDRESS", SMTP_USER)

# --- Infos vendeur (factures) ---
SELLER_NAME = os.getenv("SELLER_NAME", "Ton Nom / Ta Marque")
SELLER_ADDRESS = os.getenv("SELLER_ADDRESS", "Adresse, CP Ville")
SELLER_SIRET = os.getenv("SELLER_SIRET", "")
SELLER_EMAIL = os.getenv("SELLER_EMAIL", MAIL_FROM_ADDRESS)
VAT_RATE = float(os.getenv("VAT_RATE", "0"))  # 0 = micro-entreprise
VAT_MENTION = os.getenv("VAT_MENTION", "TVA non applicable, art. 293 B du CGI")
