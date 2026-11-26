"""Everything you'd want to edit lives here."""
import os
from pathlib import Path

ROOT = Path(__file__).parent

# --- location ---------------------------------------------------------------
LATITUDE, LONGITUDE, PLACE = 10.78, 106.70, "Ho Chi Minh City"
TIDE_LAT, TIDE_LON, TIDE_PLACE = 10.38, 106.95, "Vũng Tàu"  # the tide model only covers the sea: use the nearest sea point

# --- markets: Yahoo symbol -> label ("vps:" prefix = VPS feed, for UPCoM stocks Yahoo lacks) ---
MARKETS = {
    "US": {"VOO": "VOO", "NVDA": "NVDA", "ANT": "ANT", "PLTR": "PLTR", "MU": "MU"},
    "VIỆT NAM": {"vps:VNINDEX": "VN-Index", "VIC.VN": "VIC", "VCB.VN": "VCB", "VHM.VN": "VHM", "vps:MSR": "MSR"},
    "CRYPTO": {"BTC-USD": "BTC", "ETH-USD": "ETH", "BNB-USD": "BNB", "XRP-USD": "XRP", "SOL-USD": "SOL"},
}
CHARTS = {"GC=F": "GOLD  USD/oz", "DX-Y.NYB": "DXY"}  # 1-month charts; "vps:" symbols come from VPS (e.g. "vps:VNINDEX")
ECON_COUNTRIES = {"USD"}  # ForexFactory currency codes; high-impact events only

# --- news & Claude usage ----------------------------------------------------------
NEWS_FEEDS = {
    "VN": ["https://vnexpress.net/rss/kinh-doanh.rss", "https://cafef.vn/thi-truong-chung-khoan.rss"],
    "WORLD": ["https://www.cnbc.com/id/100003114/device/rss/rss.html"],
}
HEADLINES = {"VN": 2, "WORLD": 2}  # market-moving headlines per feed group (see news_filter.py)
SECRETS_FILE = ROOT / ".secrets.env"  # KEY=VALUE lines, git-ignored; see README
PANASONIC_TOKEN_FILE = ROOT / ".panasonic-token"


def secret(name: str) -> str:
    """Env var wins; otherwise the KEY=VALUE line in .secrets.env. Empty string when unset."""
    if os.environ.get(name):
        return os.environ[name]
    if not SECRETS_FILE.exists():
        return ""
    for line in SECRETS_FILE.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


# Apple Music: this Mac plus others running music_agent.py on Tailscale (token: MUSIC_AGENT_TOKEN in .secrets.env)
MUSIC_LOCAL_NAME = "Mac mini"
MUSIC_REMOTES: dict[str, str] = {}  # e.g. {"MacBook": "http://<tailscale-ip>:8765"}
CLAUDE_USAGE_FILE = ROOT / ".claude_usage.json"  # written by usage_tap.py from Claude Code's status line

# --- alert thresholds ---------------------------------------------------------
TIDE_ALERT_M = 2.3  # model metres above MSL at Vũng Tàu; tune after watching a few triều cường days
BIG_MOVE_PCT = 3.0
AQI_ALERT = 150  # US AQI "Unhealthy"
RAIN_ALERT_MINUTES = 60
HEAVY_RAIN_PROB = 70
CLAUDE_USAGE_ALERT_PCT = 80

# --- display / serving ------------------------------------------------------
WIDTH, HEIGHT = 1680, 1264  # landscape layout; Kindle framebuffer is 1264x1680 portrait (check `eips -i`)
ROTATE = 90  # degrees CCW before sending to the Kindle; use 270 if it shows upside down
RENDER_EVERY_SECONDS = 15
# touch: raw panel size and axis flips (calibrate with the on-screen tap marker), marker on while setting up
TOUCH_PANEL_W, TOUCH_PANEL_H = 1264, 1680
TOUCH_FLIP_X, TOUCH_FLIP_Y = False, False
TOUCH_DEBUG = False  # True shows a marker where each tap lands (for calibrating a new Kindle)
TAP_MARKER_SECONDS = 30
SWIPE_MIN_PX = 250  # horizontal finger travel (layout px) that counts as a page swipe
HOME_IDLE_SECONDS = 180  # Home page falls back to the dashboard after this long without a touch
PORT = 8080
OUT_DIR = ROOT / "out"


# Personal overrides (location, other Macs, ...) live in config_local.py, which is git-ignored.
try:
    from config_local import *  # noqa: E402,F401,F403
except ImportError:
    pass
