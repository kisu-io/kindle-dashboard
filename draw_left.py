"""Left column: clock, current weather, next-12h chart, 3-day forecast, tides, Claude usage."""
from datetime import datetime

from config import PLACE, TIDE_ALERT_M, TIDE_PLACE
from draw_common import DARK, FAINT, INK, LIGHT, MID, Draw, clock_font, font, section_title, stripes, truncate
from icons import weather_icon
from lunar import to_lunar

X0, X1 = 56, 720  # column bounds
CX = (X0 + X1) / 2
AQI_LEFT = X1 - 150
AQI_LEVELS = [(50, "Good"), (100, "Moderate"), (150, "Sensitive"), (200, "Unhealthy"), (300, "Very unhealthy")]


def rule(d: Draw, y: float) -> None:
    d.rounded_rectangle((X0, y - 1, X1, y + 2), radius=2, fill=INK)


def draw_clock(d: Draw, now: datetime) -> None:
    lday, lmonth, _, is_leap = to_lunar(now.date())
    d.text((CX, 108), now.strftime("%H:%M"), font=clock_font(170), fill=INK, anchor="mm")
    lunar_txt = f"Âm lịch {lday}/{lmonth}{' nhuận' if is_leap else ''}"
    d.text((CX, 205), f"{now:%A, %d %B %Y}  ·  {lunar_txt}", font=font(26), fill=DARK, anchor="mm")
    stripes(d, X0, X1, 228)


def aqi_level(aqi: int) -> str:
    return next((name for limit, name in AQI_LEVELS if aqi <= limit), "Hazardous")


def draw_aqi_badge(d: Draw, aqi: dict | None, is_stale: bool) -> None:
    left, top, right, bottom = AQI_LEFT, 262, X1, 352
    d.rounded_rectangle((left, top, right, bottom), radius=(bottom - top) / 2, outline=INK, width=3)
    if not aqi:
        d.text(((left + right) / 2, (top + bottom) / 2), "AQI n/a", font=font(22), fill=MID, anchor="mm")
        return
    is_bad = aqi["aqi"] > 100
    if is_bad:  # invert so poor air is visible across the room
        d.rounded_rectangle((left, top, right, bottom), radius=(bottom - top) / 2, fill=INK)
    fg = 255 if is_bad else INK
    d.text(((left + right) / 2, top + 30), f"AQI {aqi['aqi']}", font=font(28, bold=True), fill=fg, anchor="mm")
    d.text(((left + right) / 2, top + 66), f"{aqi_level(aqi['aqi'])}{' · old' if is_stale else ''}",
           font=font(18), fill=fg, anchor="mm")


def draw_current(d: Draw, w: dict | None, aqi: dict | None, stale: set) -> None:
    draw_aqi_badge(d, aqi, "aqi" in stale)
    if not w:
        section_title(d, X0, 270, "WEATHER", is_stale=True)
        d.text((X0, 300), "Weather unavailable", font=font(32), fill=MID)
        return
    weather_icon(d, w["code"], X0 + 58, 318, 116)
    temp = f"{w['temp']}°"
    d.text((X0 + 135, 252), temp, font=font(96, bold=True), fill=INK)
    tx = X0 + 135 + d.textlength(temp, font=font(96, bold=True)) + 18
    max_w = AQI_LEFT - 14 - tx
    d.text((tx, 270), truncate(d, w["summary"], font(26, bold=True), max_w), font=font(26, bold=True), fill=INK)
    d.text((tx, 312), f"Feels like {w['feels']}°", font=font(22), fill=MID)
    today = w["today"]
    d.text((X0, 384), f"H {today['high']}°  L {today['low']}°   ·   Rain {today['rain']}%   ·   Humidity {w['humidity']}%"
           f"{'   ·   OFFLINE' if 'weather' in stale else ''}", font=font(24), fill=DARK)
    cast = w["nowcast"]
    if cast["start"]:
        msg = f"Rain from {cast['start']:%H:%M}  ·  about {cast['minutes']} min"
        weather_icon(d, 63, X0 + 18, 440, 40)
    else:
        msg = f"No rain expected in the next {cast.get('window_minutes', 120) // 60} hours"
    d.text((X0 + (44 if cast["start"] else 0), 424), msg, font=font(24, bold=True), fill=INK)
    d.text((X1, 428), PLACE, font=font(20), fill=MID, anchor="ra")


def draw_hourly(d: Draw, hourly: list[dict]) -> None:
    """Temperature line over rain-probability bars for the next 12 hours."""
    section_title(d, X0, 470, "NEXT 12 HOURS  ·  temperature / chance of rain")
    if len(hourly) < 2:
        return
    left, right, top, bottom = X0 + 4, X1 - 4, 520, 612
    step = (right - left) / (len(hourly) - 1)
    bar_w = step * 0.55
    for i, h in enumerate(hourly):
        x = left + i * step
        if h["rain"]:
            d.rectangle((x - bar_w / 2, bottom - h["rain"] / 100 * (bottom - top), x + bar_w / 2, bottom), fill=FAINT)
    temps = [h["temp"] for h in hourly]
    lo, hi = min(temps), max(temps)
    span = (hi - lo) or 1
    pts = [(left + i * step, bottom - 8 - (t - lo) / span * (bottom - top - 26)) for i, t in enumerate(temps)]
    d.line((left, bottom, right, bottom), fill=LIGHT, width=1)
    d.line(pts, fill=INK, width=3, joint="curve")
    for i, h in enumerate(hourly):
        if i % 3 == 0 or i == len(hourly) - 1:
            x, y = pts[i]
            d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=INK)
            d.text((x, y - 10), f"{round(h['temp'])}°", font=font(18, bold=True), fill=INK, anchor="ms")
            d.text((x, bottom + 8), f"{h['time']:%H}h", font=font(18), fill=MID, anchor="mt")


def draw_forecast(d: Draw, w: dict | None) -> None:
    rule(d, 650)
    if not w:
        return
    col_w = (X1 - X0) / max(1, len(w["forecast"]))
    for i, day in enumerate(w["forecast"]):
        cx = X0 + col_w * (i + 0.5)
        d.text((cx, 680), day["date"].strftime("%a %d"), font=font(24, bold=True), fill=INK, anchor="mm")
        weather_icon(d, day["code"], cx, 740, 74)
        d.text((cx, 798), f"{day['high']}° / {day['low']}°", font=font(26, bold=True), fill=INK, anchor="mm")
        d.text((cx, 830), f"Rain {day['rain']}%  ·  Hum {day['humidity']}%", font=font(19), fill=MID, anchor="mm")


def draw_tides(d: Draw, tides: list[dict] | None, now: datetime, is_stale: bool) -> None:
    rule(d, 862)
    section_title(d, X0, 876, f"TRIỀU CƯỜNG  ·  {TIDE_PLACE} (model)", is_stale or tides is None)
    if not tides:
        d.text((X0, 910), "Tide data unavailable", font=font(24), fill=MID)
        return
    col_w = (X1 - X0) / 3
    for i, t in enumerate(tides):
        x = X0 + col_w * i
        day = "Today" if t["time"].date() == now.date() else t["time"].strftime("%a")
        is_high = t["height"] >= TIDE_ALERT_M
        d.text((x, 906), f"{day} {t['time']:%H:%M}", font=font(24, bold=True), fill=INK)
        d.text((x, 938), f"{t['height']:+.2f} m{'  · HIGH' if is_high else ''}", font=font(21, bold=is_high),
               fill=INK if is_high else MID)


def usage_row(d: Draw, y: float, label: str, w: dict | None, now: datetime) -> None:
    """'5-hour  [██████░░░░]  62% · resets 15:40'; a window whose reset has passed shows as fresh."""
    d.text((X0, y), label, font=font(22, bold=True), fill=INK)
    left, right, h = X0 + 112, X1 - 250, 22
    d.rounded_rectangle((left, y + 2, right, y + 2 + h), radius=h / 2, outline=INK, width=2)
    if not w:
        d.text((X1, y + 1), "no data", font=font(20), fill=MID, anchor="ra")
        return
    has_reset = w["resets"] is not None and w["resets"] <= now
    pct = 0.0 if has_reset else max(0.0, min(100.0, w["pct"]))
    if pct > 0:
        d.rounded_rectangle((left + 4, y + 6, left + 4 + max(h - 8, (right - left - 8) * pct / 100), y + h - 2),
                            radius=(h - 8) / 2, fill=INK)
    if has_reset:
        note = "reset · fresh window"
    elif w["resets"] is None:
        note = ""
    elif w["resets"].date() == now.date():
        note = f"resets {w['resets']:%H:%M}"
    else:
        note = f"resets {w['resets']:%a %H:%M}"
    d.text((right + 16, y - 2), f"{pct:.0f}%", font=font(24, bold=True), fill=INK)
    d.text((X1, y + 1), note, font=font(19), fill=MID, anchor="ra")


def draw_claude_usage(d: Draw, usage: dict | None, now: datetime, is_stale: bool) -> None:
    rule(d, 984)
    as_of = f"  ·  as of {usage['saved_at']:%H:%M}" if usage else ""
    section_title(d, X0, 998, f"CLAUDE USAGE{as_of}", is_stale and usage is None)
    if not usage:
        d.text((X0, 1036), "Open Claude Code on this Mac to sync usage", font=font(22), fill=MID)
        return
    usage_row(d, 1040, "5-hour", usage["five_hour"], now)
    usage_row(d, 1090, "Weekly", usage["seven_day"], now)
