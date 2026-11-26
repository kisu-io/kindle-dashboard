"""Now Playing section (under the USD/VND line) and its touch targets."""
from pathlib import Path

from PIL import Image, ImageOps

from draw_common import DARK, INK, LIGHT, MID, Draw, font, section_title, truncate
from draw_right import MUSIC_H, MUSIC_TOP, X0, X1, rule

CONTENT_TOP = MUSIC_TOP + 34  # below the section pill
ART = 100
BUTTON_R = 42  # drawn radius; the hit box is larger (fingers are blunter than e-ink pixels)
BUTTON_GAP = 108
BUTTON_CY = CONTENT_TOP + ART / 2
BUTTON_CX = {"previous": X1 - BUTTON_R - 2 * BUTTON_GAP, "playpause": X1 - BUTTON_R - BUTTON_GAP, "next": X1 - BUTTON_R}
# landscape-layout hit boxes (left, top, right, bottom) the server checks taps against: whole section height
MUSIC_BUTTONS = {name: (cx - BUTTON_GAP / 2, MUSIC_TOP, cx + BUTTON_GAP / 2, MUSIC_TOP + MUSIC_H)
                 for name, cx in BUTTON_CX.items()}


def hit_button(x: float, y: float) -> str | None:
    return next((name for name, (l, t, r, b) in MUSIC_BUTTONS.items() if l <= x <= r and t <= y <= b), None)


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _paste_art(img: Image.Image, art: Path | None, x: float, y: float) -> None:
    box = (int(x), int(y), int(x) + ART, int(y) + ART)
    try:
        if not art:
            raise FileNotFoundError
        with Image.open(art) as im:
            tile = ImageOps.fit(ImageOps.autocontrast(im.convert("L")), (ART, ART))
        img.paste(tile, box[:2])
    except (OSError, FileNotFoundError):  # no or unreadable artwork: draw a record instead
        d = Draw(img)
        d.ellipse(box, fill=INK)
        c = ART / 2
        d.ellipse((x + c - 14, y + c - 14, x + c + 14, y + c + 14), fill=255)
    Draw(img).rounded_rectangle(box, radius=10, outline=INK, width=3)


def _triangle(d: Draw, cx: float, cy: float, s: float, pointing_right: bool) -> None:
    sign = 1 if pointing_right else -1
    d.polygon([(cx - sign * s * 0.5, cy - s * 0.6), (cx - sign * s * 0.5, cy + s * 0.6), (cx + sign * s * 0.6, cy)], fill=INK)


def _button(d: Draw, name: str, is_playing: bool) -> None:
    cx, cy, r = BUTTON_CX[name], BUTTON_CY, BUTTON_R
    is_primary = name == "playpause"
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK if is_primary else 255, outline=INK, width=3)
    if is_primary:
        if is_playing:  # pause bars
            for dx in (-10, 10):
                d.rounded_rectangle((cx + dx - 6, cy - 16, cx + dx + 6, cy + 16), radius=3, fill=255)
        else:
            d.polygon([(cx - 9, cy - 17), (cx - 9, cy + 17), (cx + 17, cy)], fill=255)
        return
    is_next = name == "next"
    _triangle(d, cx - 6 if is_next else cx + 6, cy, 22, pointing_right=is_next)
    bar_x = cx + 12 if is_next else cx - 16
    d.rectangle((bar_x, cy - 13, bar_x + 4, cy + 13), fill=INK)


def draw_music(img: Image.Image, d: Draw, track: dict | None, host: str | None = None) -> None:
    """Own section: art, title, progress, and ⏮ ⏯ ⏭. Shown even when nothing plays."""
    is_playing = bool(track) and track["state"] == "playing"
    status = "playing" if is_playing else ("paused" if track else "nothing playing")
    where = f" on {host}" if host else ""
    section_title(d, X0, MUSIC_TOP, f"NOW PLAYING  ·  Apple Music{where}, {status}")
    top = CONTENT_TOP
    _paste_art(img, track.get("art") if track else None, X0, top)
    tx = X0 + ART + 18
    text_w = BUTTON_CX["previous"] - BUTTON_R - 22 - tx
    for name in BUTTON_CX:
        _button(d, name, is_playing)
    rule(d, MUSIC_TOP + MUSIC_H)
    if not track:
        d.text((tx, top + 14), "Nothing playing", font=font(26, bold=True), fill=INK)
        d.text((tx, top + 52), "Tap play to start Music on the Mac", font=font(20), fill=DARK)
        return
    d.text((tx, top), truncate(d, track["name"], font(26, bold=True), text_w), font=font(26, bold=True), fill=INK)
    sub = " · ".join(p for p in (track["artist"], track["album"]) if p)
    d.text((tx, top + 34), truncate(d, sub, font(20), text_w), font=font(20), fill=DARK)
    bar_y, bar_h = top + 66, 10
    d.rounded_rectangle((tx, bar_y, tx + text_w, bar_y + bar_h), radius=bar_h / 2, outline=INK, width=2)
    frac = track["position"] / track["duration"] if track["duration"] else 0
    if frac > 0:
        d.rounded_rectangle((tx, bar_y, tx + max(bar_h, text_w * min(frac, 1)), bar_y + bar_h), radius=bar_h / 2, fill=INK)
    d.text((tx, bar_y + 16), _clock(track["position"]), font=font(17), fill=MID)
    d.text((tx + text_w, bar_y + 16), _clock(track["duration"]), font=font(17), fill=MID, anchor="ra")


def draw_tap_marker(d: Draw, x: float, y: float) -> None:
    """Calibration aid: where the server thinks the last tap landed."""
    d.ellipse((x - 14, y - 14, x + 14, y + 14), outline=INK, width=3)
    d.line((x - 24, y, x + 24, y), fill=INK, width=2)
    d.line((x, y - 24, x, y + 24), fill=INK, width=2)
    d.text((x + 18, y + 14), "tap", font=font(16, bold=True), fill=LIGHT)
