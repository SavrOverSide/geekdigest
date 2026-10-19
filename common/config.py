import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def lang_of(user) -> str:
    code = (getattr(user, "language_code", None) or "").lower()
    return "ru" if code.startswith(("ru", "uk", "be", "kk")) else "en"
