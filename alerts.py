"""Decide what deserves the black alert bar. Pure function of the data so it is easy to test."""
from datetime import datetime, timedelta

from config import AQI_ALERT, BIG_MOVE_PCT, CLAUDE_USAGE_ALERT_PCT, HEAVY_RAIN_PROB, RAIN_ALERT_MINUTES, TIDE_ALERT_M
from lunar import is_spring_tide_window, to_lunar


def _rain_alert(weather: dict | None, now: datetime) -> str | None:
    cast = (weather or {}).get("nowcast") or {}
    start = cast.get("start")
    if start and start - now <= timedelta(minutes=RAIN_ALERT_MINUTES):
        when = "now" if start <= now else f"from {start:%H:%M}"
        return f"Rain {when} (~{cast['minutes']} min)"
    return None


def _flood_alert(tides: list[dict] | None, weather: dict | None, now: datetime) -> str | None:
    high = [t for t in tides or [] if t["height"] >= TIDE_ALERT_M and t["time"] - now <= timedelta(hours=24)]
    if not high:
        return None
    peak = high[0]
    is_wet = ((weather or {}).get("today", {}).get("rain") or 0) >= HEAVY_RAIN_PROB or bool(_rain_alert(weather, now))
    if is_wet and is_spring_tide_window(to_lunar(now.date())[0]):
        return f"Flood risk: triều cường {peak['time']:%H:%M} + heavy rain"
    return f"Triều cường {peak['time']:%H:%M} ({peak['height']:+.2f} m)"


def _market_alert(markets: dict | None) -> str | None:
    moves = [q for qs in (markets or {}).values() for q in qs if abs(q["change_pct"]) >= BIG_MOVE_PCT]
    moves.sort(key=lambda q: -abs(q["change_pct"]))
    return "Big moves: " + ", ".join(f"{q['symbol']} {q['change_pct']:+.1f}%" for q in moves[:3]) if moves else None


def _soon(items: list[dict] | None, now: datetime, minutes: int) -> dict | None:
    return next((e for e in items or [] if now <= e["time"] <= now + timedelta(minutes=minutes)), None)


def _claude_alert(usage: dict | None, now: datetime) -> str | None:
    for key, name in (("five_hour", "5-hour"), ("seven_day", "weekly")):
        w = (usage or {}).get(key)
        if w and w["pct"] >= CLAUDE_USAGE_ALERT_PCT and not (w["resets"] and w["resets"] <= now):
            return f"Claude {name} usage {w['pct']:.0f}%" + (f" · resets {w['resets']:%H:%M}" if w["resets"] else "")
    return None


def build_alerts(data: dict, now: datetime) -> list[str]:
    """Most urgent first."""
    econ = _soon(data.get("econ"), now, 60)
    aqi = data.get("aqi")
    candidates = [
        _claude_alert(data.get("claude"), now),
        _rain_alert(data.get("weather"), now),
        _flood_alert(data.get("tides"), data.get("weather"), now),
        econ and f"US {econ['title']} at {econ['time']:%H:%M}",
        aqi and aqi["aqi"] >= AQI_ALERT and f"Air unhealthy: AQI {aqi['aqi']}",
        _market_alert(data.get("markets")),
    ]
    return [c for c in candidates if c]
