"""Home page (swipe from the dashboard): Panasonic AC cards on the left, Smart Life light switches on the right.

Every button is registered as a touch target: (left, top, right, bottom, action) in landscape layout coordinates.
"""
from datetime import datetime

from draw_common import DARK, INK, LIGHT, MID, Draw, clock_font, font, pill, section_title, stripes, truncate

X0, SPLIT, X1 = 56, 760, 1624
LEFT_X1, RIGHT_X0 = SPLIT - 40, SPLIT + 44
TOP = 168  # below the header stripes
AC_CARD_H, AC_GAP = 300, 16
ROOM_ROW_H, LIGHT_GAP = 86, 12
NAME_W = 250
MODE_LABEL = {"Cool": "Cool", "Dry": "Dry", "Fan": "Fan only", "Auto": "Auto", "Heat": "Heat"}
FAN_LABEL = {"Auto": "Auto", "Low": "1", "LowMid": "2", "Mid": "3", "HighMid": "4", "High": "5"}

Target = tuple[float, float, float, float, dict]


def _button(d: Draw, box: tuple, label: str, is_on: bool, targets: list, action: dict, size: int = 22) -> None:
    """Rounded toggle: black with white text when on, outlined when off."""
    l, t, r, b = box
    radius = (b - t) / 2
    if is_on:
        d.rounded_rectangle(box, radius=radius, fill=INK)
    else:
        d.rounded_rectangle(box, radius=radius, outline=INK, width=3)
    fnt = font(size, bold=True)
    d.text(((l + r) / 2, (t + b) / 2), truncate(d, label, fnt, r - l - 24), font=fnt,
           fill=255 if is_on else INK, anchor="mm")
    targets.append((l - 6, t - 6, r + 6, b + 6, action))


def _round_button(d: Draw, cx: float, cy: float, r: float, symbol: str, targets: list, action: dict) -> None:
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK, width=3)
    w = r * 0.5
    d.rounded_rectangle((cx - w, cy - 3, cx + w, cy + 3), radius=3, fill=INK)  # minus bar
    if symbol == "+":
        d.rounded_rectangle((cx - 3, cy - w, cx + 3, cy + w), radius=3, fill=INK)
    targets.append((cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10, action))


def draw_header(d: Draw, now: datetime) -> None:
    d.text((X0, 28), "HOME", font=clock_font(76), fill=INK)
    d.text((X0 + 250, 50), "Swipe left or right for the dashboard", font=font(22), fill=MID)
    d.text((X1, 28), now.strftime("%H:%M"), font=clock_font(76), fill=INK, anchor="ra")
    stripes(d, X0, X1, 118, thickness=5, gap=3)


def draw_ac_card(d: Draw, ac: dict, top: float, targets: list) -> None:
    l, r, b = X0, LEFT_X1, top + AC_CARD_H
    d.rounded_rectangle((l, top, r, b), radius=28, outline=INK, width=3)
    pad = 24
    fg = INK if ac["is_on"] else MID
    d.text((l + pad, top + 18), ac["name"], font=font(32, bold=True), fill=INK)
    room = f"Room {ac['room']:g}°" if ac["room"] is not None else "Room --"
    d.text((l + pad, top + 60), room, font=font(22), fill=DARK)
    _button(d, (r - pad - 150, top + 20, r - pad, top + 82), "ON" if ac["is_on"] else "OFF", ac["is_on"], targets,
            {"kind": "ac", "id": ac["id"], "action": "power"}, size=26)
    # target temperature with - / +
    cy = top + 168
    target = f"{ac['target']:g}°" if ac["target"] is not None else "--"
    d.text(((l + r) / 2, cy), target, font=clock_font(96), fill=fg, anchor="mm")
    _round_button(d, l + pad + 52, cy, 46, "-", targets, {"kind": "ac", "id": ac["id"], "action": "cooler"})
    _round_button(d, r - pad - 52, cy, 46, "+", targets, {"kind": "ac", "id": ac["id"], "action": "warmer"})
    # mode and fan cycle buttons
    half = (r - l - 2 * pad - 16) / 2
    by = b - 82
    _button(d, (l + pad, by, l + pad + half, by + 60), f"Mode: {MODE_LABEL.get(ac['mode'], ac['mode'])}", False,
            targets, {"kind": "ac", "id": ac["id"], "action": "mode"})
    _button(d, (r - pad - half, by, r - pad, by + 60), f"Fan: {FAN_LABEL.get(ac['fan'], ac['fan'])}", False,
            targets, {"kind": "ac", "id": ac["id"], "action": "fan"})


def draw_acs(d: Draw, acs: list[dict] | None, is_stale: bool, targets: list) -> None:
    section_title(d, X0, TOP, "AIR CONDITIONING  ·  Panasonic", is_stale or acs is None)
    if not acs:
        d.text((X0, TOP + 44), "AC unavailable: run panasonic_login.py if the login expired", font=font(22), fill=MID)
        return
    for i, ac in enumerate(acs[:3]):
        draw_ac_card(d, ac, TOP + 40 + i * (AC_CARD_H + AC_GAP), targets)


def draw_lights(d: Draw, rooms: list[dict] | None, is_stale: bool, targets: list) -> None:
    right = pill(d, RIGHT_X0, TOP - 2, "LIGHTS")
    d.text((right + 10, TOP + 11), "Smart Life  ·  tap to switch", font=font(18), fill=MID, anchor="lm")
    if is_stale or rooms is None:
        pill(d, right + 270, TOP - 2, "OFFLINE", size=15, is_filled=False)
    any_on = any(g["on"] for room in rooms or [] for g in room["gangs"])
    _button(d, (X1 - 170, TOP - 8, X1, TOP + 34), "All off", False, targets, {"kind": "lights_off"}, size=20)
    if not rooms:
        d.text((RIGHT_X0, TOP + 50), "Lights unavailable", font=font(22), fill=MID)
        return
    d.text((X1 - 186, TOP + 13), f"{'some on' if any_on else 'all off'}", font=font(18), fill=MID, anchor="rm")
    btn_w = (X1 - RIGHT_X0 - NAME_W - 2 * LIGHT_GAP) / 3
    for i, room in enumerate(rooms[:12]):
        y = TOP + 50 + i * ROOM_ROW_H
        d.text((RIGHT_X0, y + ROOM_ROW_H / 2 - 6), truncate(d, room["room"], font(21, bold=True), NAME_W - 12),
               font=font(21, bold=True), fill=INK, anchor="lm")
        for j, gang in enumerate(room["gangs"][:3]):
            bx = RIGHT_X0 + NAME_W + j * (btn_w + LIGHT_GAP)
            _button(d, (bx, y, bx + btn_w, y + ROOM_ROW_H - 18), gang["name"], gang["on"], targets,
                    {"kind": "light", "id": room["id"], "code": gang["code"], "on": not gang["on"]}, size=19)


SCREEN_LIGHT_TOP = 1010
SCREEN_LIGHT_MAX = 24  # Kindle front-light levels (flIntensity 0-24)


SLIDER_H, KNOB_R = 26, 26


def draw_screen_light(d: Draw, level: int | None, targets: list) -> None:
    """Front light: a slider (tap or drag; far left = off) and an Auto button that hands control to the sensor."""
    right = pill(d, RIGHT_X0, SCREEN_LIGHT_TOP - 2, "SCREEN LIGHT")
    if level is None:
        note = "auto-brightness (light sensor)"
    else:
        note = "off" if level == 0 else f"level {level} / {SCREEN_LIGHT_MAX}"
    d.text((right + 10, SCREEN_LIGHT_TOP + 11), note, font=font(18), fill=MID, anchor="lm")
    cy = SCREEN_LIGHT_TOP + 84
    left, track_right = RIGHT_X0 + KNOB_R, X1 - 230
    d.rounded_rectangle((left - KNOB_R, cy - SLIDER_H / 2, track_right + KNOB_R, cy + SLIDER_H / 2),
                        radius=SLIDER_H / 2, outline=INK, width=3)
    if level is not None:
        kx = left + (track_right - left) * level / SCREEN_LIGHT_MAX
        if level > 0:
            d.rounded_rectangle((left - KNOB_R + 5, cy - SLIDER_H / 2 + 5, kx, cy + SLIDER_H / 2 - 5),
                                radius=(SLIDER_H - 10) / 2, fill=INK)
        d.ellipse((kx - KNOB_R, cy - KNOB_R, kx + KNOB_R, cy + KNOB_R), fill=255, outline=INK, width=4)
    targets.append((left - KNOB_R - 10, cy - 56, track_right + KNOB_R + 10, cy + 56,
                    {"kind": "brightness_slider", "left": left, "right": track_right}))
    _button(d, (X1 - 200, cy - 34, X1, cy + 34), "Auto", level is None, targets, {"kind": "brightness_auto"})


def level_at(x: float, slider: dict) -> int:
    """Slider position -> front-light level 0..SCREEN_LIGHT_MAX (clamped, so the rounded ends still count)."""
    frac = (x - slider["left"]) / (slider["right"] - slider["left"])
    return round(max(0.0, min(1.0, frac)) * SCREEN_LIGHT_MAX)


def draw_home(d: Draw, data: dict, now: datetime) -> list[Target]:
    """Draw the Home page; return its touch targets."""
    targets: list[Target] = []
    stale = data.get("_stale", set())
    draw_header(d, now)
    d.line((SPLIT, TOP, SPLIT, 1176), fill=LIGHT, width=2)
    draw_acs(d, data.get("acs"), "acs" in stale, targets)
    draw_lights(d, data.get("lights"), "lights" in stale, targets)
    draw_screen_light(d, data.get("screen_light"), targets)
    return targets


def hit(targets: list[Target], x: float, y: float) -> dict | None:
    return next((action for l, t, r, b, action in targets if l <= x <= r and t <= y <= b), None)
