"""Compose the full dashboard image from data."""
from datetime import datetime

from PIL import Image, ImageDraw

import draw_left as left
import draw_right as right
from alerts import build_alerts
from config import HEIGHT, TAP_MARKER_SECONDS, TOUCH_DEBUG, WIDTH
from draw_home import draw_home
from draw_music import draw_music, draw_tap_marker
from draw_common import INK, MID, Draw, font, stripes, truncate, vertical_stripes

FOOTER_TOP = 1196
KINDLE_SEEN_SECONDS = 300
GRAY_LEVELS = 16  # Kindle Oasis panel depth


def kindle_battery(kindle: dict | None, now: datetime) -> tuple[str, int | None]:
    """('Kindle 84%', 84), or an offline/online label with no level."""
    if not kindle or (now - kindle["seen"]).total_seconds() > KINDLE_SEEN_SECONDS:
        return "Kindle offline", None
    level = kindle.get("battery")
    return (f"Kindle {level}%", level) if level is not None else ("Kindle online", None)


def battery_icon(d: Draw, right: float, cy: float, level: int | None, color: int) -> float:
    """Battery outline filled to `level`; returns its left edge. Empty outline when unknown."""
    w, h = 40, 20
    left, top = right - w - 5, cy - h / 2
    d.rounded_rectangle((left, top, left + w, top + h), radius=4, outline=color, width=2)
    d.rectangle((left + w, cy - 4, left + w + 4, cy + 4), fill=color)
    if level is not None and level > 0:
        d.rounded_rectangle((left + 4, top + 4, left + 4 + (w - 8) * min(level, 100) / 100, top + h - 4), radius=2, fill=color)
    return left


def draw_status(d: Draw, level: int | None, color: int) -> float:
    """Battery icon at the right end of the footer; returns its left edge."""
    return battery_icon(d, WIDTH - 56, FOOTER_TOP + 34, level, color)


def draw_footer(d: Draw, alerts: list[str], level: int | None = None) -> None:
    """Black bar with alerts when something needs attention; quiet line otherwise. Battery icon on the right."""
    if alerts:  # rounded 70s pill bar, inset from the edges
        d.rounded_rectangle((28, FOOTER_TOP + 4, WIDTH - 28, HEIGHT - 8), radius=(HEIGHT - 12 - FOOTER_TOP) / 2, fill=INK)
        status_left = draw_status(d, level, 255)
        text = "  ·  ".join(alerts)
        d.text((56, FOOTER_TOP + 34), truncate(d, text, font(26, bold=True), status_left - 30 - 56),
               font=font(26, bold=True), fill=255, anchor="lm")
        return
    stripes(d, 56, WIDTH - 56, FOOTER_TOP - 6, thickness=4, gap=3)
    d.text((56, FOOTER_TOP + 34), "All clear", font=font(22, bold=True), fill=MID, anchor="lm")
    left = draw_status(d, level, MID)
    d.text((left - 18, FOOTER_TOP + 34), "US & VN stocks delayed ~15 min", font=font(20), fill=MID, anchor="rm")


def quantize(img: Image.Image) -> Image.Image:
    """Snap to the panel's 16 grays so the Kindle doesn't dither text and lines into mush."""
    step = 256 // GRAY_LEVELS
    return img.point(lambda v: min(255, v // step * (255 // (GRAY_LEVELS - 1))))


def render(data: dict, now: datetime) -> Image.Image:
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    d = ImageDraw.Draw(img)
    stale = data.get("_stale", set())
    weather = data.get("weather")

    left.draw_clock(d, now)
    left.draw_current(d, weather, data.get("aqi"), stale)
    left.draw_hourly(d, (weather or {}).get("hourly", []))
    left.draw_forecast(d, weather)
    left.draw_tides(d, data.get("tides"), now, "tides" in stale)
    left.draw_claude_usage(d, data.get("claude"), now, "claude" in stale)

    vertical_stripes(d, 752, 46, FOOTER_TOP - 20)
    right.draw_markets(d, data.get("markets"), "markets" in stale)
    right.draw_charts(d, data.get("charts"), data.get("fx"), stale)
    music = data.get("music") or {}
    draw_music(img, d, music.get("track"), music.get("host"))
    right.draw_econ(d, data.get("econ"), now, "econ" in stale)
    right.draw_news(d, data.get("news"), "news" in stale)

    tap = data.get("last_tap")
    if TOUCH_DEBUG and tap and (now - tap["time"]).total_seconds() < TAP_MARKER_SECONDS:
        draw_tap_marker(d, tap["x"], tap["y"])
    _, level = kindle_battery(data.get("kindle"), now)
    draw_footer(d, build_alerts(data, now), level)
    return quantize(img)


def render_home(data: dict, now: datetime) -> tuple[Image.Image, list]:
    """The swipe-to page: AC + lights. Returns the image and its touch targets."""
    img = Image.new("L", (WIDTH, HEIGHT), 255)
    d = ImageDraw.Draw(img)
    targets = draw_home(d, data, now)
    tap = data.get("last_tap")
    if TOUCH_DEBUG and tap and (now - tap["time"]).total_seconds() < TAP_MARKER_SECONDS:
        draw_tap_marker(d, tap["x"], tap["y"])
    _, level = kindle_battery(data.get("kindle"), now)
    draw_footer(d, build_alerts(data, now), level)
    return quantize(img), targets
