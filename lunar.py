"""Vietnamese lunar calendar (âm lịch), UTC+7. Port of Hồ Ngọc Đức's public algorithm."""
import math
from datetime import date

TZ = 7.0
_DR = math.pi / 180


def _jd(dd: int, mm: int, yy: int) -> int:
    a = (14 - mm) // 12
    y, m = yy + 4800 - a, mm + 12 * a - 3
    return dd + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def _new_moon(k: int) -> float:
    t = k / 1236.85
    t2, t3 = t * t, t * t * t
    jd1 = 2415020.75933 + 29.53058868 * k + 0.0001178 * t2 - 0.000000155 * t3
    jd1 += 0.00033 * math.sin((166.56 + 132.87 * t - 0.009173 * t2) * _DR)
    m = 359.2242 + 29.10535608 * k - 0.0000333 * t2 - 0.00000347 * t3
    mpr = 306.0253 + 385.81691806 * k + 0.0107306 * t2 + 0.00001236 * t3
    f = 21.2964 + 390.67050646 * k - 0.0016528 * t2 - 0.00000239 * t3
    c1 = (0.1734 - 0.000393 * t) * math.sin(m * _DR) + 0.0021 * math.sin(2 * _DR * m)
    c1 -= 0.4068 * math.sin(mpr * _DR) + 0.0161 * math.sin(_DR * 2 * mpr)
    c1 -= 0.0004 * math.sin(_DR * 3 * mpr)
    c1 += 0.0104 * math.sin(_DR * 2 * f) - 0.0051 * math.sin(_DR * (m + mpr))
    c1 -= 0.0074 * math.sin(_DR * (m - mpr)) + 0.0004 * math.sin(_DR * (2 * f + m))
    c1 -= 0.0004 * math.sin(_DR * (2 * f - m)) - 0.0006 * math.sin(_DR * (2 * f + mpr))
    c1 += 0.0010 * math.sin(_DR * (2 * f - mpr)) + 0.0005 * math.sin(_DR * (2 * mpr + m))
    if t < -11:
        delta_t = 0.001 + 0.000839 * t + 0.0002261 * t2 - 0.00000845 * t3 - 0.000000081 * t * t3
    else:
        delta_t = -0.000278 + 0.000265 * t + 0.000262 * t2
    return jd1 + c1 - delta_t


def _new_moon_day(k: int) -> int:
    return math.floor(_new_moon(k) + 0.5 + TZ / 24)


def _sun_longitude_sector(day_number: int) -> int:
    """Which of 12 sectors (30° each) the sun is in at local midnight."""
    t = (day_number - 0.5 - TZ / 24 - 2451545.0) / 36525
    t2 = t * t
    m = 357.52910 + 35999.05030 * t - 0.0001559 * t2 - 0.00000048 * t * t2
    l0 = 280.46645 + 36000.76983 * t + 0.0003032 * t2
    dl = (1.914600 - 0.004817 * t - 0.000014 * t2) * math.sin(_DR * m)
    dl += (0.019993 - 0.000101 * t) * math.sin(_DR * 2 * m) + 0.000290 * math.sin(_DR * 3 * m)
    lon = (l0 + dl) * _DR
    lon -= math.pi * 2 * math.floor(lon / (math.pi * 2))
    return math.floor(lon / math.pi * 6)


def _lunar_month_11(yy: int) -> int:
    k = math.floor((_jd(31, 12, yy) - 2415021) / 29.530588853)
    nm = _new_moon_day(k)
    return _new_moon_day(k - 1) if _sun_longitude_sector(nm) >= 9 else nm


def _leap_month_offset(a11: int) -> int:
    k = math.floor((a11 - 2415021.076998695) / 29.530588853 + 0.5)
    i, arc = 1, _sun_longitude_sector(_new_moon_day(k + 1))
    while True:
        last, i = arc, i + 1
        arc = _sun_longitude_sector(_new_moon_day(k + i))
        if arc == last or i >= 14:
            return i - 1


def to_lunar(d: date) -> tuple[int, int, int, bool]:
    """Solar date -> (lunar day, lunar month, lunar year, is_leap_month)."""
    day_number = _jd(d.day, d.month, d.year)
    k = math.floor((day_number - 2415021.076998695) / 29.530588853)
    month_start = _new_moon_day(k + 1)
    if month_start > day_number:
        month_start = _new_moon_day(k)
    a11 = b11 = _lunar_month_11(d.year)
    if a11 >= month_start:
        year, a11 = d.year, _lunar_month_11(d.year - 1)
    else:
        year, b11 = d.year + 1, _lunar_month_11(d.year + 1)
    lunar_day = day_number - month_start + 1
    diff = math.floor((month_start - a11) / 29)
    is_leap, month = False, diff + 11
    if b11 - a11 > 365:
        leap_diff = _leap_month_offset(a11)
        if diff >= leap_diff:
            month = diff + 10
            is_leap = diff == leap_diff
    if month > 12:
        month -= 12
    if month >= 11 and diff < 4:
        year -= 1
    return lunar_day, month, year, is_leap


def is_spring_tide_window(lunar_day: int, days: int = 3) -> bool:
    """Triều cường peaks a day or two after mùng 1 and rằm (15)."""
    return lunar_day <= 1 + days or lunar_day >= 30 - 1 or abs(lunar_day - 15) <= days
