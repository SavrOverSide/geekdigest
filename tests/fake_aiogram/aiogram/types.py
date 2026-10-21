class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class BufferedInputFile(_Obj):
    def __init__(self, data, filename="f"):
        self.data, self.filename = data, filename


class InlineKeyboardButton(_Obj):
    def __init__(self, text, callback_data=None, url=None):
        self.text, self.callback_data, self.url = text, callback_data, url


class InlineKeyboardMarkup(_Obj):
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class LabeledPrice(_Obj):
    def __init__(self, label, amount):
        self.label, self.amount = label, amount


class LinkPreviewOptions(_Obj):
    pass


class User(_Obj):
    def __init__(self, id, language_code="ru", first_name=None):
        self.id, self.language_code, self.first_name = id, language_code, first_name


class Message(_Obj):
    """Records everything the bot does with it in `.out` (answer, answer_photo, edit_text)."""

    def __init__(self, from_user=None, text="", bot=None, successful_payment=None):
        self.from_user, self.text, self.bot = from_user, text, bot
        self.chat = _Obj(id=getattr(from_user, "id", 0))
        self.successful_payment = successful_payment
        self.out = []

    async def answer(self, text, **kw):
        self.out.append({"kind": "text", "text": text, **kw})
        return self

    async def answer_photo(self, photo, **kw):
        self.out.append({"kind": "photo", "photo": photo, **kw})
        return self

    async def edit_text(self, text, **kw):
        self.out.append({"kind": "edit", "text": text, **kw})
        return self


class CallbackQuery(_Obj):
    def __init__(self, from_user, data, message, bot):
        self.from_user, self.data, self.message, self.bot = from_user, data, message, bot
        self.answers = []

    async def answer(self, text=None, show_alert=False, **kw):
        self.answers.append({"text": text, "alert": show_alert})


class PreCheckoutQuery(_Obj):
    def __init__(self, invoice_payload, total_amount):
        self.invoice_payload, self.total_amount = invoice_payload, total_amount
        self.result = None

    async def answer(self, ok, error_message=None):
        self.result = (ok, error_message)


class BotCommand:
    def __init__(self, command, description):
        self.command, self.description = command, description


class LinkPreviewOptions(_Obj):
    def __init__(self, **kw):
        self.__dict__.update(kw)
