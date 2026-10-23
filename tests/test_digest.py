import json
import time
import unittest

from tests import harness  # noqa: F401  (puts the fake aiogram on sys.path first)
from tests.harness import Chat, assert_buttons_routable
from aiogram import Bot

import common.config as cfg
from digest import digest as dg
from digest.bot import router, store

BOT = Bot("x")


def chat(uid, lang="ru"):
    return Chat(router, BOT, uid, lang)


def sections(lang):
    word = "Новость" if lang == "ru" else "Story"
    return {("🤖 ИИ" if lang == "ru" else "🤖 AI"): [{"title": f"{word} {n}", "summary": "", "link": f"https://x/{lang}/{n}"} for n in range(3)]}


class Bot_(unittest.IsolatedAsyncioTestCase):
    async def test_start_answers_in_both_languages_with_working_buttons(self):
        for uid, lg, word in ((1, "ru", "Каждое утро"), (2, "en", "Every morning")):
            c = chat(uid, lg)
            await c.say("/start")
            self.assertIn(word, c.last()["text"])
            assert_buttons_routable(self, c)
            urls = [b.url for b in c.buttons() if b.url]
            self.assertIn("https://t.me/wordlore_bot", urls)
            self.assertTrue(any("geekdigests" in u for u in urls))

    async def test_subscribe_and_switch_language(self):
        c = chat(10)
        await c.say("/start")
        await c.press("sub")
        self.assertTrue(store.is_sub(10))
        await c.press("lang")
        self.assertEqual(store.get_lang(10), "en")
        self.assertIn("Every morning", c.last()["text"])
        await c.say("/sub")
        self.assertFalse(store.is_sub(10))

    async def test_stats_for_owner_only(self):
        import digest.bot as mod
        mod.env = lambda name, default="": {"OWNER_ID": "77"}.get(name, default)
        c = chat(77)
        await c.say("/stats")
        self.assertIn("Людей всего", c.last()["text"])
        d = chat(78)
        n = len(d.log)
        await d.say("/stats")
        self.assertEqual(len(d.log), n)

    async def test_stale_button(self):
        r = await chat(11).press("whatever")
        self.assertEqual(r.handler.__name__, "stale")


class Editions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sent = []
        self._orig = (dg.collect, dg.Bot, dg.DATA, dg.render_cover, dg.env)
        dg.collect = lambda seen, lang="ru": sections(lang)
        dg.render_cover = lambda *a, **k: b"JPEG"
        dg.env = lambda name, default="": {"CHANNEL": "@ru_chan", "CHANNEL_EN": "@en_chan"}.get(name, default)
        import tempfile, pathlib
        dg.DATA = pathlib.Path(tempfile.mkdtemp())
        self.bot = Bot("x")
        dg.Bot = lambda token: self.bot

    def tearDown(self):
        dg.collect, dg.Bot, dg.DATA, dg.render_cover, dg.env = self._orig

    async def test_each_language_gets_its_own_edition(self):
        for uid, lg in ((20, "ru"), (21, "en"), (22, "ru"), (23, "en")):
            store.ensure_user(uid)
            store.set_lang(uid, lg)
            store.set_sub(uid, True)
        self.bot.fail_for = {22}                       # one subscriber blocked the bot
        await dg.main(store=store)
        texts = {}
        for s in self.bot.sent:
            if s["kind"] == "message":
                texts.setdefault(s["chat_id"], s["text"])
        self.assertIn("Гик-дайджест", texts["@ru_chan"])
        self.assertIn("Geek Digest", texts["@en_chan"])
        self.assertIn("Новость", texts[20])
        self.assertIn("Story", texts[21])
        self.assertIn("Story", texts[23])
        self.assertNotIn(22, texts)
        self.assertFalse(store.is_sub(22))
        self.assertTrue(store.is_sub(20))
        # every edition sent its cover picture before the text
        photos = [s["chat_id"] for s in self.bot.sent if s["kind"] == "photo"]
        self.assertIn("@ru_chan", photos)
        self.assertIn(21, photos)
        # nothing is sent twice: links are remembered per language
        seen_ru = json.loads(dg.seen_file("ru").read_text())
        seen_en = json.loads(dg.seen_file("en").read_text())
        self.assertTrue(all("/ru/" in x for x in seen_ru) and all("/en/" in x for x in seen_en))

    async def test_no_english_channel_still_serves_english_subscribers(self):
        dg.env = lambda name, default="": {"CHANNEL": "@ru_chan"}.get(name, default)
        store.ensure_user(30)
        store.set_lang(30, "en")
        store.set_sub(30, True)
        await dg.main(store=store)
        self.assertTrue(any(s["chat_id"] == 30 for s in self.bot.sent))
        self.assertFalse(any(s["chat_id"] == "@en_chan" for s in self.bot.sent))

    async def test_nothing_new_sends_nothing(self):
        dg.collect = lambda seen, lang="ru": {}
        await dg.main(store=store)
        self.assertEqual(self.bot.sent, [])

    async def test_digest_text_fits_telegram(self):
        big = {"🤖 ИИ": [{"title": "т" * 140, "summary": "", "link": f"https://x/{n}"} for n in range(3)]}
        big.update({f"s{k}": big["🤖 ИИ"] for k in range(6)})
        self.assertLessEqual(len(dg.render(big, {}, "ru")), 4096)


class Feeds(unittest.TestCase):
    def test_russian_edition_uses_only_russian_sources_and_headers(self):
        from digest.feeds import FEEDS
        self.assertEqual(set(FEEDS), {"ru", "en"})
        for name, _ in FEEDS["ru"]:
            self.assertRegex(name, r"[А-Яа-я]")
        for name, _ in FEEDS["en"]:
            self.assertNotRegex(name, r"[А-Яа-я]")

    def test_collect_filters_seen_and_old(self):
        import feedparser
        now = time.time()
        fresh, old = time.gmtime(now - 3600), time.gmtime(now - 99 * 3600)
        entries = [{"link": "https://a/1", "title": "fresh", "summary": "<b>s</b>", "published_parsed": fresh},
                   {"link": "https://a/2", "title": "old", "summary": "", "published_parsed": old},
                   {"link": "https://a/3", "title": "seen", "summary": "", "published_parsed": fresh}]
        real = feedparser.parse
        feedparser.parse = lambda *a, **k: type("F", (), {"entries": [type("E", (dict,), {})(e) for e in entries]})()
        try:
            got = dg.collect({"https://a/3"}, "ru")
        finally:
            feedparser.parse = real
        links = [i["link"] for items in got.values() for i in items]
        self.assertIn("https://a/1", links)
        self.assertNotIn("https://a/2", links)
        self.assertNotIn("https://a/3", links)


class Report(unittest.TestCase):
    def test_report_counts_today_and_survives_missing_tables(self):
        import pathlib, sqlite3, tempfile
        from digest.report import report
        from common.daily import TZ
        from datetime import datetime
        root = pathlib.Path(tempfile.mkdtemp())
        now = datetime(2026, 10, 23, 20, 0, tzinfo=TZ).timestamp()
        db = root / "wordlore/data"
        db.mkdir(parents=True)
        c = sqlite3.connect(db / "lingvo.sqlite3")
        c.executescript("CREATE TABLE users (id INTEGER, created INTEGER); CREATE TABLE payments (stars INTEGER, at INTEGER);"
                        "CREATE TABLE activity (user_id INTEGER, day TEXT); CREATE TABLE subs (user_id INTEGER);")
        c.executemany("INSERT INTO users VALUES (?, ?)", [(1, now - 5 * 86400), (2, now - 3600), (3, now - 60)])
        c.executemany("INSERT INTO activity VALUES (?, ?)", [(1, "2026-10-23"), (2, "2026-10-23"), (1, "2026-10-20")])
        c.executemany("INSERT INTO payments VALUES (?, ?)", [(99, now - 100), (25, now - 3 * 86400)])
        c.commit()
        (root / "ideaforgegen/data").mkdir(parents=True)
        sqlite3.connect(root / "ideaforgegen/data/ideas.sqlite3").execute("CREATE TABLE users (id INTEGER, created INTEGER)")
        text = report(now, root)
        self.assertIn("👥 3 всего, +2 сегодня · активных сегодня 2, за 7 дней 2", text)
        self.assertIn("⭐ сегодня 99, всего 124", text)
        self.assertIn("Гик-дайджест: база не найдена", text)
        self.assertIn("Итого за день: +2 новых, 99 ⭐.", text)


class Backup(unittest.TestCase):
    def test_backup_contains_every_database_and_is_readable(self):
        import io, pathlib, sqlite3, tempfile, zipfile
        from digest.report import backup_zip
        root = pathlib.Path(tempfile.mkdtemp())
        own = pathlib.Path(tempfile.mkdtemp()) / "data"
        own.mkdir()
        for bot, name in (("wordlore", "lingvo"), ("ideaforgegen", "ideas")):
            (root / bot / "data").mkdir(parents=True)
            c = sqlite3.connect(root / bot / "data" / f"{name}.sqlite3")
            c.execute("CREATE TABLE payments (stars INTEGER)")
            c.execute("INSERT INTO payments VALUES (99)")
            c.commit()
        sqlite3.connect(own / "digest.sqlite3").execute("CREATE TABLE users (id INTEGER)")
        z = zipfile.ZipFile(io.BytesIO(backup_zip(root, own)))
        names = z.namelist()
        self.assertIn("wordlore/lingvo.sqlite3", names)
        self.assertIn("ideaforgegen/ideas.sqlite3", names)
        self.assertEqual(len(names), 3)
        out = pathlib.Path(tempfile.mkdtemp()) / "x.sqlite3"
        out.write_bytes(z.read("wordlore/lingvo.sqlite3"))
        self.assertEqual(sqlite3.connect(out).execute("SELECT stars FROM payments").fetchone()[0], 99)

    def test_backup_only_on_sundays(self):
        import asyncio
        from datetime import datetime
        from common.daily import TZ
        from digest.report import send_backup
        friday = datetime(2026, 10, 23, 21, 5, tzinfo=TZ).timestamp()
        self.assertFalse(asyncio.run(send_backup(Bot("x"), "1", friday)))


class Profile(unittest.IsolatedAsyncioTestCase):
    async def test_profile(self):
        from common.profile import setup_profile
        from digest.profile import COMMANDS, DESCRIPTION, SHORT
        b = Bot("x")
        await setup_profile(b, COMMANDS, DESCRIPTION, SHORT)
        self.assertEqual({p[1] for p in b.profile}, {None, "en", "ru"})


if __name__ == "__main__":
    unittest.main()


class Clean(unittest.TestCase):
    def test_double_encoded_entities_and_tags(self):
        self.assertEqual(dg.clean("&amp;quot;Hi&amp;quot; it&amp;#x27;s <b>fine</b>", 100), '"Hi" it\'s fine')
