"""Right column: market columns with sparklines, gold/DXY charts, USD/VND, US economic events, news."""
from datetime import datetime

import math

from config import CHARTS, HEADLINES, WIDTH
from news_filter import market_headlines
from quotes import quote_for
from draw_common import DARK, INK, MID, Draw, font, pct_with_trend, pill, price_text, section_title, sparkline, truncate

X0, X1 = 804, WIDTH - 56  # column bounds


def rule(d: Draw, y: float) -> None:
    d.rounded_rectangle((X0, y - 1, X1, y + 2), radius=2, fill=INK)


def draw_market_column(d: Draw, title: str, quotes: list[dict], x: float, w: float, is_stale: bool) -> None:
    section_title(d, x, 46, title, is_stale)
    if not quotes:
        d.text((x, 82), "Unavailable", font=font(22), fill=MID)
    for i, q in enumerate(quotes):
        y = 80 + i * 63
        d.text((x, y), q["symbol"], font=font(23, bold=True), fill=INK)
        pct_with_trend(d, x + w, y + 1, q["change_pct"], size=21)
        d.text((x, y + 30), price_text(q["price"]), font=font(21), fill=DARK)
        spark_left = x + w * 0.52
        sparkline(d, q["closes"], (spark_left, y + 32, x + w, y + 54), width=2)


def draw_markets(d: Draw, markets: dict | None, is_stale: bool) -> None:
    markets = markets or {}
    gap = 34
    w = (X1 - X0 - gap * (len(markets) - 1)) / max(1, len(markets))
    for i, (title, quotes) in enumerate(markets.items()):
        draw_market_column(d, title, quotes, X0 + i * (w + gap), w, is_stale)
    rule(d, 400)


CHART_TOP, CHART_H, CHART_GAP = 414, 150, 18
CHART_ROWS = max(1, math.ceil(len(CHARTS) / 2))  # 2 charts per row
FX_Y = CHART_TOP + CHART_ROWS * CHART_H + (CHART_ROWS - 1) * CHART_GAP + 14
MUSIC_TOP = FX_Y + 54  # Now Playing section (draw_music.py)
MUSIC_H = 148
ECON_TOP = MUSIC_TOP + MUSIC_H + 14
HEADLINES_TOP = ECON_TOP + 150


def draw_chart_box(d: Draw, series: dict, x: float, y: float, w: float, h: float) -> None:
    d.rounded_rectangle((x, y, x + w, y + h), radius=26, outline=INK, width=3)
    pad = 22
    d.text((x + pad, y + 10), series["symbol"], font=font(20, bold=True), fill=MID)
    d.text((x + w - pad, y + 12), "1M", font=font(18), fill=MID, anchor="ra")
    if "closes" not in series:
        d.text((x + pad, y + 44), "Unavailable", font=font(24), fill=MID)
        return
    d.text((x + pad, y + 36), price_text(series["price"]), font=font(28, bold=True), fill=INK)
    pct_with_trend(d, x + w - pad, y + 42, series["change_pct"], size=21)
    sparkline(d, series["closes"], (x + pad, y + 80, x + w - pad, y + h - 14), width=3)


def draw_charts(d: Draw, charts: list[dict] | None, fx: dict | None, stale: set) -> None:
    """2x2 grid of 1-month charts, then the USD/VND line."""
    gap_x = 28
    w = (X1 - X0 - gap_x) / 2
    for i, series in enumerate((charts or [])[:4]):
        row, col = divmod(i, 2)
        draw_chart_box(d, series, X0 + col * (w + gap_x), CHART_TOP + row * (CHART_H + CHART_GAP), w, CHART_H)
    y = FX_Y
    label_right = pill(d, X0, y + 1, "USD / VND")
    if "fx" in stale:
        label_right = pill(d, label_right + 10, y + 1, "OFFLINE", size=15, is_filled=False)
    if fx:
        value = f"{fx['sell']:,.0f}"
        d.text((label_right + 16, y), value, font=font(24, bold=True), fill=INK)
        note_x = label_right + 16 + d.textlength(value, font=font(24, bold=True)) + 18
        d.text((note_x, y + 3), f"Vietcombank sell  ·  buy {fx['buy']:,.0f}", font=font(20), fill=MID)
    rule(d, MUSIC_TOP - 14)


def wrap(d: Draw, text: str, fnt, max_width: float, max_lines: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=fnt) <= max_width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [truncate(d, " ".join(lines[max_lines - 1:]), fnt, max_width)]
    return lines


def draw_quote(d: Draw, now: datetime) -> None:
    """Fills the econ box on the many days with no major US releases."""
    text, author = quote_for(now)
    section_title(d, X0, ECON_TOP, "QUOTE  ·  new one every 15 min")
    fnt, lines, line_h = layout_quote(d, f"“{text}”")
    for i, line in enumerate(lines):
        d.text((X0, ECON_TOP + 34 + i * line_h), line, font=fnt, fill=INK)
    d.text((X1, ECON_TOP + 34 + len(lines) * line_h + 2), f"— {author}", font=font(20), fill=MID, anchor="ra")


QUOTE_SIZES = ((26, 2, 36), (21, 3, 29))  # (font size, max lines, line height): big first, smaller for long quotes


def layout_quote(d: Draw, text: str) -> tuple:
    for size, max_lines, line_h in QUOTE_SIZES:
        fnt = font(size, bold=True)
        lines = wrap(d, text, fnt, X1 - X0, max_lines)
        if " ".join(lines) == text:
            return fnt, lines, line_h
    return fnt, lines, line_h  # still too long: last size, truncated with …


def draw_econ(d: Draw, events: list[dict] | None, now: datetime, is_stale: bool) -> None:
    if events:
        section_title(d, X0, ECON_TOP, "US ECONOMIC EVENTS  ·  high impact", is_stale)
        for i, e in enumerate(events[:3]):
            y = ECON_TOP + 34 + i * 34
            when = e["time"].strftime("%H:%M") if e["time"].date() == now.date() else e["time"].strftime("%a %H:%M")
            d.text((X0, y), when, font=font(22, bold=True), fill=INK)
            detail = "  ·  ".join(p for p in (e["forecast"] and f"fcst {e['forecast']}", e["previous"] and f"prev {e['previous']}") if p)
            d.text((X0 + 130, y), truncate(d, e["title"], font(22), 380), font=font(22), fill=INK)
            d.text((X1, y), detail, font=font(20), fill=MID, anchor="ra")
    else:  # none this week, or the feed is down: show the quote instead of an empty box
        draw_quote(d, now)
    rule(d, HEADLINES_TOP - 14)


def draw_news(d: Draw, news: dict | None, is_stale: bool) -> None:
    """Compact strip: a few top stories, each tagged with its feed."""
    items = market_headlines(news, HEADLINES)
    section_title(d, X0, HEADLINES_TOP, "MARKET HEADLINES  ·  high impact only", is_stale)
    fnt, tag_w = font(23), 100
    for i, (tag, headline) in enumerate(items or [("", "No market-moving headlines right now")]):
        y = HEADLINES_TOP + 36 + i * 36
        if tag:
            pill(d, X0, y + 1, tag, size=14, is_filled=False)
        d.text((X0 + tag_w, y), truncate(d, headline, fnt, X1 - X0 - tag_w), font=fnt, fill=INK)
