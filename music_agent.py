#!/usr/bin/env python3
"""Apple Music helper for one Mac: Now Playing, play/pause/skip, and whether the Focusrite is plugged in here.

Standard library only, so it can be copied to any Mac. The dashboard server imports it for the local Mac and
talks to it over Tailscale for other Macs:

  python3 music_agent.py install --token TOKEN    # on another Mac: save token, start at login (LaunchAgent)
  python3 music_agent.py uninstall
  python3 music_agent.py serve                     # what the LaunchAgent runs
"""
from __future__ import annotations  # macOS /usr/bin/python3 can be 3.9

import argparse
import ipaddress
import json
import os
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8765
HOME_DIR = Path.home() / ".kindle-music"
TOKEN_FILE = HOME_DIR / "token"
ART_FILE = HOME_DIR / "artwork.img"
LABEL = "com.kindle-dashboard.music-agent"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
SOUND_CARD = "Scarlett"  # USB product name prefix of the Focusrite (Scarlett 6i6 USB)
ALLOWED_NETS = [ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("127.0.0.0/8")]  # Tailscale + local
SEP = "\x1f"  # unit separator: never appears in track names
OSASCRIPT_TIMEOUT = 10

NOW_PLAYING = f'''
if application "Music" is not running then return "not running"
tell application "Music"
  if player state is stopped then return "stopped"
  set t to current track
  return (player state as text) & "{SEP}" & (persistent ID of t) & "{SEP}" & (name of t) & "{SEP}" & (artist of t) ¬
    & "{SEP}" & (album of t) & "{SEP}" & (player position as text) & "{SEP}" & (duration of t as text) ¬
    & "{SEP}" & ((count of artworks of t) as text)
end tell
'''

SAVE_ARTWORK = '''
tell application "Music" to set artData to data of artwork 1 of current track
set f to open for access POSIX file "{path}" with write permission
set eof f to 0
write artData to f
close access f
'''

COMMANDS = {
    # play/pause opens Music and plays if it is closed; skips only act on a running Music
    "playpause": 'if application "Music" is running then\ntell application "Music" to playpause\nelse\n'
                 'tell application "Music" to play\nend if',
    "next": 'if application "Music" is running then tell application "Music" to next track',
    "previous": 'if application "Music" is running then tell application "Music" to previous track',
}


def osascript(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=OSASCRIPT_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[:200])
    return result.stdout.strip()


def _number(text: str) -> float:
    return float(text.replace(",", "."))  # AppleScript uses the locale's decimal mark


def parse_now_playing(raw: str) -> dict | None:
    """None when Music is closed or stopped; otherwise the track and playback state."""
    parts = raw.split(SEP)
    if len(parts) != 8:
        return None
    state, track_id, name, artist, album, position, duration, artworks = parts
    return {"state": state, "id": track_id, "name": name, "artist": artist, "album": album,
            "position": _number(position), "duration": _number(duration), "has_art": int(artworks) > 0}


def has_sound_card() -> bool:
    """True when the Focusrite is on this Mac's USB, i.e. this Mac is the one the speakers hear."""
    out = subprocess.run(["ioreg", "-p", "IOUSB", "-w0"], capture_output=True, text=True, timeout=5).stdout
    return SOUND_CARD.lower() in out.lower()


def now_playing() -> dict:
    return {"track": parse_now_playing(osascript(NOW_PLAYING)), "sound_card": has_sound_card(),
            "host": socket.gethostname().split(".")[0]}


def save_artwork(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    osascript(SAVE_ARTWORK.format(path=path))


def control(action: str) -> None:
    if action not in COMMANDS:
        raise ValueError(f"unknown music action {action!r}")
    osascript(COMMANDS[action])


# --- HTTP service for other Macs ---------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _allowed(self) -> bool:
        ip = ipaddress.ip_address(self.client_address[0])
        token = self.headers.get("X-Token", "")
        return any(ip in net for net in ALLOWED_NETS) and token and token == TOKEN_FILE.read_text().strip()

    def _reply(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._allowed():
            self._reply(403, b'{"error": "forbidden"}')
            return
        url = urlparse(self.path)
        try:
            if url.path == "/now":
                self._reply(200, json.dumps(now_playing()).encode())
            elif url.path == "/art":
                save_artwork(ART_FILE)
                self._reply(200, ART_FILE.read_bytes(), "application/octet-stream")
            elif url.path == "/control":
                control(parse_qs(url.query).get("action", [""])[0])
                self._reply(200, b'{"ok": true}')
            else:
                self._reply(404, b'{"error": "not found"}')
        except Exception as exc:  # report to the dashboard instead of dropping the connection
            self._reply(500, json.dumps({"error": str(exc)[:200]}).encode())

    def log_message(self, fmt: str, *args) -> None:  # polled every few seconds; keep logs quiet
        pass


def serve() -> None:
    if not TOKEN_FILE.exists():
        sys.exit(f"No token at {TOKEN_FILE}; run: python3 {__file__} install --token TOKEN")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


PLIST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key><array><string>{python}</string><string>{script}</string><string>serve</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>{home}/agent.log</string>
</dict></plist>
"""


def install(token: str) -> None:
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token.strip())
    os.chmod(TOKEN_FILE, 0o600)
    script = HOME_DIR / "music_agent.py"
    if Path(__file__).resolve() != script.resolve():
        script.write_bytes(Path(__file__).read_bytes())
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_text(PLIST_XML.format(label=LABEL, python=sys.executable, script=script, home=HOME_DIR))
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(PLIST)], capture_output=True)  # ok if not loaded
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST)], check=True)
    print(f"Installed. Listening on port {PORT}; starts at login. Testing Music access (approve the prompt)...")
    print(json.dumps(now_playing(), indent=2))


def uninstall() -> None:
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(PLIST)], capture_output=True)
    PLIST.unlink(missing_ok=True)
    print("Uninstalled (token and copy remain in ~/.kindle-music; delete that folder to remove everything).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["install", "uninstall", "serve"])
    parser.add_argument("--token")
    args = parser.parse_args()
    if args.command == "install":
        if not args.token:
            sys.exit("install needs --token")
        install(args.token)
    elif args.command == "uninstall":
        uninstall()
    else:
        serve()
