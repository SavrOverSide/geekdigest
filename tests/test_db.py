import pathlib
import sys
import tempfile
import time
import unittest
from datetime import timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import common.config as cfg
import common.db as dbm
from common import growth


class StoreTests(unittest.TestCase):
    def setUp(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        cfg.DATA = tmp
        dbm.DATA = tmp
        self.s = dbm.Store("t")

    def test_ensure_user_reports_new_only_once(self):
        self.assertTrue(self.s.ensure_user(1))
        self.assertFalse(self.s.ensure_user(1))

    def test_take_free_then_credits_then_denied(self):
        self.assertTrue(self.s.take(1, 2))
        self.assertTrue(self.s.take(1, 2))
        self.assertFalse(self.s.take(1, 2))
        self.s.add_credits(1, 1)
        self.assertTrue(self.s.take(1, 2))
        self.assertFalse(self.s.take(1, 2))
        self.assertEqual(self.s.free_left(1, 2), 0)

    def test_premium_is_unlimited_and_stacks(self):
        self.s.add_premium(1, 30)
        for _ in range(50):
            self.assertTrue(self.s.take(1, 1))
        first = self.s.premium_until(1)
        self.s.add_premium(1, 30)
        self.assertAlmostEqual(self.s.premium_until(1) - first, 30 * 86400, delta=2)

    def test_streak_grows_resets_and_forgives(self):
        s = self.s
        self.assertEqual(s.streak_hit(1)[:3], (1, 1, True))
        self.assertEqual(s.streak_hit(1)[:3], (1, 1, False))  # same day: no growth

        def backdate(days):
            d = (dbm.today() - timedelta(days=days)).isoformat()
            s.conn.execute("UPDATE streaks SET last_day = ? WHERE user_id = 1", (d,))

        backdate(1)
        self.assertEqual(s.streak_hit(1)[0], 2)
        backdate(2)  # missed one day: broken without grace
        self.assertEqual(s.streak_hit(1)[0], 1)
        s.conn.execute("UPDATE streaks SET streak = 5, best = 5 WHERE user_id = 1")
        backdate(2)  # missed one day: forgiven with grace=1
        self.assertEqual(s.streak_hit(1, grace=1)[0], 6)
        backdate(4)
        self.assertEqual(s.streak_hit(1, grace=1)[0], 1)
        self.assertEqual(s.streak(1)[1], 6)  # best is kept

    def test_streak_view_expires(self):
        self.s.streak_hit(1)
        self.assertEqual(self.s.streak(1)[0], 1)
        old = (dbm.today() - timedelta(days=3)).isoformat()
        self.s.conn.execute("UPDATE streaks SET last_day = ? WHERE user_id = 1", (old,))
        self.assertEqual(self.s.streak(1)[0], 0)

    def test_stats(self):
        self.s.add_answer(1, True)
        self.s.add_answer(1, False)
        self.s.add_answer(1, True)
        self.s.finish_round(1)
        self.assertEqual(self.s.user_stats(1), {"correct": 2, "answered": 3, "rounds": 1})
        self.assertEqual(self.s.user_stats(99), {"correct": 0, "answered": 0, "rounds": 0})

    def test_referrals(self):
        s = self.s
        s.ensure_user(1)
        self.assertFalse(s.add_referral(1, 1))      # self
        self.assertFalse(s.add_referral(2, 777))    # unknown inviter
        self.assertTrue(s.add_referral(2, 1))
        self.assertFalse(s.add_referral(2, 1))      # repeat
        self.assertEqual(s.referrals(1), 1)

    def test_saved_items(self):
        s = self.s
        self.assertTrue(s.save_item(1, "a", "x"))
        self.assertFalse(s.save_item(1, "a", "x"))
        s.save_item(1, "b", "y")
        self.assertEqual([k for k, _ in s.list_saved(1)], ["b", "a"])  # newest first
        self.assertEqual(s.count_saved(1), 2)
        s.delete_saved(1, "a")
        self.assertFalse(s.has_saved(1, "a"))

    def test_subscriptions(self):
        s = self.s
        s.set_sub(1, True)
        s.set_sub(2, True)
        s.set_sub(1, False)
        self.assertEqual(s.subs(), [2])
        self.assertTrue(s.is_sub(2))

    def test_payments_are_idempotent(self):
        self.assertTrue(self.s.record_payment("c1", 1, 99, "premium_30"))
        self.assertFalse(self.s.record_payment("c1", 1, 99, "premium_30"))
        self.assertIn("99 ⭐ всего", self.s.stats_text())

    def test_dashboard_numbers(self):
        s = self.s
        for uid in (1, 2, 3):
            s.ensure_user(uid)
        s.ensure_user(1)                                  # repeated activity on one day counts once
        s.record_payment("a", 1, 99, "premium_30")
        s.record_payment("b", 1, 799, "premium_365")
        s.record_payment("c", 2, 25, "pack_50")
        s.add_referral(3, 1)
        s.set_sub(2, True)
        text = s.stats_text()
        self.assertIn("Людей всего: 3", text)
        self.assertIn("Новых: сегодня 3", text)
        self.assertIn("Активных: сегодня 3", text)
        self.assertIn("923 ⭐ всего", text)
        self.assertIn("покупателей: 2 (66.7% от всех)", text)
        self.assertIn("premium_365: 1 шт, 799 ⭐", text)
        self.assertIn("Подписчиков на рассылку: 1", text)
        self.assertIn("Приглашений по ссылкам: 1", text)

    def test_day1_return_rate(self):
        s = self.s
        yesterday = int(time.time()) - 86400
        for uid in (10, 11):
            s.ensure_user(uid)
            s.conn.execute("UPDATE users SET created = ? WHERE id = ?", (yesterday, uid))
        s.conn.commit()                                   # both signed up yesterday; only 10 shows up today
        s.conn.execute("DELETE FROM activity WHERE user_id = 11")
        s.conn.commit()
        self.assertIn("1 из 2", s.stats_text())

    def test_migrates_old_database(self):
        import sqlite3
        path = cfg.DATA / "old.sqlite3"
        c = sqlite3.connect(path)
        c.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY, premium_until INTEGER DEFAULT 0, credits INTEGER DEFAULT 0, "
                        "used_day TEXT DEFAULT '', used INTEGER DEFAULT 0, created INTEGER);"
                        "INSERT INTO users (id, premium_until, created) VALUES (5, 9999999999, 1);")
        c.commit()
        c.close()
        s = dbm.Store("old")
        self.assertTrue(s.is_premium(5))
        s.set_lang(5, "ru")
        self.assertEqual(s.get_lang(5), "ru")


class GrowthTests(unittest.TestCase):
    def test_start_arg_and_ref(self):
        self.assertEqual(growth.start_arg("/start ref_42"), "ref_42")
        self.assertEqual(growth.start_arg("/start"), "")
        self.assertEqual(growth.parse_ref("ref_42"), 42)
        self.assertIsNone(growth.parse_ref("ref_x"))
        self.assertIsNone(growth.parse_ref("quiz"))

    def test_links(self):
        self.assertEqual(growth.ref_link("wordlore_bot", 7), "https://t.me/wordlore_bot?start=ref_7")
        u = growth.share_url("https://t.me/b?start=ref_7", "Привет мир")
        self.assertTrue(u.startswith("https://t.me/share/url?url=https%3A%2F%2Ft.me%2Fb%3Fstart%3Dref_7&text="))
        self.assertNotIn(" ", u)

    def test_promo_excludes_own(self):
        p = growth.promo("words")
        self.assertIn("@geekdigests", p)
        self.assertNotIn("@wordlores", p)


if __name__ == "__main__":
    unittest.main()
