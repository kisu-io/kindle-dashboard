"""Fonts and small drawing helpers shared by the dashboard panels."""
import logging
from functools import lru_cache
from pathlib import Path

from PIL import ImageDraw, ImageFont

from config import ROOT
from icons import trend_icon

INK, DARK, MID, LIGHT, FAINT = 0, 60, 110, 150, 200  # grays that survive the 16-level e-ink quantize
# Vietnamese-capable fonts, best first: bundled Be Vietnam Pro, macOS Arial, Debian/Pi DejaVu
FONT_FILES = {
    False: [ROOT / "fonts/BeVietnamPro-Regular.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    True: [ROOT / "fonts/PaytoneOne-Regular.ttf", ROOT / "fonts/BeVietnamPro-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}
log = logging.getLogger("dashboard")
Draw = ImageDraw.ImageDraw


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in FONT_FILES[bold]:
        if Path(path).exists():
            return ImageFont.truetype(str(path), size)
    log.warning("No Vietnamese-capable font found; accents may not render")
    return ImageFont.load_default(size=size)


CLOCK_FONT_FILE = ROOT / "fonts/Righteous-Regular.ttf"  # retro 70s, digits only


@lru_cache(maxsize=None)
def clock_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(CLOCK_FONT_FILE), size) if CLOCK_FONT_FILE.exists() else font(size, bold=True)


def truncate(d: Draw, text: str, fnt, max_width: float) -> str:
    if d.textlength(text, font=fnt) <= max_width:
        return text
    while text and d.textlength(text + "…", font=fnt) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


PILL_H = 26


def pill(d: Draw, x: float, y: float, text: str, size: int = 17, is_filled: bool = True) -> float:
    """70s-style rounded label; returns its right edge."""
    fnt = font(size, bold=True)
    w = d.textlength(text, font=fnt) + 24
    box = (x, y, x + w, y + PILL_H)
    if is_filled:
        d.rounded_rectangle(box, radius=PILL_H / 2, fill=INK)
    else:
        d.rounded_rectangle(box, radius=PILL_H / 2, outline=INK, width=2)
    d.text((x + 12, y + PILL_H / 2), text, font=fnt, fill=255 if is_filled else INK, anchor="lm")
    return x + w


def section_title(d: Draw, x: float, y: float, text: str, is_stale: bool = False) -> None:
    """Black pill label; stale sections get an outlined 'OFFLINE' pill so frozen data is obvious."""
    title, _, note = text.partition("  ·  ")
    right = pill(d, x, y - 2, title)
    if note:
        d.text((right + 10, y + 11), note, font=font(18), fill=MID, anchor="lm")
        right += 10 + d.textlength(note, font=font(18))
    if is_stale:
        pill(d, right + 10, y - 2, "OFFLINE", size=15, is_filled=False)


STRIPE_FILLS = (INK, MID, FAINT)  # the classic triple racing stripe, in grays


def stripes(d: Draw, x0: float, x1: float, y: float, thickness: int = 6, gap: int = 4) -> None:
    for i, fill in enumerate(STRIPE_FILLS):
        top = y + i * (thickness + gap)
        d.rounded_rectangle((x0, top, x1, top + thickness), radius=thickness / 2, fill=fill)


def vertical_stripes(d: Draw, x: float, y0: float, y1: float, thickness: int = 4, gap: int = 4) -> None:
    for i, fill in enumerate(STRIPE_FILLS):
        left = x + i * (thickness + gap)
        d.rounded_rectangle((left, y0, left + thickness, y1), radius=thickness / 2, fill=fill)


def price_text(price: float) -> str:
    return f"{price:,.0f}" if price >= 10_000 else f"{price:,.2f}"


def pct_with_trend(d: Draw, right_x: float, y: float, pct: float, size: int = 22) -> None:
    """Right-aligned '+1.23%' with a ▲/▽ drawn just left of it."""
    text, fnt = f"{pct:+.2f}%", font(size)
    d.text((right_x, y), text, font=fnt, fill=INK, anchor="ra")
    tri = size * 0.75
    trend_icon(d, right_x - d.textlength(text, font=fnt) - tri - 8, y + size * 0.62, tri, pct >= 0)


def sparkline(d: Draw, values: list[float], box: tuple[float, float, float, float], width: int = 2,
              baseline: float | None = None) -> None:
    """Line chart scaled into box; optional dotted baseline (e.g. previous close)."""
    if len(values) < 2:
        return
    left, top, right, bottom = box
    lo, hi = min(values + ([baseline] if baseline is not None else [])), max(values + ([baseline] if baseline is not None else []))
    span = (hi - lo) or 1

    def y_of(v: float) -> float:
        return bottom - (v - lo) / span * (bottom - top)

    if baseline is not None:
        by = y_of(baseline)
        for x in range(int(left), int(right), 8):
            d.line((x, by, min(x + 3, right), by), fill=LIGHT, width=1)
    step = (right - left) / (len(values) - 1)
    d.line([(left + i * step, y_of(v)) for i, v in enumerate(values)], fill=INK, width=width, joint="curve")
