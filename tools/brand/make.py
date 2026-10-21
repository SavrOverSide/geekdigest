"""Avatars for the three bots and four channels: same look as the cards (gradient, glow, grain, emblem rings)."""
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONT = Path("/app/assets/fonts/Inter-ExtraBold.otf")
FONT_B = Path("/app/assets/fonts/Inter-Bold.otf")
S = 1024

# name -> (letter, top, bottom, accent, glow1, glow2, badge)
BRANDS = {
    "geekdigests": ("G", (10, 12, 28), (24, 14, 46), (255, 200, 90), (90, 70, 255), (255, 70, 150), "RU"),
    "geekdigest_eng": ("G", (10, 12, 28), (24, 14, 46), (120, 230, 255), (60, 110, 255), (170, 70, 255), "EN"),
    "wordlores": ("W", (6, 22, 30), (10, 40, 52), (255, 214, 120), (30, 170, 200), (255, 120, 60), ""),
    "ideaforges": ("I", (20, 8, 38), (40, 12, 60), (120, 240, 255), (130, 60, 255), (255, 70, 170), ""),
}


def over(img, layer):
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def make(name: str) -> Image.Image:
    letter, top, bottom, accent, g1, g2, badge = BRANDS[name]
    rnd = random.Random(name)
    strip = Image.new("RGB", (1, S))
    for y in range(S):
        t = y / (S - 1)
        strip.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    img = strip.resize((S, S))
    blobs = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blobs)
    bd.ellipse((-260, -260, 560, 560), fill=g1 + (150,))
    bd.ellipse((520, 560, 1300, 1340), fill=g2 + (130,))
    img = over(img, blobs.filter(ImageFilter.GaussianBlur(120)))
    grain = Image.effect_noise((S, S), 48).convert("RGB")
    img = Image.blend(img, ImageChops.overlay(img, grain), 0.2)

    # emblem rings at 2x for smooth lines
    big = Image.new("RGBA", (S * 2, S * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    c = S
    d.ellipse((c - 780, c - 780, c + 780, c + 780), outline=accent + (200,), width=10)
    for k in range(60):                      # ticks
        a = k * math.tau / 60
        r1, r2 = 780 - (30 if k % 5 == 0 else 14), 780
        d.line((c + r1 * math.cos(a), c + r1 * math.sin(a), c + r2 * math.cos(a), c + r2 * math.sin(a)), fill=accent + (150,), width=6)
    for sides, rad, rot in ((7, 560, rnd.random()), (5, 400, rnd.random())):
        pts = [(c + rad * math.cos(rot + i * math.tau / sides), c + rad * math.sin(rot + i * math.tau / sides)) for i in range(sides)]
        d.polygon(pts, outline=accent + (140,), width=8)
    for k in range(3):                       # orbiting dots
        a = rnd.random() * math.tau
        d.ellipse((c + 780 * math.cos(a) - 22, c + 780 * math.sin(a) - 22, c + 780 * math.cos(a) + 22, c + 780 * math.sin(a) + 22), fill=accent + (255,))
    rings = big.resize((S, S), Image.LANCZOS)
    glow = rings.filter(ImageFilter.GaussianBlur(18))
    img = over(img, glow)
    img = over(img, rings)

    # letter
    d2 = ImageDraw.Draw(img, "RGBA")
    f = ImageFont.truetype(str(FONT), 520)
    d2.text((S // 2, S // 2 + 10), letter, font=f, fill=(255, 255, 255, 255), anchor="mm")
    if badge:
        fb = ImageFont.truetype(str(FONT_B), 78)
        w = d2.textlength(badge, font=fb) + 70
        x1, y1 = S // 2 - w / 2, 800
        d2.rounded_rectangle((x1, y1, x1 + w, y1 + 120), 60, fill=accent + (255,))
        d2.text((S // 2, y1 + 62), badge, font=fb, fill=top + (255,), anchor="mm")
    return img


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    for n in BRANDS:
        make(n).resize((640, 640), Image.LANCZOS).save(out / f"{n}.jpg", quality=93)
        print(n)
