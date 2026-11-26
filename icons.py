"""70s-style weather and trend icons drawn with Pillow shapes (crisp on e-ink, no image assets).

Motifs: striped sunset sun, chunky outlined clouds, teardrop rain, stripe-band fog. Icons assume a white background:
the sunset stripes are white bars drawn across the shape.
"""
import math

from PIL import ImageDraw

INK, CLOUD_FILL, STRIPE_GRAY, PAPER = 0, 190, 120, 255
Draw = ImageDraw.ImageDraw


def _circle(d: Draw, cx: float, cy: float, r: float, **kw) -> None:
    d.ellipse((cx - r, cy - r, cx + r, cy + r), **kw)


def _sun(d: Draw, cx: float, cy: float, s: float) -> None:
    """Solid disc with sunset stripes through its lower half, ringed by chunky rounded rays."""
    r = s * 0.27
    ray_w = max(4, int(s * 0.075))
    for i in range(8):
        a = i * math.pi / 4 + math.pi / 8
        x0, y0 = cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45
        x1, y1 = cx + math.cos(a) * r * 1.95, cy + math.sin(a) * r * 1.95
        d.line((x0, y0, x1, y1), fill=INK, width=ray_w)
        _circle(d, x0, y0, ray_w / 2, fill=INK)  # round caps
        _circle(d, x1, y1, ray_w / 2, fill=INK)
    _circle(d, cx, cy, r, fill=INK)
    gap = max(2, s * 0.018)
    for i, frac in enumerate((0.22, 0.48, 0.72)):  # stripes get thicker toward the horizon
        y = cy + r * frac
        d.rectangle((cx - r - 1, y, cx + r + 1, y + gap * (1 + i * 0.6)), fill=PAPER)


_CLOUD_PUFFS = ((-0.2, 0.04, 0.19), (0.04, -0.1, 0.25), (0.27, 0.06, 0.17))


def _cloud_shape(d: Draw, cx: float, cy: float, s: float, fill: int, pad: float) -> None:
    for ox, oy, r in _CLOUD_PUFFS:
        _circle(d, cx + ox * s, cy + oy * s, r * s + pad, fill=fill)
    d.rounded_rectangle((cx - 0.39 * s - pad, cy + 0.02 * s - pad, cx + 0.44 * s + pad, cy + 0.23 * s + pad),
                        radius=0.105 * s + pad, fill=fill)


def _cloud(d: Draw, cx: float, cy: float, s: float, fill: int = CLOUD_FILL, halo: bool = False) -> None:
    """Chunky cloud: thick black outline, light fill, one gray 70s stripe along the base."""
    w = max(3, s * 0.045)
    if halo:  # white gap so the cloud reads in front of the sun
        _cloud_shape(d, cx, cy, s, PAPER, w * 2.2)
    _cloud_shape(d, cx, cy, s, INK, w)
    _cloud_shape(d, cx, cy, s, fill, 0)
    d.rounded_rectangle((cx - 0.3 * s, cy + 0.13 * s, cx + 0.36 * s, cy + 0.13 * s + w), radius=w / 2, fill=STRIPE_GRAY)


def _drop(d: Draw, x: float, y: float, s: float) -> None:
    """Teardrop: round bottom, pointed top."""
    r = s * 0.055
    _circle(d, x, y + r, r, fill=INK)
    d.polygon([(x - r, y + r * 0.9), (x + r, y + r * 0.9), (x, y - r * 1.6)], fill=INK)


def _rain(d: Draw, cx: float, cy: float, s: float) -> None:
    for ox, oy in ((-0.2, 0.36), (0.02, 0.44), (0.24, 0.36)):
        _drop(d, cx + ox * s, cy + oy * s, s)


def _bolt(d: Draw, cx: float, cy: float, s: float) -> None:
    pts = [(0.06, 0.2), (-0.12, 0.46), (0.0, 0.46), (-0.08, 0.68), (0.16, 0.38), (0.03, 0.38), (0.12, 0.2)]
    poly = [(cx + x * s, cy + y * s) for x, y in pts]
    d.polygon(poly, fill=INK, outline=INK)
    d.line(poly + [poly[0]], fill=INK, width=max(2, int(s * 0.03)), joint="curve")


def _fog(d: Draw, cx: float, cy: float, s: float) -> None:
    """Three rounded stripe bands, like the racing stripes elsewhere on the screen."""
    h = max(5, s * 0.09)
    for i, (oy, inset, fill) in enumerate(((-0.2, 0.0, INK), (0.0, 0.1, STRIPE_GRAY), (0.2, 0.04, CLOUD_FILL))):
        left, right = cx - 0.4 * s + inset * s, cx + 0.4 * s - inset * s * (1.6 if i == 1 else 0.5)
        d.rounded_rectangle((left, cy + oy * s - h / 2, right, cy + oy * s + h / 2), radius=h / 2, fill=fill)


def icon_kind(code: int) -> str:
    """Map an Open-Meteo WMO weather code to an icon family."""
    if code == 0:
        return "sun"
    if code in (1, 2):
        return "partly"
    if code == 3:
        return "cloud"
    if code in (45, 48):
        return "fog"
    if code >= 95:
        return "storm"
    return "rain"


def weather_icon(d: Draw, code: int, cx: float, cy: float, size: float) -> None:
    """Draw the icon for `code` centred on (cx, cy), roughly `size` px square."""
    kind = icon_kind(code)
    if kind == "sun":
        _sun(d, cx, cy, size)
    elif kind == "partly":
        _sun(d, cx + 0.16 * size, cy - 0.15 * size, size * 0.78)
        _cloud(d, cx - 0.06 * size, cy + 0.1 * size, size * 0.82, halo=True)
    elif kind == "fog":
        _fog(d, cx, cy, size)
    else:
        _cloud(d, cx, cy - 0.12 * size, size)
        if kind == "rain":
            _rain(d, cx, cy - 0.12 * size, size)
        elif kind == "storm":
            _bolt(d, cx, cy - 0.12 * size, size)


def trend_icon(d: Draw, x: float, cy: float, size: float, is_up: bool) -> None:
    """Solid triangle with left edge at x: up for gains, outlined down for losses (readable in grayscale)."""
    h = size * 0.8
    if is_up:
        d.polygon([(x, cy + h / 2), (x + size, cy + h / 2), (x + size / 2, cy - h / 2)], fill=INK)
    else:
        d.polygon([(x, cy - h / 2), (x + size, cy - h / 2), (x + size / 2, cy + h / 2)],
                  outline=INK, width=max(2, int(size * 0.12)))
