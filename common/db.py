import json
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta

from .config import DATA
from .daily import TZ


def today() -> date:
    """The current day in Kazakhstan time, so daily limits reset at local midnight."""
    return datetime.now(TZ).date()


class Store:
    """Per-bot SQLite store: premium, bought credits, daily free usage, streaks, stats, referrals, saved items."""

    def __init__(self, name: str):
        DATA.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(DATA / f"{name}.sqlite3")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                premium_until INTEGER DEFAULT 0,
                credits INTEGER DEFAULT 0,
                used_day TEXT DEFAULT '',
                used INTEGER DEFAULT 0,
                created INTEGER
            );
            CREATE TABLE IF NOT EXISTS payments (
                charge_id TEXT PRIMARY KEY,
                user_id INTEGER,
                stars INTEGER,
                payload TEXT,
                at INTEGER
            );
            CREATE TABLE IF NOT EXISTS stats (
                user_id INTEGER PRIMARY KEY,
                correct INTEGER DEFAULT 0,
                answered INTEGER DEFAULT 0,
                rounds INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS streaks (
                user_id INTEGER PRIMARY KEY,
                last_day TEXT,
                streak INTEGER DEFAULT 0,
                best INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS referrals (
                invitee INTEGER PRIMARY KEY,
                inviter INTEGER,
                at INTEGER
            );
            CREATE TABLE IF NOT EXISTS saved (
                user_id INTEGER,
                key TEXT,
                payload TEXT,
                at INTEGER,
                PRIMARY KEY (user_id, key)
            );
            CREATE TABLE IF NOT EXISTS duels (
                code TEXT PRIMARY KEY, creator INTEGER, name TEXT, qs TEXT, score INTEGER, at INTEGER
            );
            CREATE TABLE IF NOT EXISTS duel_plays (
                code TEXT, user_id INTEGER, name TEXT, score INTEGER, at INTEGER, PRIMARY KEY (code, user_id)
            );
            CREATE TABLE IF NOT EXISTS week_snap (
                user_id INTEGER PRIMARY KEY, correct INTEGER, answered INTEGER, rounds INTEGER
            );
            CREATE TABLE IF NOT EXISTS vouchers (user_id INTEGER, kind TEXT, n INTEGER, PRIMARY KEY (user_id, kind));
            CREATE TABLE IF NOT EXISTS wishes (word TEXT, user_id INTEGER, at INTEGER, PRIMARY KEY (word, user_id));
            CREATE TABLE IF NOT EXISTS subs (
                user_id INTEGER PRIMARY KEY,
                at INTEGER
            );
            """
        )
        # migrations for databases created by older versions
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(users)")}
        if "lang" not in cols:
            self.conn.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT ''")
        self.conn.commit()

    # ---- users -------------------------------------------------------------------------------
    def ensure_user(self, uid: int) -> bool:
        """Creates the user if needed; True when this call created them (a brand-new user)."""
        cur = self.conn.execute("INSERT OR IGNORE INTO users (id, created) VALUES (?, ?)", (uid, int(time.time())))
        self.conn.commit()
        return cur.rowcount == 1

    def _user(self, uid: int) -> tuple:
        self.ensure_user(uid)
        return self.conn.execute(
            "SELECT premium_until, credits, used_day, used FROM users WHERE id = ?", (uid,)
        ).fetchone()

    def set_lang(self, uid: int, lang: str) -> None:
        self.ensure_user(uid)
        self.conn.execute("UPDATE users SET lang = ? WHERE id = ?", (lang, uid))
        self.conn.commit()

    def get_lang(self, uid: int) -> str:
        row = self.conn.execute("SELECT lang FROM users WHERE id = ?", (uid,)).fetchone()
        return (row[0] if row else "") or ""

    # ---- premium, credits, daily quota ------------------------------------------------------
    def is_premium(self, uid: int) -> bool:
        return self._user(uid)[0] > time.time()

    def premium_until(self, uid: int) -> int:
        return self._user(uid)[0]

    def add_premium(self, uid: int, days: int) -> None:
        until = max(self._user(uid)[0], int(time.time())) + days * 86400
        self.conn.execute("UPDATE users SET premium_until = ? WHERE id = ?", (until, uid))
        self.conn.commit()

    def add_credits(self, uid: int, n: int) -> None:
        self._user(uid)
        self.conn.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (n, uid))
        self.conn.commit()

    def credits(self, uid: int) -> int:
        return self._user(uid)[1]

    def free_left(self, uid: int, free_per_day: int) -> int:
        _, _, used_day, used = self._user(uid)
        return max(0, free_per_day - (used if used_day == today().isoformat() else 0))

    def take(self, uid: int, free_per_day: int) -> bool:
        """Spend one use: premium is unlimited, then free daily quota, then bought credits."""
        premium_until, credits, used_day, used = self._user(uid)
        if premium_until > time.time():
            return True
        day = today().isoformat()
        if used_day != day:
            used = 0
        if used < free_per_day:
            self.conn.execute("UPDATE users SET used_day = ?, used = ? WHERE id = ?", (day, used + 1, uid))
        elif credits > 0:
            self.conn.execute("UPDATE users SET credits = credits - 1 WHERE id = ?", (uid,))
        else:
            return False
        self.conn.commit()
        return True

    def take_n(self, uid: int, free_per_day: int, n: int) -> bool:
        """Spend `n` uses at once, or none at all if there are not enough (premium is unlimited)."""
        premium_until, credits, used_day, used = self._user(uid)
        if premium_until > time.time():
            return True
        day = today().isoformat()
        used = used if used_day == day else 0
        free = max(0, free_per_day - used)
        if free + credits < n:
            return False
        from_free = min(free, n)
        self.conn.execute("UPDATE users SET used_day = ?, used = ?, credits = credits - ? WHERE id = ?",
                          (day, used + from_free, n - from_free, uid))
        self.conn.commit()
        return True

    # ---- payments ----------------------------------------------------------------------------
    def record_payment(self, charge_id: str, uid: int, stars: int, payload: str) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO payments VALUES (?, ?, ?, ?, ?)",
            (charge_id, uid, stars, payload, int(time.time())),
        )
        self.conn.commit()
        return cur.rowcount == 1

    # ---- streaks and stats --------------------------------------------------------------------
    def streak_hit(self, uid: int, grace: int = 0) -> tuple:
        """Registers activity today. Returns (streak, best, grew_today). `grace` forgives that many missed days."""
        day = today()
        row = self.conn.execute("SELECT last_day, streak, best FROM streaks WHERE user_id = ?", (uid,)).fetchone()
        if row is None:
            streak, best, grew = 1, 1, True
        else:
            last = date.fromisoformat(row[0])
            gap = (day - last).days
            if gap <= 0:
                return row[1], row[2], False
            streak = row[1] + 1 if gap <= 1 + grace else 1
            best, grew = max(row[2], streak), True
        self.conn.execute(
            "INSERT INTO streaks (user_id, last_day, streak, best) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_day = excluded.last_day, streak = excluded.streak, best = excluded.best",
            (uid, day.isoformat(), streak, best),
        )
        self.conn.commit()
        return streak, best, grew

    def streak(self, uid: int) -> tuple:
        """Current (streak, best); a streak whose last day is older than yesterday counts as 0."""
        row = self.conn.execute("SELECT last_day, streak, best FROM streaks WHERE user_id = ?", (uid,)).fetchone()
        if row is None:
            return 0, 0
        alive = (today() - date.fromisoformat(row[0])).days <= 1
        return (row[1] if alive else 0), row[2]

    def add_answer(self, uid: int, correct: bool) -> None:
        self.conn.execute("INSERT OR IGNORE INTO stats (user_id) VALUES (?)", (uid,))
        self.conn.execute(
            "UPDATE stats SET answered = answered + 1, correct = correct + ? WHERE user_id = ?", (1 if correct else 0, uid)
        )
        self.conn.commit()

    def finish_round(self, uid: int) -> None:
        self.conn.execute("INSERT OR IGNORE INTO stats (user_id) VALUES (?)", (uid,))
        self.conn.execute("UPDATE stats SET rounds = rounds + 1 WHERE user_id = ?", (uid,))
        self.conn.commit()

    def user_stats(self, uid: int) -> dict:
        row = self.conn.execute("SELECT correct, answered, rounds FROM stats WHERE user_id = ?", (uid,)).fetchone()
        return dict(zip(("correct", "answered", "rounds"), row or (0, 0, 0)))

    # ---- referrals ---------------------------------------------------------------------------
    def add_referral(self, invitee: int, inviter: int) -> bool:
        """Records that `inviter` brought `invitee`. False for self-invites, unknown inviters or repeats."""
        if invitee == inviter:
            return False
        if self.conn.execute("SELECT 1 FROM users WHERE id = ?", (inviter,)).fetchone() is None:
            return False
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO referrals (invitee, inviter, at) VALUES (?, ?, ?)", (invitee, inviter, int(time.time()))
        )
        self.conn.commit()
        return cur.rowcount == 1

    def referrals(self, uid: int) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM referrals WHERE inviter = ?", (uid,)).fetchone()[0]

    # ---- saved items -------------------------------------------------------------------------
    def save_item(self, uid: int, key: str, payload: str = "") -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO saved (user_id, key, payload, at) VALUES (?, ?, ?, ?)", (uid, key, payload, int(time.time()))
        )
        self.conn.commit()
        return cur.rowcount == 1

    def has_saved(self, uid: int, key: str) -> bool:
        return self.conn.execute("SELECT 1 FROM saved WHERE user_id = ? AND key = ?", (uid, key)).fetchone() is not None

    def count_saved(self, uid: int) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM saved WHERE user_id = ?", (uid,)).fetchone()[0]

    def list_saved(self, uid: int, limit: int = 30) -> list:
        return self.conn.execute(
            "SELECT key, payload FROM saved WHERE user_id = ? ORDER BY at DESC, rowid DESC LIMIT ?", (uid, limit)
        ).fetchall()

    def delete_saved(self, uid: int, key: str) -> None:
        self.conn.execute("DELETE FROM saved WHERE user_id = ? AND key = ?", (uid, key))
        self.conn.commit()

    # ---- weekly summary: what changed since the previous one --------------------------------------
    def week_delta(self, uid: int) -> dict:
        """Stats gained since the last call, then moves the snapshot forward."""
        now = self.user_stats(uid)
        row = self.conn.execute("SELECT correct, answered, rounds FROM week_snap WHERE user_id = ?", (uid,)).fetchone()
        before = dict(zip(("correct", "answered", "rounds"), row or (0, 0, 0)))
        self.conn.execute("INSERT OR REPLACE INTO week_snap VALUES (?, ?, ?, ?)", (uid, now["correct"], now["answered"], now["rounds"]))
        self.conn.commit()
        return {k: now[k] - before[k] for k in now}

    # ---- vouchers: things paid for but not delivered yet (a file that failed to build, say) ---------
    def add_voucher(self, uid: int, kind: str, n: int = 1) -> None:
        self.conn.execute("INSERT INTO vouchers VALUES (?, ?, ?) ON CONFLICT(user_id, kind) DO UPDATE SET n = n + ?", (uid, kind, n, n))
        self.conn.commit()

    def take_voucher(self, uid: int, kind: str) -> bool:
        cur = self.conn.execute("UPDATE vouchers SET n = n - 1 WHERE user_id = ? AND kind = ? AND n > 0", (uid, kind))
        self.conn.commit()
        return cur.rowcount == 1

    def vouchers(self, uid: int, kind: str) -> int:
        row = self.conn.execute("SELECT n FROM vouchers WHERE user_id = ? AND kind = ?", (uid, kind)).fetchone()
        return row[0] if row else 0

    # ---- wishes: words people looked for and we do not have yet ---------------------------------
    def add_wish(self, uid: int, word: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO wishes VALUES (?, ?, ?)", (word, uid, int(time.time())))
        self.conn.commit()

    def top_wishes(self, n: int = 15) -> list:
        return self.conn.execute("SELECT word, COUNT(*) c FROM wishes GROUP BY word ORDER BY c DESC, MAX(at) DESC LIMIT ?", (n,)).fetchall()

    # ---- duels -------------------------------------------------------------------------------
    def create_duel(self, creator: int, name: str, qs: list, score: int) -> str:
        code = secrets.token_hex(4)
        self.conn.execute("INSERT INTO duels VALUES (?, ?, ?, ?, ?, ?)", (code, creator, name, json.dumps(qs), score, int(time.time())))
        self.conn.commit()
        return code

    def get_duel(self, code: str):
        row = self.conn.execute("SELECT creator, name, qs, score FROM duels WHERE code = ?", (code,)).fetchone()
        return None if row is None else {"creator": row[0], "name": row[1], "qs": json.loads(row[2]), "score": row[3]}

    def duel_played(self, code: str, uid: int) -> bool:
        return self.conn.execute("SELECT 1 FROM duel_plays WHERE code = ? AND user_id = ?", (code, uid)).fetchone() is not None

    def duel_play(self, code: str, uid: int, name: str, score: int) -> bool:
        cur = self.conn.execute("INSERT OR IGNORE INTO duel_plays VALUES (?, ?, ?, ?, ?)", (code, uid, name, score, int(time.time())))
        self.conn.commit()
        return cur.rowcount == 1

    def duel_plays(self, code: str) -> list:
        return self.conn.execute("SELECT name, score FROM duel_plays WHERE code = ? ORDER BY score DESC, at", (code,)).fetchall()

    # ---- daily-message subscriptions -----------------------------------------------------------
    def set_sub(self, uid: int, on: bool) -> None:
        if on:
            self.conn.execute("INSERT OR IGNORE INTO subs (user_id, at) VALUES (?, ?)", (uid, int(time.time())))
        else:
            self.conn.execute("DELETE FROM subs WHERE user_id = ?", (uid,))
        self.conn.commit()

    def is_sub(self, uid: int) -> bool:
        return self.conn.execute("SELECT 1 FROM subs WHERE user_id = ?", (uid,)).fetchone() is not None

    def subs(self) -> list:
        return [r[0] for r in self.conn.execute("SELECT user_id FROM subs")]

    # ---- owner stats -------------------------------------------------------------------------
    def stats_text(self) -> str:
        c = self.conn
        users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        day = c.execute("SELECT COUNT(*) FROM users WHERE used_day = ?", (today().isoformat(),)).fetchone()[0]
        paid, stars = c.execute("SELECT COUNT(*), COALESCE(SUM(stars), 0) FROM payments").fetchone()
        buyers = c.execute("SELECT COUNT(DISTINCT user_id) FROM payments").fetchone()[0]
        premium = c.execute("SELECT COUNT(*) FROM users WHERE premium_until > ?", (int(time.time()),)).fetchone()[0]
        subs = c.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
        refs = c.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
        return (f"users: {users} (active today: {day})\npremium now: {premium}\npayments: {paid} from {buyers} buyers\n"
                f"stars: {stars}\ndaily-DM subscribers: {subs}\nreferrals: {refs}")

    # kept for old callers
    def stats(self) -> str:
        return self.stats_text()
