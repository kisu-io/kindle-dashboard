# Kindle home-office dashboard

A jailbroken **Kindle Oasis 2** turned into a 70s-styled e-ink dashboard and smart-home remote. A small Python server, running on a Mac on your network, draws the screen. The Kindle shows it and sends your touches back.

**Dashboard page:** clock with the âm lịch date, weather with a 3-day forecast and a 12-hour chart, rain in the next 2 hours, AQI, triều cường (tide) times, US / Việt Nam / crypto quotes with small charts, gold and DXY charts, USD/VND, Apple Music now playing with controls, a rotating quote or upcoming high-impact US economic events, market-moving headlines, Claude plan usage, and an alert bar.

**Home page** (swipe, or press a page-turn button): Panasonic Comfort Cloud air conditioners (power, temperature, mode, fan), Smart Life (Tuya) light switches, and a screen-light slider.

## How it works

- **Server (Mac):** `server.py` fetches each data source on its own schedule and renders a 1680×1264 landscape image. It serves the image to the Kindle (rotated to the panel) and a browser preview at `http://<mac>:8080/`.
- **Updates:** the Kindle long-polls. The server holds each request until the picture actually changes, so updates appear in well under a second, with no redraw when nothing changes.
- **Touch:** a small LuaJIT script (using KOReader's bundled `luajit`) reads the touch screen and sends taps and swipes to `/tap`. The server runs the button under your finger and sends back a fresh image. Device commands run in the background, and the screen updates immediately.
- **Exiting:** the power button exits the dashboard. If the server can't be reached 4 times in a row, the Kindle restores its normal UI by itself.

## Server setup

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp config_local.example.py config_local.py   # your location, other Macs
.venv/bin/python server.py
```

**Run at login:** `./install_service.sh` installs a LaunchAgent that starts the server when you log in and restarts it if it crashes (log: `~/Library/Logs/kindle-dashboard.log`; remove with `./install_service.sh uninstall`). With FileVault on, macOS waits at the unlock screen after a reboot, so use `sudo fdesetup authrestart` for planned restarts.

Edit `config.py` (or override it in `config_local.py`) to change the location, tickers, news feeds and alert thresholds.

Secrets go in `.secrets.env`, as `KEY=VALUE` lines. It's git-ignored; run `chmod 600 .secrets.env`.

| Key | For |
|---|---|
| `TUYA_ACCESS_ID`, `TUYA_ACCESS_SECRET`, `TUYA_REGION` | Smart Life lights: a free [Tuya developer](https://platform.tuya.com) cloud project linked to your Smart Life app |
| `MUSIC_AGENT_TOKEN` | any random string, shared with other Macs running `music_agent.py` |
| `PANASONIC_EMAIL`, `PANASONIC_PASSWORD` | optional; not needed when you sign in with Google |

**Panasonic login** (works with Google sign-in): run `.venv/bin/python panasonic_login.py start` and open the printed URL with DevTools open (Console or Network). After you sign in, copy the `panasonic-iot-cfc://…` address that the browser failed to open, then run `panasonic_login.py finish '<address>'`. The token is saved to `.panasonic-token` and refreshed automatically.

**Apple Music on more than one Mac:** run `music_agent.py install --token <MUSIC_AGENT_TOKEN>` on each extra Mac and add it to `MUSIC_REMOTES`. The dashboard follows whichever Mac your USB sound card is plugged into (it looks for "Scarlett", the Focusrite; change `SOUND_CARD` in `music_agent.py`). It listens only on Tailscale and needs the token.

**Claude usage** (optional): put `python3 /path/to/usage_tap.py | ` in front of your Claude Code `statusLine` command. It copies the plan's 5-hour and weekly limits to `.claude_usage.json`.

## Kindle setup (jailbroken, with KUAL and KOReader)

1. Write your server address into `kindle/extensions/dashboard/server_url`, e.g. `http://192.168.1.10:8080`. See `server_url.example`.
2. Copy `kindle/extensions/dashboard/` to the Kindle's USB drive at `extensions/dashboard/`.
3. KUAL → **Home Dashboard → Start dashboard**. Keep the Kindle plugged in.

Exit with the **power button**. The dashboard locks the screen orientation and holds the front light at the level you choose (or leaves it on Auto). It writes `dashboard.log` next to the script.

## Files

| File | What |
|---|---|
| `config.py`, `config_local.example.py` | settings |
| `sources.py` | data fetchers and refresh schedule |
| `home_devices.py`, `panasonic_login.py` | Tuya lights and Panasonic AC |
| `music.py`, `music_agent.py` | Apple Music across Macs |
| `alerts.py`, `news_filter.py`, `quotes.py`, `lunar.py` | alert rules, headline scoring, quotes, âm lịch |
| `render.py`, `draw_*.py`, `icons.py` | drawing |
| `touch.py`, `server.py` | touch mapping, server loops and HTTP |
| `install_service.sh` | run the server at login (LaunchAgent) |
| `usage_tap.py` | Claude Code status-line tap |
| `kindle/extensions/dashboard/` | the Kindle side: `dashboard.sh`, `tap.lua`, KUAL menu |

Tests: `.venv/bin/pytest`

## Notes

- **Unofficial sources:** several sources are unofficial and could change without notice: Yahoo Finance, the VPS feed, Panasonic Comfort Cloud (via `aio-panasonic-comfort-cloud`), the ForexFactory feed and the Open-Meteo tide model. US and VN quotes are delayed about 15 minutes.
- **Tide model:** the triều cường times come from a sea-level model at the nearest sea point, not an official station.
- **Fonts:** all under the SIL Open Font License, see `fonts/`. Be Vietnam Pro for body text, Paytone One for headings and numbers, Righteous for the clock.

MIT licensed.
