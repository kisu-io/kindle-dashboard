"""Map raw Kindle touch-panel coordinates to the landscape layout the dashboard is drawn in."""
from config import HEIGHT, ROTATE, SWIPE_MIN_PX, TOUCH_FLIP_X, TOUCH_FLIP_Y, TOUCH_PANEL_H, TOUCH_PANEL_W, WIDTH


def panel_to_layout(px: int, py: int) -> tuple[int, int]:
    """Inverse of `img.rotate(ROTATE, expand=True)`; flips exist for panels that report mirrored axes."""
    px = TOUCH_PANEL_W - 1 - px if TOUCH_FLIP_X else px
    py = TOUCH_PANEL_H - 1 - py if TOUCH_FLIP_Y else py
    if ROTATE == 90:  # landscape (x, y) was drawn at portrait (y, WIDTH-1-x)
        return WIDTH - 1 - py, px
    if ROTATE == 270:  # landscape (x, y) was drawn at portrait (HEIGHT-1-y, x)
        return py, HEIGHT - 1 - px
    return px, py


def classify(start: tuple[int, int] | None, end: tuple[int, int]) -> str:
    """'swipe' for a mostly-horizontal drag of at least SWIPE_MIN_PX (layout coords), else 'tap'."""
    if start is None:
        return "tap"
    dx, dy = end[0] - start[0], end[1] - start[1]
    return "swipe" if abs(dx) >= SWIPE_MIN_PX and abs(dx) > 1.5 * abs(dy) else "tap"
