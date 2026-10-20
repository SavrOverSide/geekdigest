"""Cover picture for the daily digest: date, one headline per section, brand look."""
import io
import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H = 1080, 1350
PAD = 84
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
# section accent colours, cycled in order
ACCENTS = [(255, 120, 150), (120, 220, 255), (255, 200, 90), (150, 240, 160), (190, 150, 255)]


def font(name, size):
    return ImageFont.truetype(str(FONTS / f"Inter-{name}.otf"), size)


def wrap(draw, text, fnt, width, max_lines):
    lines, line = [], ""
    words = text.split()
    for i, word in enumerate(words):
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
            continue
        lines.append(line)
        line = word
        if len(lines) == max_lines:
            break
    else:
        lines.append(line)
        return lines
    # out of lines: finish the last one with an ellipsis
    last = lines[max_lines - 1]
    while last and draw.textlength(last + "…", font=fnt) > width:
        last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
    lines[max_lines - 1] = last + "…"
    return lines[:max_lines]


def over(img, layer):
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def render(sections: dict, summaries: dict, when: datetime, handle: str = "@geekdigests") -> bytes:
    top, bottom = (10, 12, 28), (24, 14, 46)
    strip = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / (H - 1)
        strip.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    img = strip.resize((W, H))
    blobs = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blobs)
    bd.ellipse((-200, -200, 640, 640), fill=(90, 70, 255, 120))
    bd.ellipse((560, 800, 1300, 1540), fill=(255, 70, 150, 100))
    img = over(img, blobs.filter(ImageFilter.GaussianBlur(140)))
    grain = Image.effect_noise((W, H), 48).convert("RGB")
    img = Image.blend(img, ImageChops.overlay(img, grain), 0.22)

    d = ImageDraw.Draw(img, "RGBA")
    white = (255, 255, 255, 255)
    d.rounded_rectangle((PAD, 80, PAD + 64, 144), 18, fill=(255, 200, 90, 255))
    d.text((PAD + 32, 112), "G", font=font("ExtraBold", 40), fill=top + (255,), anchor="mm")
    d.text((PAD + 86, 112), "ГИК-ДАЙДЖЕСТ", font=font("Bold", 30), fill=white, anchor="lm")
    date_s = f"{when.day} {MONTHS[when.month - 1]}".upper()
    f = font("SemiBold", 24)
    tw = d.textlength(date_s, font=f)
    d.rounded_rectangle((W - PAD - tw - 48, 82, W - PAD, 142), 30, fill=(255, 200, 90, 36), outline=(255, 200, 90, 150), width=2)
    d.text((W - PAD - 24, 112), date_s, font=f, fill=(255, 200, 90, 255), anchor="rm")

    d.text((PAD, 230), "Что нового", font=font("ExtraBold", 120), fill=white)
    d.text((PAD, 360), "сегодня", font=font("ExtraBold", 120), fill=(255, 200, 90, 255))

    items = list(sections.items())[:5]
    y = 560
    room = H - 170 - y
    step = room // max(len(items), 1)
    fh, ft = font("Medium", 34), font("Bold", 22)
    for n, (name, news) in enumerate(items):
        accent = ACCENTS[n % len(ACCENTS)]
        label = re.sub(r"^[\W_]+", "", name).upper()
        d.rounded_rectangle((PAD, y, PAD + 10, y + step - 30), 5, fill=accent + (255,))
        d.text((PAD + 36, y), label, font=ft, fill=accent + (255,))
        first = news[0]
        text = summaries.get(first["link"]) or first["title"]
        for k, line in enumerate(wrap(d, text, fh, W - 2 * PAD - 40, 2)):
            d.text((PAD + 36, y + 38 + k * 46), line, font=fh, fill=(255, 255, 255, 240))
        if len(news) > 1:
            d.text((W - PAD, y), f"+{len(news) - 1}", font=ft, fill=(255, 255, 255, 120), anchor="ra")
        y += step

    d.line((PAD, H - 140, W - PAD, H - 140), fill=(255, 255, 255, 40), width=2)
    d.text((PAD, H - 90), handle, font=font("Bold", 36), fill=(255, 200, 90, 255), anchor="lm")
    d.text((W - PAD, H - 90), "ИИ · игры · техника · наука", font=font("Medium", 26), fill=(255, 255, 255, 150), anchor="rm")

    out = io.BytesIO()
    img.save(out, "JPEG", quality=92, optimize=True)
    return out.getvalue()
