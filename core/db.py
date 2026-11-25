import os
import time

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS keys (
    key         TEXT PRIMARY KEY,
    plan        TEXT NOT NULL,
    days        INTEGER NOT NULL,
    price       REAL NOT NULL,
    created_at  INTEGER NOT NULL,
    created_by  INTEGER NOT NULL,
    redeemed_by INTEGER,
    redeemed_at INTEGER,
    revoked     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_keys_user ON keys(redeemed_by);

CREATE TABLE IF NOT EXISTS subscriptions (
    user_id    INTEGER PRIMARY KEY,
    plan       TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    last_key   TEXT,
    reminded   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS invoices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    number     TEXT UNIQUE,
    user_id    INTEGER NOT NULL,
    key        TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL,
    address    TEXT NOT NULL,
    city       TEXT NOT NULL,
    company    TEXT,
    plan       TEXT NOT NULL,
    days       INTEGER NOT NULL,
    amount     REAL NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS feeds (
    feed_key   TEXT PRIMARY KEY,
    channel_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def _one(self, sql, args=()):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchone()

    async def _all(self, sql, args=()):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchall()

    # ---------- keys ----------
    async def create_keys(self, keys: list[str], plan: str, days: int, price: float, admin_id: int):
        now = int(time.time())
        await self.conn.executemany(
            "INSERT INTO keys (key, plan, days, price, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            [(k, plan, days, price, now, admin_id) for k in keys],
        )
        await self.conn.commit()

    async def get_key(self, key: str):
        return await self._one("SELECT * FROM keys WHERE key = ?", (key,))

    async def claim_key(self, key: str, user_id: int) -> bool:
        """Lie la key au compte de façon atomique. False si déjà prise entre-temps."""
        cur = await self.conn.execute(
            "UPDATE keys SET redeemed_by = ?, redeemed_at = ? "
            "WHERE key = ? AND redeemed_by IS NULL AND revoked = 0",
            (user_id, int(time.time()), key),
        )
        await self.conn.commit()
        return cur.rowcount == 1

    async def revoke_key(self, key: str) -> bool:
        cur = await self.conn.execute("UPDATE keys SET revoked = 1 WHERE key = ?", (key,))
        await self.conn.commit()
        return cur.rowcount == 1

    async def last_key_for(self, user_id: int):
        return await self._one(
            "SELECT * FROM keys WHERE redeemed_by = ? ORDER BY redeemed_at DESC LIMIT 1", (user_id,)
        )

    async def keys_for(self, user_id: int):
        return await self._all(
            "SELECT * FROM keys WHERE redeemed_by = ? ORDER BY redeemed_at DESC", (user_id,)
        )

    async def key_stats(self):
        return await self._all(
            "SELECT plan, COUNT(*) AS total, "
            "SUM(CASE WHEN redeemed_by IS NULL AND revoked = 0 THEN 1 ELSE 0 END) AS dispo, "
            "SUM(CASE WHEN redeemed_by IS NOT NULL THEN price ELSE 0 END) AS revenu "
            "FROM keys GROUP BY plan"
        )

    # ---------- subscriptions ----------
    async def get_sub(self, user_id: int):
        return await self._one("SELECT * FROM subscriptions WHERE user_id = ?", (user_id,))

    async def set_sub(self, user_id: int, plan: str, expires_at: float, last_key: str | None):
        await self.conn.execute(
            "INSERT INTO subscriptions (user_id, plan, expires_at, last_key, reminded) VALUES (?, ?, ?, ?, 0) "
            "ON CONFLICT(user_id) DO UPDATE SET plan = excluded.plan, expires_at = excluded.expires_at, "
            "last_key = COALESCE(excluded.last_key, subscriptions.last_key), reminded = 0",
            (user_id, plan, int(expires_at), last_key),
        )
        await self.conn.commit()

    async def delete_sub(self, user_id: int):
        await self.conn.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def expired_subs(self, now: float):
        return await self._all("SELECT * FROM subscriptions WHERE expires_at <= ?", (int(now),))

    async def subs_to_remind(self, now: float, before: float):
        return await self._all(
            "SELECT * FROM subscriptions WHERE reminded = 0 AND expires_at > ? AND expires_at <= ?",
            (int(now), int(before)),
        )

    async def mark_reminded(self, user_id: int):
        await self.conn.execute("UPDATE subscriptions SET reminded = 1 WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def active_counts(self, now: float):
        return await self._all(
            "SELECT plan, COUNT(*) AS n FROM subscriptions WHERE expires_at > ? GROUP BY plan", (int(now),)
        )

    # ---------- invoices ----------
    async def invoice_for_key(self, key: str):
        return await self._one("SELECT * FROM invoices WHERE key = ?", (key,))

    async def create_invoice(self, *, user_id, key, name, email, address, city, company, plan, days, amount):
        now = int(time.time())
        cur = await self.conn.execute(
            "INSERT INTO invoices (user_id, key, name, email, address, city, company, plan, days, amount, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, key, name, email, address, city, company, plan, days, amount, now),
        )
        number = f"FAC-{time.strftime('%Y', time.localtime(now))}-{cur.lastrowid:05d}"
        await self.conn.execute("UPDATE invoices SET number = ? WHERE id = ?", (number, cur.lastrowid))
        await self.conn.commit()
        return await self._one("SELECT * FROM invoices WHERE id = ?", (cur.lastrowid,))

    # ---------- feeds ----------
    async def set_feed_channel(self, feed_key: str, channel_id: int):
        await self.conn.execute(
            "INSERT INTO feeds (feed_key, channel_id) VALUES (?, ?) "
            "ON CONFLICT(feed_key) DO UPDATE SET channel_id = excluded.channel_id",
            (feed_key, channel_id),
        )
        await self.conn.commit()

    async def get_feed_channels(self) -> dict[str, int]:
        rows = await self._all("SELECT feed_key, channel_id FROM feeds")
        return {r["feed_key"]: r["channel_id"] for r in rows}

    # ---------- settings ----------
    async def get_setting(self, k: str, default: str | None = None) -> str | None:
        row = await self._one("SELECT v FROM settings WHERE k = ?", (k,))
        return row["v"] if row else default

    async def set_setting(self, k: str, v: str):
        await self.conn.execute(
            "INSERT INTO settings (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (k, v)
        )
        await self.conn.commit()
