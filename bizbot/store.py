"""Bookings in SQLite."""
import sqlite3
import time
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, phone TEXT,
                service TEXT, master TEXT, start INTEGER, minutes INTEGER,
                status TEXT DEFAULT 'active', reminded INTEGER DEFAULT 0, created INTEGER
            );
            CREATE INDEX IF NOT EXISTS bookings_start ON bookings (start);
            CREATE TABLE IF NOT EXISTS closed_days (day TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS clients (user_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, first_seen INTEGER);
        """)

    def touch_client(self, uid: int, name: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO clients VALUES (?, ?, '', ?)", (uid, name, int(time.time())))
        self.conn.commit()

    def phone(self, uid: int) -> str:
        row = self.conn.execute("SELECT phone FROM clients WHERE user_id = ?", (uid,)).fetchone()
        return row[0] if row else ""

    def set_phone(self, uid: int, phone: str) -> None:
        self.conn.execute("UPDATE clients SET phone = ? WHERE user_id = ?", (phone, uid))
        self.conn.commit()

    def busy(self, master: str, start: int, end: int) -> bool:
        """True if any active booking of this master (or of anyone when master is '') overlaps [start, end)."""
        q = "SELECT 1 FROM bookings WHERE status = 'active' AND start < ? AND start + minutes * 60 > ?"
        args = [end, start]
        if master:
            q += " AND master = ?"
            args.append(master)
        return self.conn.execute(q, args).fetchone() is not None

    def add(self, uid, name, phone, service, master, start, minutes) -> int:
        cur = self.conn.execute(
            "INSERT INTO bookings (user_id, name, phone, service, master, start, minutes, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, name, phone, service, master, start, minutes, int(time.time())))
        self.conn.commit()
        return cur.lastrowid

    def get(self, bid: int):
        row = self.conn.execute("SELECT id, user_id, name, phone, service, master, start, minutes, status FROM bookings WHERE id = ?",
                                (bid,)).fetchone()
        keys = ("id", "user_id", "name", "phone", "service", "master", "start", "minutes", "status")
        return dict(zip(keys, row)) if row else None

    def cancel(self, bid: int) -> bool:
        cur = self.conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status = 'active'", (bid,))
        self.conn.commit()
        return cur.rowcount == 1

    def upcoming(self, uid: int = None, frm: int = None, to: int = None) -> list:
        q, args = "SELECT id FROM bookings WHERE status = 'active' AND start >= ?", [frm if frm is not None else int(time.time())]
        if to is not None:
            q += " AND start < ?"
            args.append(to)
        if uid is not None:
            q += " AND user_id = ?"
            args.append(uid)
        return [self.get(r[0]) for r in self.conn.execute(q + " ORDER BY start", args)]

    def due_reminders(self, now: int, ahead_minutes: int) -> list:
        rows = self.conn.execute("SELECT id FROM bookings WHERE status = 'active' AND reminded = 0 AND user_id != 0 AND start > ? AND start <= ?",
                                 (now, now + ahead_minutes * 60)).fetchall()
        return [self.get(r[0]) for r in rows]

    def mark_reminded(self, bid: int) -> None:
        self.conn.execute("UPDATE bookings SET reminded = 1 WHERE id = ?", (bid,))
        self.conn.commit()

    def set_closed(self, day: str, closed: bool) -> None:
        if closed:
            self.conn.execute("INSERT OR IGNORE INTO closed_days VALUES (?)", (day,))
        else:
            self.conn.execute("DELETE FROM closed_days WHERE day = ?", (day,))
        self.conn.commit()

    def is_closed(self, day: str) -> bool:
        return self.conn.execute("SELECT 1 FROM closed_days WHERE day = ?", (day,)).fetchone() is not None

    def stats(self, now: int) -> dict:
        c = self.conn
        week = now - 7 * 86400
        return {
            "clients": c.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
            "bookings_week": c.execute("SELECT COUNT(*) FROM bookings WHERE created >= ? AND user_id != 0", (week,)).fetchone()[0],
            "cancelled_week": c.execute("SELECT COUNT(*) FROM bookings WHERE created >= ? AND status = 'cancelled' AND user_id != 0", (week,)).fetchone()[0],
            "upcoming": c.execute("SELECT COUNT(*) FROM bookings WHERE status = 'active' AND user_id != 0 AND start >= ?", (now,)).fetchone()[0],
        }
