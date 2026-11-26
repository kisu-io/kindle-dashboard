from datetime import date, datetime, timedelta

import pytest
from PIL import Image, ImageDraw

import alerts
import icons
import lunar
import render
import server
import sources
from draw_common import font, truncate

NOW = datetime(2026, 11, 26, 9, 5)
DAY = {"date": date(2026, 11, 27), "code": 63, "high": 33, "low": 25, "rain": 40, "humidity": 80}
WEATHER = {
    "temp": 31, "feels": 36, "humidity": 70, "code": 2, "summary": "Partly cloudy", "today": {**DAY, "rain": 80},
    "forecast": [DAY, {**DAY, "code": 95}, {**DAY, "code": 0}],
    "hourly": [{"time": NOW + timedelta(hours=h), "temp": 28 + h % 4, "rain": h * 8} for h in range(12)],
    "nowcast": {"start": NOW + timedelta(minutes=30), "minutes": 45},
}
QUOTE = {"symbol": "MU", "price": 601.25, "change_pct": -4.57, "closes": [630, 620, 601.25]}
FULL = {
    "weather": WEATHER, "aqi": {"aqi": 160, "pm25": 70}, "fx": {"buy": 25630.0, "sell": 26040.0},
    "tides": [{"time": NOW + timedelta(hours=6), "height": 2.43}],
    "markets": {"US": [QUOTE], "VIỆT NAM": [{**QUOTE, "symbol": "VIC", "change_pct": 1.0}], "CRYPTO": []},
    "charts": [{"symbol": "GOLD", "price": 3622.2, "change_pct": 2.4, "closes": [3500, 3550, 3622]}, {"symbol": "DXY"}],
    "econ": [{"time": NOW + timedelta(minutes=40), "title": "CPI m/m", "forecast": "0.3%", "previous": "0.4%"}],
    "claude": {"five_hour": {"pct": 86.0, "resets": NOW + timedelta(hours=2)},
               "seven_day": {"pct": 31.0, "resets": NOW + timedelta(days=3)}, "saved_at": NOW},
    "news": {"VN": ["Tin nhanh về thời tiết Hà Nội " * 6, "Tin hai", "Tin ba"], "WORLD": ["World one", "World two"]},
    "_stale": {"news"}, "kindle": {"battery": 84, "seen": NOW},
}


def test_render_full_and_empty_data():
    for data in (FULL, {}):
        img = render.render(data, NOW)
        assert img.size == (1680, 1264) and img.mode == "L"
        assert img.getextrema()[0] == 0  # clock always drawn


def test_render_uses_only_16_gray_levels():
    assert len(render.render(FULL, NOW).getcolors(256)) <= 16


@pytest.mark.parametrize("d, expected", [(date(2026, 2, 17), (1, 1, 2026, False)), (date(2025, 1, 29), (1, 1, 2025, False)),
                                         (date(2025, 7, 25), (1, 6, 2025, True)), (date(2023, 1, 22), (1, 1, 2023, False))])
def test_lunar_matches_known_tet_and_leap_month(d, expected):
    assert lunar.to_lunar(d) == expected


def test_alerts_priority_and_content():
    found = alerts.build_alerts(FULL, NOW)
    assert found[0] == "Claude 5-hour usage 86% · resets 11:05"
    assert any(a.startswith("Rain from 09:35") for a in found)
    assert any("Flood risk" in a for a in found)  # high tide + 80% rain + 18/10 âm lịch (near rằm)
    assert any("CPI" in a for a in found) and any("AQI 160" in a for a in found)
    assert any(a.startswith("Big moves: MU -4.6%") for a in found)


def test_no_alerts_when_calm():
    assert alerts.build_alerts({"weather": {**WEATHER, "nowcast": {"start": None, "minutes": 0}}}, NOW) == []


def test_nowcast_finds_first_rain_run():
    times = [f"2026-11-26T12:{m:02d}" for m in (0, 15, 30, 45)]
    assert sources.nowcast(times, [0.0, 0.4, 0.2, 0.0]) == {"start": datetime(2026, 11, 26, 12, 15), "minutes": 30}
    assert sources.nowcast(times, [0.0] * 4)["start"] is None


def test_high_tides_finds_peaks_after_cutoff():
    times = [f"2026-11-26T{h:02d}:00" for h in range(8)]
    peaks = sources.high_tides(times, [1.0, 2.0, 1.5, 0.5, 1.8, 2.4, None, 1.0], datetime(2026, 11, 26, 0))
    assert [(p["time"].hour, p["height"]) for p in peaks] == [(1, 2.0)]


def test_quote_from_closes_skips_none_and_uses_prev():
    q = sources.quote_from_closes("X", [50.0, None, 55.4, 56.1])
    assert q["price"] == 56.1 and round(q["change_pct"], 2) == 1.26
    assert sources.quote_from_closes("X", [10.0, 11.0], prev=10.0)["change_pct"] == pytest.approx(10.0)


def test_upcoming_econ_filters_country_impact_and_time():
    feed = [{"title": "CPI", "country": "USD", "impact": "High", "date": "2026-11-26T08:30:00-05:00"},
            {"title": "Old", "country": "USD", "impact": "High", "date": "2026-11-20T08:30:00-05:00"},
            {"title": "AUD CPI", "country": "AUD", "impact": "High", "date": "2026-11-26T08:30:00-05:00"},
            {"title": "Minor", "country": "USD", "impact": "Low", "date": "2026-11-26T08:30:00-05:00"}]
    assert [e["title"] for e in sources.upcoming_econ(feed, NOW)] == ["CPI"]


def test_parse_claude_usage_from_tap_snapshot():
    snap = {"rate_limits": {"five_hour": {"used_percentage": 42.5, "resets_at": 1795680000},
                            "seven_day": {"used_percentage": None}}, "saved_at": 1795674000}
    usage = sources.parse_claude_usage(snap)
    assert usage["five_hour"]["pct"] == 42.5 and usage["five_hour"]["resets"] == datetime.fromtimestamp(1795680000)
    assert usage["seven_day"] is None


def test_claude_alert_ignores_windows_that_already_reset():
    stale_high = {"five_hour": {"pct": 95.0, "resets": NOW - timedelta(minutes=5)}, "seven_day": None, "saved_at": NOW}
    assert alerts._claude_alert(stale_high, NOW) is None


def test_usage_tap_passes_input_through_and_saves(tmp_path, monkeypatch):
    import io, json, sys, usage_tap
    monkeypatch.setattr(usage_tap, "OUT", tmp_path / "u.json")
    raw = json.dumps({"rate_limits": {"five_hour": {"used_percentage": 5}}}).encode()
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(out))
    usage_tap.main()
    assert out.getvalue() == raw and json.loads((tmp_path / "u.json").read_text())["rate_limits"]["five_hour"]["used_percentage"] == 5


def test_has_data_distinguishes_failure_from_empty():
    assert not sources.has_data(None) and not sources.has_data({"US": [], "VN": []})
    assert not sources.has_data([{"symbol": "DXY"}]) and sources.has_data([])


@pytest.mark.parametrize("query, battery", [("battery=84", 84), ("battery=", None), ("battery=abc", None), ("", None), ("battery=300", None)])
def test_parse_battery_validates_input(query, battery):
    assert server.parse_battery(query) == battery


def test_truncate_and_icons():
    d = ImageDraw.Draw(Image.new("L", (10, 10)))
    cut = truncate(d, "word " * 50, font(24), 300)
    assert cut.endswith("…") and d.textlength(cut, font=font(24)) <= 300
    for code in (0, 2, 3, 45, 61, 95):
        img = Image.new("L", (200, 200), 255)
        icons.weather_icon(ImageDraw.Draw(img), code, 100, 100, 150)
        assert img.getextrema()[0] < 255


def test_quote_changes_daily_and_always_fits():
    import quotes
    from draw_right import layout_quote
    t = datetime(2026, 11, 26, 9, 0)
    assert quotes.quote_for(t) == quotes.quote_for(t + timedelta(minutes=14))
    assert quotes.quote_for(t) != quotes.quote_for(t + timedelta(minutes=15))
    d = ImageDraw.Draw(Image.new("L", (10, 10)))
    for text, _ in quotes.QUOTES:
        _, lines, _ = layout_quote(d, f"“{text}”")
        assert " ".join(lines) == f"“{text}”", text  # every quote fits without being cut off


def test_impact_score_whole_words_and_both_languages():
    from news_filter import impact_score
    assert impact_score("NHNN tăng lãi suất điều hành") >= 6
    assert impact_score("Fed signals rate cut as inflation cools") >= 9
    assert impact_score("Prices went down at the window shop") == 0  # 'dow' must not match 'down'
    assert impact_score("Cà phê ngon ở Đà Lạt") == 0


def test_market_headlines_quota_fill_and_order():
    from news_filter import market_headlines
    news = {"VN": ["Hoa hậu đăng quang", "Khối ngoại bán tháo cổ phiếu", "Tỷ giá tăng mạnh"],
            "WORLD": ["Fed holds interest rate", "Celebrity wedding", "Oil falls", "Tariffs hit stocks", "OPEC cuts oil output"]}
    picked = market_headlines(news, {"VN": 2, "WORLD": 2})
    assert picked == [("VN", "Khối ngoại bán tháo cổ phiếu"), ("VN", "Tỷ giá tăng mạnh"),
                      ("WORLD", "Fed holds interest rate"), ("WORLD", "Tariffs hit stocks")]
    short = market_headlines({"VN": ["Hoa hậu"], "WORLD": news["WORLD"]}, {"VN": 2, "WORLD": 2})
    assert len(short) == 3 and all(tag == "WORLD" for tag, _ in short)  # spare VN slots filled from WORLD
    assert market_headlines(None, {"VN": 2}) == []


def test_kindle_battery_label():
    assert render.kindle_battery({"battery": 84, "seen": NOW}, NOW) == ("Kindle 84%", 84)
    assert render.kindle_battery({"battery": 84, "seen": NOW - timedelta(minutes=10)}, NOW) == ("Kindle offline", None)
    assert render.kindle_battery(None, NOW) == ("Kindle offline", None)


def test_usage_tap_keeps_max_within_window_and_follows_new_window():
    from usage_tap import merge_window
    a, b = {"used_percentage": 39, "resets_at": 100}, {"used_percentage": 1, "resets_at": 100}
    assert merge_window(a, b) == a and merge_window(b, a) == a  # stale idle session can't lower it
    fresh = {"used_percentage": 2, "resets_at": 200}
    assert merge_window(a, fresh) == fresh and merge_window(fresh, a) == fresh  # new window wins, old ignored
    assert merge_window(None, b) == b and merge_window(a, None) == a


def test_panel_to_layout_inverts_the_image_rotation():
    import config
    from touch import panel_to_layout
    for lx, ly in [(0, 0), (1500, 880), (config.WIDTH - 1, config.HEIGHT - 1), (812, 40)]:
        img = Image.new("L", (config.WIDTH, config.HEIGHT), 255)
        img.putpixel((lx, ly), 0)
        portrait = img.rotate(config.ROTATE, expand=True)
        px, py = _find_black(portrait)
        assert panel_to_layout(px, py) == (lx, ly)


def _find_black(img):
    bbox = Image.eval(img, lambda v: 255 - v).getbbox()
    return bbox[0], bbox[1]


def test_music_buttons_hit_and_miss():
    from draw_music import BUTTON_CX, BUTTON_CY, hit_button
    for name, cx in BUTTON_CX.items():
        assert hit_button(cx, BUTTON_CY) == name
    assert hit_button(900, 300) is None  # markets area


def test_parse_tap_validates():
    assert server.parse_tap("x=10&y=20") == ((10, 20), None)
    assert server.parse_tap("x=10&y=20&sx=500&sy=21") == ((10, 20), (500, 21))
    assert server.parse_tap("x=10&y=20&sx=bad&sy=21") == ((10, 20), None)
    assert server.parse_tap("x=abc&y=1") is None and server.parse_tap("x=-1&y=5") is None and server.parse_tap("") is None


def test_parse_now_playing_and_closed_music():
    import music
    sep = music.SEP
    t = music.parse_now_playing(sep.join(["paused", "ID", "Song", "Artist", "Album", "12,5", "200", "0"]))
    assert t["state"] == "paused" and t["position"] == 12.5 and t["has_art"] is False
    assert music.parse_now_playing("not running") is None and music.parse_now_playing("stopped") is None


def test_render_with_music_and_tap_marker():
    track = {"state": "playing", "id": "x", "name": "Song", "artist": "A", "album": "B",
             "position": 30.0, "duration": 0.0, "has_art": False, "art": None}
    img = render.render({**FULL, "music": {"track": track}, "last_tap": {"x": 1500, "y": 880, "time": NOW}}, NOW)
    assert img.size == (1680, 1264)


def test_classify_swipe_vs_tap():
    from touch import classify
    assert classify(None, (100, 100)) == "tap"
    assert classify((100, 500), (120, 510)) == "tap"
    assert classify((900, 500), (300, 540)) == "swipe" and classify((300, 500), (900, 470)) == "swipe"
    assert classify((500, 100), (520, 700)) == "tap"  # vertical drag is not a page swipe


def test_with_light_is_immutable_and_targets_one_gang():
    from home_devices import with_light
    rooms = [{"id": "a", "room": "Kitchen", "gangs": [{"code": "switch_1", "name": "Table", "on": False},
                                                       {"code": "switch_2", "name": "Down", "on": True}]}]
    one = with_light(rooms, "a", "switch_1", True)
    assert [g["on"] for g in one[0]["gangs"]] == [True, True] and rooms[0]["gangs"][0]["on"] is False
    assert all(not g["on"] for g in with_light(rooms, None, None, False)[0]["gangs"])


def test_home_page_targets_cover_every_button():
    from draw_home import hit
    acs = [{"id": "x", "name": "Studio", "is_on": True, "mode": "Cool", "target": 25, "room": 23, "fan": "Low"}]
    lights = [{"id": "a", "room": "Kitchen", "gangs": [{"code": "switch_1", "name": "Table", "on": False}]}]
    _, targets = render.render_home({"acs": acs, "lights": lights}, NOW)
    kinds = sorted({(a["kind"], a.get("action", a.get("code", ""))) for *_, a in targets})
    assert kinds == [("ac", "cooler"), ("ac", "fan"), ("ac", "mode"), ("ac", "power"), ("ac", "warmer"),
                     ("brightness_auto", ""), ("brightness_slider", ""), ("light", "switch_1"), ("lights_off", "")]
    l, t, r, b, action = targets[0]
    assert hit(targets, (l + r) / 2, (t + b) / 2) == action and hit(targets, 1, 1) is None


def test_pick_active_follows_the_sound_card():
    from music import pick_active
    playing = {"state": "playing"}
    mini = {"host": "Mac mini", "track": playing, "sound_card": False}
    book = {"host": "MacBook", "track": None, "sound_card": True}
    assert pick_active([mini, book])["host"] == "MacBook"  # speakers are on the MacBook
    assert pick_active([mini, None])["host"] == "Mac mini"  # MacBook asleep
    paused = {"host": "MacBook", "track": {"state": "paused"}, "sound_card": False}
    assert pick_active([paused, mini])["host"] == "Mac mini" and pick_active([None, None]) is None


def test_with_ac_predicts_each_button_without_mutating():
    from home_devices import with_ac
    acs = [{"id": "s", "name": "Studio", "is_on": False, "mode": "Cool", "target": 25.0, "room": 24, "fan": "High"},
           {"id": "m", "name": "Master", "is_on": True, "mode": "Dry", "target": 16.0, "room": 27, "fan": "Auto"}]
    assert with_ac(acs, "s", "power")[0]["is_on"] is True and acs[0]["is_on"] is False
    assert with_ac(acs, "s", "warmer")[0]["target"] == 25.5 and with_ac(acs, "m", "cooler")[1]["target"] == 16.0
    assert with_ac(acs, "s", "mode")[0]["mode"] == "Dry" and with_ac(acs, "s", "fan")[0]["fan"] == "Auto"
    assert with_ac(acs, "s", "power")[1] is acs[1]  # other units untouched


def test_duplicate_touch_is_ignored(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "current_image", lambda: Image.new("L", (1680, 1264), 255))
    monkeypatch.setattr(server, "save_atomic", lambda *a: None)
    monkeypatch.setattr(server, "run_dashboard_tap", lambda x, y: calls.append((x, y)))
    monkeypatch.setattr(server, "last_touch_key", None)
    server.handle_tap((700, 600), (700, 600))
    server.handle_tap((700, 600), (700, 600))  # the second reader's copy
    server.handle_tap((710, 600), (710, 600))  # a genuinely new tap
    assert len(calls) == 2


def test_frame_versions_only_change_with_the_picture_and_wake_waiters():
    import threading, time as _t
    f = server.Frame()
    f.publish(b"a"); f.publish(b"a")
    assert f.version == 1  # identical picture: no new version, so the Kindle doesn't redraw
    start = _t.time()
    assert f.wait(1, timeout=0.2) == (1, b"a") and _t.time() - start >= 0.19  # nothing new: times out
    threading.Timer(0.1, f.publish, args=(b"b",)).start()
    start = _t.time()
    assert f.wait(1, timeout=5) == (2, b"b") and _t.time() - start < 1  # change arrives: returns at once


def test_slider_level_maps_and_clamps():
    from draw_home import level_at
    slider = {"left": 100, "right": 580}
    assert level_at(100, slider) == 0 and level_at(580, slider) == 24 and level_at(340, slider) == 12
    assert level_at(20, slider) == 0 and level_at(700, slider) == 24  # rounded ends of the track still count


def test_drag_that_starts_on_slider_sets_level_instead_of_swiping(monkeypatch, tmp_path):
    _, targets = render.render_home({"screen_light": 6}, NOW)
    slider = next(t for t in targets if t[4]["kind"] == "brightness_slider")
    cy = (slider[1] + slider[3]) / 2
    monkeypatch.setattr(server, "page", "home")
    monkeypatch.setattr(server, "home_targets", targets)
    monkeypatch.setattr(server, "last_touch_key", None)
    monkeypatch.setattr(server, "SCREEN_LIGHT_FILE", tmp_path / "light")
    monkeypatch.setattr(server, "publish", lambda img: b"")
    monkeypatch.setattr(server, "current_image", lambda: Image.new("L", (10, 10)))
    to_raw = lambda x, y: (int(y), int(1679 - x))  # inverse of touch.panel_to_layout for ROTATE=90
    left, right = slider[4]["left"], slider[4]["right"]
    server.handle_tap(to_raw(right, cy), to_raw(left + 10, cy))  # long horizontal drag along the slider
    assert server.screen_light == 24 and server.page == "home"
