"""Render a home-office dashboard for a Kindle Oasis 2 and serve it over HTTP.

Run:  .venv/bin/python server.py   ->  http://<this-machine-ip>:8080/              (browser preview)
                                       http://<this-machine-ip>:8080/dashboard.png  (Kindle)
"""
import logging
import shutil
import threading
import time
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

import music
from config import HOME_IDLE_SECONDS, OUT_DIR, PORT, RENDER_EVERY_SECONDS, ROOT, ROTATE
from draw_home import hit as hit_home, level_at
from draw_music import hit_button
from home_devices import predict, run_home_action
from render import render, render_home
from touch import classify, panel_to_layout
from sources import SOURCES, collect_data, has_data, safe

DATA_POLL_SECONDS = 5
STALE_AFTER_TTLS = 3  # a source is "offline" once it has failed for this many refresh periods
log = logging.getLogger("dashboard")

latest: dict = {}  # replaced wholesale (never mutated) by data_loop
kindle: dict | None = None  # last status the Kindle reported with its image request
last_tap: dict | None = None  # for the calibration marker
page = "dashboard"  # or "home"; switched by swiping
last_touch = 0.0  # time.time() of the last tap/swipe, for the Home idle fallback
last_page_switch = 0.0
SWIPE_COOLDOWN_SECONDS = 1.5  # one physical swipe can arrive as two touches; only the first switches pages
DUPLICATE_TOUCH_SECONDS = 1.5  # an identical touch this soon after the last one is a duplicate, not a new tap
last_touch_key: tuple | None = None
_device_queue = ThreadPoolExecutor(max_workers=1)  # device commands run in order, off the touch path
home_targets: list = []  # touch targets from the last Home render
SCREEN_LIGHT_FILE = ROOT / ".screen_light"  # remembered front-light level ("auto" or 0-24)


def load_screen_light() -> int | None:
    text = SCREEN_LIGHT_FILE.read_text().strip() if SCREEN_LIGHT_FILE.exists() else "auto"
    return int(text) if text.isdigit() else None


screen_light: int | None = load_screen_light()
MAX_TOUCH_COORD = 4096
MAX_KEY_CODE = 1023  # Linux KEY_MAX


def data_loop() -> None:
    """Refresh each source on its own schedule, so slow APIs never delay the clock."""
    global latest
    started = time.time()
    fetched_at = {name: started for name in SOURCES}  # __main__ did the first full fetch
    last_ok = {name: started if has_data(latest.get(name)) else 0.0 for name in SOURCES}
    while True:
        now = time.time()
        for name, (ttl, load) in SOURCES.items():
            if now - fetched_at[name] < ttl:
                continue
            value = load()
            fetched_at[name] = time.time()
            if has_data(value):
                last_ok[name] = fetched_at[name]
                latest = {**latest, name: value}  # keep the last good value on failure
        stale = {n for n, (ttl, _) in SOURCES.items() if time.time() - last_ok[n] > ttl * STALE_AFTER_TTLS}
        latest = {**latest, "_stale": stale}
        time.sleep(DATA_POLL_SECONDS)


def save_atomic(img: Image.Image, name: str) -> None:
    tmp = OUT_DIR / f"{name}.{threading.get_ident()}.tmp.png"  # per thread: taps and the render loop save concurrently
    img.save(tmp, optimize=True)
    tmp.replace(OUT_DIR / name)  # atomic swap so a reader never gets a half-written file


def current_image() -> Image.Image:
    """Render whichever page is showing; Home falls back to the dashboard when left idle."""
    global page, home_targets
    if page == "home" and time.time() - last_touch > HOME_IDLE_SECONDS:
        page = "dashboard"
    data = {**latest, "kindle": kindle, "last_tap": last_tap, "screen_light": screen_light}
    if page == "home":
        img, home_targets = render_home(data, datetime.now())
        return img
    return render(data, datetime.now())


class Frame:
    """The Kindle's current image and a version that changes only when the picture does.
    Long-polling Kindle requests wait here, so a change reaches the screen at once instead of on a timer."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self.version, self.png, self._digest = 0, b"", b""

    def publish(self, png: bytes) -> None:
        digest = hashlib.sha1(png).digest()
        with self._cond:
            if digest != self._digest:
                self.version, self.png, self._digest = self.version + 1, png, digest
                self._cond.notify_all()

    def wait(self, after: int, timeout: float) -> tuple[int, bytes]:
        with self._cond:
            self._cond.wait_for(lambda: self.version != after, timeout=timeout)
            return self.version, self.png


frame = Frame()
LONG_POLL_SECONDS = 25  # Kindle waits up to this long for a change; then gets the current image anyway
HOME_RENDER_SECONDS = 3  # Home page re-renders often so device changes show quickly (only changes are sent)


def publish(img: Image.Image) -> bytes:
    """Save the browser preview and hand the Kindle image to any waiting Kindle request."""
    save_atomic(img, "preview.png")  # upright, for the browser
    save_atomic(img.rotate(ROTATE, expand=True), "dashboard.png")  # portrait, for plain (non-waiting) requests
    png = _kindle_png(img)
    frame.publish(png)
    return png


def render_loop() -> None:
    while True:
        try:
            publish(current_image())
        except Exception:  # keep serving the last good image rather than dying
            log.exception("render failed")
        now = datetime.now()
        every = HOME_RENDER_SECONDS if page == "home" else RENDER_EVERY_SECONDS
        time.sleep(every - (now.second % every) - now.microsecond / 1e6 + 0.2)


def _coord(q: dict, key: str) -> int | None:
    try:
        value = int(q[key][0])
    except (KeyError, ValueError, IndexError):
        return None
    return value if 0 <= value <= MAX_TOUCH_COORD else None


def parse_tap(query: str) -> tuple[tuple[int, int], tuple[int, int] | None] | None:
    """(end, start) raw panel coordinates from '?x=..&y=..[&sx=..&sy=..]'; None if x/y are invalid."""
    q = urllib.parse.parse_qs(query)
    x, y, sx, sy = (_coord(q, k) for k in ("x", "y", "sx", "sy"))
    if x is None or y is None:
        return None
    return (x, y), ((sx, sy) if sx is not None and sy is not None else None)


def run_dashboard_tap(x: int, y: int) -> str | None:
    """Music buttons; play also works with nothing loaded (it opens Music)."""
    global latest
    action = hit_button(x, y)
    if action:
        try:
            music.control(action, (latest.get("music") or {}).get("host"))
        except Exception as exc:  # report, but still answer with a fresh image
            log.warning("music %s failed: %r", action, exc)
        time.sleep(0.4)  # let Music update its state before we read it back
        latest = {**latest, "music": safe(music.get_now_playing) or latest.get("music")}
    return action


def run_home_tap(x: int, y: int) -> dict | None:
    """Show the result immediately (optimistic), send the command in the background, then re-read real state."""
    global latest
    action = hit_home(home_targets, x, y)
    if not action:
        return None
    if action["kind"] == "brightness_slider":  # handled on the Kindle: the level rides along in the image response
        set_screen_light(level_at(x, action))
        return action
    if action["kind"] == "brightness_auto":
        set_screen_light(None)
        return action
    before = latest.get(source_of(action))
    guess = predict(action, latest)
    if guess:
        latest = {**latest, guess[0]: guess[1]}
    _device_queue.submit(_send_home_action, action, before)
    return action


def set_screen_light(level: int | None) -> None:
    global screen_light
    screen_light = level
    SCREEN_LIGHT_FILE.write_text("auto" if level is None else str(level))


def _send_home_action(action: dict, before: list | None) -> None:
    global latest
    try:
        source, value = run_home_action(action, before)
        if value is None:  # AC: read back what Panasonic actually applied
            value = safe(SOURCES[source][1])
        if value is not None and source != "lights":  # lights: the optimistic value is already exact
            latest = {**latest, source: value}
            publish(current_image())  # push the confirmed state to the Kindle right away
    except Exception as exc:  # refused or offline: re-read so the screen stops showing the guess
        log.warning("home action %s failed: %r", action, exc)
        source = source_of(action)
        real = safe(SOURCES[source][1])
        if real is not None:
            latest = {**latest, source: real}
            publish(current_image())


def source_of(action: dict) -> str:
    return "acs" if action.get("kind") == "ac" else "lights"


def handle_tap(raw: tuple[int, int], raw_start: tuple[int, int] | None = None) -> bytes:
    """Swipe switches pages; a tap runs the button under it. Re-renders right away and returns the Kindle PNG."""
    global last_tap, page, last_touch, last_page_switch, last_touch_key
    if last_touch_key == (raw, raw_start) and time.time() - last_touch < DUPLICATE_TOUCH_SECONDS:
        log.info("touch raw=%s ignored (duplicate)", raw)
        return frame.png or publish(current_image())
    last_touch_key = (raw, raw_start)
    x, y = panel_to_layout(*raw)
    start = panel_to_layout(*raw_start) if raw_start else None
    last_touch = time.time()
    last_tap = {"x": x, "y": y, "raw": raw, "time": datetime.now()}
    slider = hit_home(home_targets, *start) if page == "home" and start else None
    if slider and slider["kind"] == "brightness_slider":  # a drag that starts on the slider moves it, not the page
        set_screen_light(level_at(x, slider))
        action = {"kind": "brightness_slider", "level": screen_light}
    elif classify(start, (x, y)) == "swipe":
        action = switch_page("swipe")
    else:
        action = run_home_tap(x, y) if page == "home" else run_dashboard_tap(x, y)
    log.info("touch raw=%s start=%s layout=(%d, %d) page=%s action=%s", raw, raw_start, x, y, page, action)
    return publish(current_image())


def switch_page(reason: str) -> str:
    """Toggle dashboard <-> Home, ignoring repeats within the cooldown (one press/swipe can arrive twice)."""
    global page, last_page_switch, last_touch
    last_touch = time.time()
    if time.time() - last_page_switch < SWIPE_COOLDOWN_SECONDS:
        return f"{reason} ignored (cooldown)"
    page = "home" if page == "dashboard" else "dashboard"
    last_page_switch = time.time()
    return f"{reason} to {page}"


def handle_key(code: int) -> bytes:
    """Page-turn buttons: either one switches page. The code is logged so the two could get different jobs."""
    log.info("key code=%d %s", code, switch_page("page button"))
    return publish(current_image())


def _kindle_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.rotate(ROTATE, expand=True).save(buf, format="PNG")
    return buf.getvalue()


def parse_battery(query: str) -> int | None:
    value = urllib.parse.parse_qs(query).get("battery", [""])[0].strip()
    return int(value) if value.isdigit() and int(value) <= 100 else None


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        global kindle
        path, _, query = self.path.partition("?")
        if path == "/tap":
            parsed = parse_tap(query)
            if parsed is None:
                self.send_error(400, "x and y must be integers 0-4096")
                return
            body = handle_tap(*parsed)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/key":
            code = urllib.parse.parse_qs(query).get("code", [""])[0]
            if not (code.isdigit() and int(code) <= MAX_KEY_CODE):
                self.send_error(400, "code must be an integer key code")
                return
            body = handle_key(int(code))
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/dashboard.png" and self.headers.get("User-Agent", "").startswith("curl"):  # the Kindle, not a browser
            kindle = {"battery": parse_battery(query), "seen": datetime.now()}
            wait = urllib.parse.parse_qs(query).get("wait", [""])[0]
            if wait.isdigit() and frame.png:  # long poll: answer when the picture changes (or after a timeout)
                version, body = frame.wait(int(wait), LONG_POLL_SECONDS)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Version", str(version))
                self.send_header("X-Brightness", "auto" if screen_light is None else str(screen_light))
                self.end_headers()
                self.wfile.write(body)
                return
        super().do_GET()

    def log_message(self, fmt: str, *args) -> None:  # quiet: the Kindle polls every 15 s
        pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    OUT_DIR.mkdir(exist_ok=True)
    shutil.copy(ROOT / "index.html", OUT_DIR)
    shutil.copy(ROOT / "music_agent.py", OUT_DIR)  # other Macs download the music helper from here (no secrets in it)
    log.info("Fetching initial data...")
    latest = {**collect_data(), "_stale": set()}
    threading.Thread(target=data_loop, daemon=True).start()
    threading.Thread(target=render_loop, daemon=True).start()
    log.info("Serving http://0.0.0.0:%d/", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), partial(Handler, directory=str(OUT_DIR))).serve_forever()
