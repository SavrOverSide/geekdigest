from . import _Pred


def Command(name):
    return _Pred(lambda m: isinstance(getattr(m, "text", None), str) and bool(m.text.split()) and m.text.split()[0].split("@")[0] == f"/{name}")


def CommandStart():
    return Command("start")
