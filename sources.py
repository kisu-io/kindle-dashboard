"""Data fetchers. Every loader in SOURCES returns data or None/[]; none of them raise."""
import json
import logging
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from home_devices import get_acs, get_lights
from music import get_now_playing
from config import (CHARTS, CLAUDE_USAGE_FILE, ECON_COUNTRIES, LATITUDE, LONGITUDE,
                    MARKETS, NEWS_FEEDS, TIDE_LAT, TIDE_LON)

USER_AGENT = "Mozilla/5.0 (kindle-dashboard)"
NEWS_PER_FEED = 30  # scanned by news_filter; only the market-moving few are shown
TIDE_PEAKS_SHOWN = 3
log = logging.getLogger("dashboard")
_pool = ThreadPoolExecutor(max_workers=8)

WEATHER_CODES = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 80: "Showers", 81: "Showers",
    82: "Heavy showers", 95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # one dead API must not blank the whole screen
        log.warning("%s failed: %r", fn.__name__, exc)  # args omitted: they can contain secret URLs
        return None


# --- weather ----------------------------------------------------------------

def nowcast(times: list[str], precip: list[float | None], threshold_mm: float = 0.1) -> dict:
    """First 15-min slot with rain and how long it lasts."""
    for i, mm in enumerate(precip):
        if mm is not None and mm >= threshold_mm:
            run = 0
            while i + run < len(precip) and (precip[i + run] or 0) >= threshold_mm:
                run += 1
            return {"start": datetime.fromisoformat(times[i]), "minutes": run * 15}
    return {"start": None, "minutes": 0, "window_minutes": len(precip) * 15}


def get_weather() -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}&timezone=auto&forecast_days=4"
        "&forecast_hours=12&forecast_minutely_15=8"
        "&current=temperature_2m,relative_humidity_2m,weather_code,apparent_temperature"
        "&minutely_15=precipitation&hourly=temperature_2m,precipitation_probability"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
        "relative_humidity_2m_mean"
    )
    data = json.loads(fetch(url))
    cur, day, hourly, m15 = data["current"], data["daily"], data["hourly"], data["minutely_15"]
    days = [
        {"date": date.fromisoformat(day["time"][i]), "code": day["weather_code"][i],
         "high": round(day["temperature_2m_max"][i]), "low": round(day["temperature_2m_min"][i]),
         "rain": day["precipitation_probability_max"][i], "humidity": day["relative_humidity_2m_mean"][i]}
        for i in range(len(day["time"]))
    ]
    return {
        "temp": round(cur["temperature_2m"]),
        "feels": round(cur["apparent_temperature"]),
        "humidity": cur["relative_humidity_2m"],
        "code": cur["weather_code"],
        "summary": WEATHER_CODES.get(cur["weather_code"], f"Code {cur['weather_code']}"),
        "today": days[0],
        "forecast": days[1:],
        "hourly": [{"time": datetime.fromisoformat(t), "temp": temp, "rain": prob or 0}
                   for t, temp, prob in zip(hourly["time"], hourly["temperature_2m"], hourly["precipitation_probability"])],
        "nowcast": nowcast(m15["time"], m15["precipitation"]),
    }


def get_aqi() -> dict:
    url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={LATITUDE}&longitude={LONGITUDE}&current=us_aqi,pm2_5"
    cur = json.loads(fetch(url))["current"]
    return {"aqi": round(cur["us_aqi"]), "pm25": round(cur["pm2_5"])}


def high_tides(times: list[str], levels: list[float | None], after: datetime) -> list[dict]:
    """Local maxima of the hourly sea level after `after`. shortcut: hourly data, so peak times are ±30 min."""
    peaks = []
    for i in range(1, len(levels) - 1):
        prev, cur, nxt = levels[i - 1], levels[i], levels[i + 1]
        if None in (prev, cur, nxt) or not (cur >= prev and cur > nxt):
            continue
        at = datetime.fromisoformat(times[i])
        if at >= after:
            peaks.append({"time": at, "height": cur})
    return peaks


def get_tides() -> list[dict]:
    url = (f"https://marine-api.open-meteo.com/v1/marine?latitude={TIDE_LAT}&longitude={TIDE_LON}"
           "&hourly=sea_level_height_msl&timezone=auto&forecast_days=3")
    hourly = json.loads(fetch(url))["hourly"]
    after = datetime.now().replace(minute=0, second=0, microsecond=0)
    return high_tides(hourly["time"], hourly["sea_level_height_msl"], after)[:TIDE_PEAKS_SHOWN]


# --- markets ----------------------------------------------------------------

def quote_from_closes(label: str, closes: list[float | None], prev: float | None = None) -> dict:
    """Latest close vs `prev` (default: the close before it)."""
    closes = [c for c in closes if c is not None]
    price = closes[-1]
    prev = prev if prev is not None else closes[-2]
    return {"symbol": label, "price": price, "change_pct": (price - prev) / prev * 100, "closes": closes}


def _yahoo(symbol: str, query: str) -> dict:
    # shortcut: Yahoo's unofficial chart API, no key; swap for a keyed API if it starts failing
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{query}"
    return json.loads(fetch(url))["chart"]["result"][0]


def get_quote(symbol: str, label: str) -> dict:
    """Intraday 5-min closes for the sparkline; change vs previous session close."""
    result = _yahoo(symbol, "range=1d&interval=5m")
    meta = result["meta"]
    closes = (result["indicators"]["quote"][0].get("close") or []) + [meta["regularMarketPrice"]]
    q = quote_from_closes(label, closes, prev=meta["chartPreviousClose"])
    if meta.get("currency") == "VND" and meta.get("instrumentType") != "INDEX":  # VN convention: thousands of VND
        q = {**q, "price": q["price"] / 1000, "closes": [c / 1000 for c in q["closes"]]}
    return q


def get_vps_quote(symbol: str, label: str) -> dict:
    # shortcut: VPS's public TradingView feed (prices in thousands of VND); sparkline is daily, not intraday
    now = int(time.time())
    url = f"https://histdatafeed.vps.com.vn/tradingview/history?symbol={urllib.parse.quote(symbol)}&resolution=D&from={now - 30 * 86400}&to={now}"
    return quote_from_closes(label, json.loads(fetch(url))["c"])


def any_quote(symbol: str, label: str) -> dict:
    return get_vps_quote(symbol[4:], label) if symbol.startswith("vps:") else get_quote(symbol, label)


def get_series(symbol: str, label: str) -> dict:
    result = _yahoo(symbol, "range=1mo&interval=1d")
    return quote_from_closes(label, result["indicators"]["quote"][0]["close"])


def get_markets() -> dict:
    jobs = {group: [_pool.submit(safe, any_quote, s, label) for s, label in tickers.items()]
            for group, tickers in MARKETS.items()}
    return {group: [q for q in (f.result() for f in futures) if q] for group, futures in jobs.items()}


def any_series(symbol: str, label: str) -> dict:
    return get_vps_quote(symbol[4:], label) if symbol.startswith("vps:") else get_series(symbol, label)


def get_charts() -> list[dict]:
    futures = [(label, _pool.submit(safe, any_series, s, label)) for s, label in CHARTS.items()]
    return [f.result() or {"symbol": label} for label, f in futures]


def get_usd_vnd() -> dict:
    root = ET.fromstring(fetch("https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx"))
    usd = next(e for e in root.iter("Exrate") if e.get("CurrencyCode") == "USD")
    return {"buy": float(usd.get("Buy").replace(",", "")), "sell": float(usd.get("Sell").replace(",", ""))}


def upcoming_econ(events: list[dict], now: datetime, limit: int = 3) -> list[dict]:
    """High-impact events for ECON_COUNTRIES from an hour ago onward, in local time."""
    out = []
    for e in events:
        if e.get("impact") != "High" or e.get("country") not in ECON_COUNTRIES:
            continue
        at = datetime.fromisoformat(e["date"]).astimezone().replace(tzinfo=None)
        if at >= now - timedelta(hours=1):
            out.append({"time": at, "title": e["title"], "forecast": e.get("forecast") or "", "previous": e.get("previous") or ""})
    return sorted(out, key=lambda e: e["time"])[:limit]


def get_econ() -> list[dict]:
    # ForexFactory's public weekly feed; it asks clients not to poll more than hourly
    return upcoming_econ(json.loads(fetch("https://nfs.faireconomy.media/ff_calendar_thisweek.json")), datetime.now())


# --- news & claude usage ----------------------------------------------------------

def get_news(feed_url: str) -> list[str]:
    root = ET.fromstring(fetch(feed_url))
    return [item.findtext("title", "").strip() for item in root.iter("item")][:NEWS_PER_FEED]


def get_all_news() -> dict:
    """{group: headlines}, merging each group's feeds in order and dropping duplicates."""
    futures = {name: [_pool.submit(safe, get_news, url) for url in urls] for name, urls in NEWS_FEEDS.items()}
    return {name: list(dict.fromkeys(h for f in fs for h in (f.result() or []))) for name, fs in futures.items()}


def parse_claude_usage(snapshot: dict) -> dict:
    """{'five_hour': {'pct', 'resets'}, 'seven_day': {...}, 'saved_at'} from the tap's JSON."""
    def window(raw: dict | None) -> dict | None:
        if not isinstance(raw, dict) or raw.get("used_percentage") is None:
            return None
        resets = raw.get("resets_at")
        return {"pct": float(raw["used_percentage"]),
                "resets": datetime.fromtimestamp(resets) if isinstance(resets, (int, float)) else None}
    limits = snapshot.get("rate_limits") or {}
    return {"five_hour": window(limits.get("five_hour")), "seven_day": window(limits.get("seven_day")),
            "saved_at": datetime.fromtimestamp(snapshot["saved_at"])}


def get_claude_usage() -> dict | None:
    if not CLAUDE_USAGE_FILE.exists():
        return None  # tap hasn't run yet: no Claude Code session since setup
    return parse_claude_usage(json.loads(CLAUDE_USAGE_FILE.read_text()))


# name: (refresh seconds, loader)
SOURCES = {
    "markets": (30, get_markets),
    "charts": (300, get_charts),
    "news": (180, get_all_news),
    "weather": (600, lambda: safe(get_weather)),
    "aqi": (1800, lambda: safe(get_aqi)),
    "fx": (1800, lambda: safe(get_usd_vnd)),
    "econ": (3600, lambda: safe(get_econ)),
    "claude": (15, lambda: safe(get_claude_usage)),
    "music": (5, lambda: safe(get_now_playing)),
    "acs": (60, lambda: safe(get_acs)),
    "lights": (60, lambda: safe(get_lights)),
    "tides": (3600, lambda: safe(get_tides)),
}


def has_data(value) -> bool:
    """False when a refresh failed. Empty econ/tide lists are legitimate; None is failure."""
    if value is None:
        return False
    if isinstance(value, dict) and value and all(isinstance(v, list) for v in value.values()):
        return any(value.values())  # markets / news: every group empty means the fetch failed
    if isinstance(value, list) and value and all(isinstance(v, dict) and "symbol" in v for v in value):
        return any("closes" in v for v in value)  # charts
    return True


def collect_data() -> dict:
    return {name: load() for name, (_, load) in SOURCES.items()}
