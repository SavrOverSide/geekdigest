"""A tiny stand-in for aiogram 3 used only by the offline tests (the real library cannot be installed in the
agent's sandbox). It models routing, filters, keyboards, messages and a recording bot, nothing more."""
import inspect


class _Pred:
    def __init__(self, fn):
        self.fn = fn

    def __call__(self, obj):
        return self.fn(obj)


class _Field:
    def __init__(self, path):
        self.path = path

    def _get(self, obj):
        for p in self.path:
            obj = getattr(obj, p, None)
        return obj

    def startswith(self, prefix):
        return _Pred(lambda o: isinstance(self._get(o), str) and self._get(o).startswith(prefix))

    def __eq__(self, other):  # F.data == "x"
        return _Pred(lambda o: self._get(o) == other)

    __hash__ = object.__hash__

    def __getattr__(self, name):
        return _Field(self.path + [name])

    def __bool__(self):
        return True


class _F:
    def __getattr__(self, name):
        field = _Field([name])
        return _TruthyField(field)


class _TruthyField(_Pred):
    """F.successful_payment is used bare as a filter (truthy attribute) but F.data.startswith(...) is chained."""

    def __init__(self, field):
        super().__init__(lambda o: bool(field._get(o)))
        self._field = field

    def startswith(self, prefix):
        return self._field.startswith(prefix)

    def __eq__(self, other):  # F.data == "x"
        return self._field == other

    __hash__ = object.__hash__

    def __getattr__(self, name):
        return getattr(self._field, name)


F = _F()


class Router:
    def __init__(self):
        self.handlers = []   # (kind, filters, fn)
        self.children = []

    def _reg(self, kind, filters):
        def deco(fn):
            self.handlers.append((kind, filters, fn))
            return fn
        return deco

    def message(self, *filters):
        return self._reg("message", filters)

    def callback_query(self, *filters):
        return self._reg("callback_query", filters)

    def pre_checkout_query(self, *filters):
        return self._reg("pre_checkout_query", filters)

    def include_router(self, r):
        self.children.append(r)

    async def feed(self, kind, obj):
        """Runs the first matching handler (own handlers in order, then child routers). Returns the handler or None."""
        for k, filters, fn in self.handlers:
            if k == kind and all(f(obj) for f in filters):
                res = fn(obj)
                if inspect.isawaitable(res):
                    await res
                return fn
        for child in self.children:
            fn = await child.feed(kind, obj)
            if fn:
                return fn
        return None


class Bot:
    def __init__(self, token="", **kw):
        self.token = token
        self.sent = []
        self.fail_for = set()

    async def me(self):
        return type("Me", (), {"username": "test_bot", "id": 1})()

    get_me = me

    async def _record(self, kind, chat_id, **kw):
        if chat_id in self.fail_for:
            raise type("TelegramForbiddenError", (Exception,), {})("blocked")
        self.sent.append({"kind": kind, "chat_id": chat_id, **kw})

    async def send_message(self, chat_id, text, **kw):
        await self._record("message", chat_id, text=text, **kw)

    async def send_photo(self, chat_id, photo, **kw):
        await self._record("photo", chat_id, photo=photo, **kw)

    async def send_document(self, chat_id, document, **kw):
        await self._record("document", chat_id, document=document, **kw)

    async def set_my_commands(self, commands, language_code=None):
        self.profile = getattr(self, "profile", [])
        self.profile.append(("commands", language_code, commands))

    async def set_my_description(self, description, language_code=None):
        self.profile.append(("description", language_code, description))

    async def set_my_short_description(self, short_description, language_code=None):
        self.profile.append(("short", language_code, short_description))

    async def send_invoice(self, chat_id, **kw):
        await self._record("invoice", chat_id, **kw)

    @property
    def session(self):
        return type("S", (), {"close": staticmethod(lambda: _noop())})()


async def _noop():
    return None


class Dispatcher(Router):
    async def start_polling(self, bot):
        return None
