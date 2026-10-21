# Источники дайджеста по языкам: (рубрика, RSS). Русский выпуск собирается из русскоязычных источников,
# английский из английских: перевод не нужен, поэтому ключ API не требуется.
FEEDS = {
    "ru": [
        ("🤖 ИИ", "https://habr.com/ru/rss/hubs/artificial_intelligence/articles/?fl=ru"),
        ("🤖 ИИ", "https://3dnews.ru/software/rss/"),
        ("💻 Техника", "https://www.ixbt.com/export/news/rss.xml"),
        ("💻 Техника", "https://habr.com/ru/rss/hubs/gadgets/articles/?fl=ru"),
        ("🎮 Игры", "https://3dnews.ru/games/rss/"),
        ("🎮 Игры", "https://dtf.ru/rss"),
        ("🔬 Наука", "https://nplus1.ru/rss"),
    ],
    "en": [
        ("🤖 AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
        ("🤖 AI", "https://huggingface.co/blog/feed.xml"),
        ("💻 Tech", "https://www.theverge.com/rss/index.xml"),
        ("💻 Tech", "https://arstechnica.com/feed/"),
        ("🎮 Games", "https://www.rockpapershotgun.com/feed"),
        ("🎮 Games", "https://www.gamedeveloper.com/rss.xml"),
        ("🔬 Science", "https://www.sciencedaily.com/rss/top/science.xml"),
    ],
}
