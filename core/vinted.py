import logging

import aiohttp

log = logging.getLogger("vinted")


class RateLimited(Exception):
    pass


class VintedClient:
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )

    def __init__(self, domain: str):
        self.base = f"https://{domain}"
        self.session: aiohttp.ClientSession | None = None
        self._has_cookie = False

    async def start(self):
        self.session = aiohttp.ClientSession(
            headers={"User-Agent": self.UA, "Accept-Language": "fr-FR,fr;q=0.9"},
            timeout=aiohttp.ClientTimeout(total=20),
        )

    async def close(self):
        if self.session:
            await self.session.close()

    async def _refresh_cookies(self):
        """Visite la page d'accueil pour récupérer le cookie de session (access_token_web)."""
        self.session.cookie_jar.clear()
        async with self.session.get(self.base + "/") as r:
            await r.read()
        self._has_cookie = True
        log.info("Cookies Vinted rafraîchis")

    async def search(self, params: dict, per_page: int = 40) -> list[dict]:
        if not self._has_cookie:
            await self._refresh_cookies()
        query = {"page": 1, "per_page": per_page, "order": "newest_first", **params}
        for _ in range(2):
            async with self.session.get(
                f"{self.base}/api/v2/catalog/items", params=query, headers={"Accept": "application/json"}
            ) as r:
                status = r.status
                if status == 429:
                    raise RateLimited()
                if status not in (401, 403):
                    r.raise_for_status()
                    data = await r.json(content_type=None)
                    return data.get("items", [])
            await self._refresh_cookies()
        raise RuntimeError(f"Vinted refuse l'accès (HTTP {status})")

    def item_url(self, item: dict) -> str:
        url = item.get("url") or f"/items/{item.get('id')}"
        return url if url.startswith("http") else self.base + url

    def profile_url(self, item: dict) -> str | None:
        user = item.get("user") or {}
        url = user.get("profile_url")
        if url:
            return url if url.startswith("http") else self.base + url
        return f"{self.base}/member/{user['id']}" if user.get("id") else None


def format_price(value) -> str | None:
    """Gère les 2 formats de l'API : '12.0' ou {'amount': '12.0', 'currency_code': 'EUR'}."""
    if value is None:
        return None
    if isinstance(value, dict):
        amount, currency = value.get("amount"), value.get("currency_code", "EUR")
    else:
        amount, currency = value, "EUR"
    try:
        amount = f"{float(amount):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(amount)
    return f"{amount} {'€' if currency == 'EUR' else currency}"
