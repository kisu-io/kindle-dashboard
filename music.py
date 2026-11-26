"""Apple Music across Macs: show and control the Mac the Focusrite (and so the speakers) is plugged into.

The local Mac is read directly (music_agent functions); other Macs run music_agent.py as a service on Tailscale.
"""
import json
import logging
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import music_agent as agent
from config import MUSIC_LOCAL_NAME, MUSIC_REMOTES, OUT_DIR, secret
from music_agent import SEP, parse_now_playing  # noqa: F401  (re-exported for tests/callers)

log = logging.getLogger("dashboard")
REMOTE_TIMEOUT = 4
_pool = ThreadPoolExecutor(max_workers=4)
_art_for: dict[str, str] = {}  # host -> track id whose artwork is on disk


def _remote(url: str, path: str) -> bytes:
    req = urllib.request.Request(url.rstrip("/") + path, headers={"X-Token": secret("MUSIC_AGENT_TOKEN")})
    with urllib.request.urlopen(req, timeout=REMOTE_TIMEOUT) as resp:
        return resp.read()


def _status(host: str) -> dict | None:
    """{'host', 'track', 'sound_card'} or None when that Mac is asleep/offline."""
    try:
        status = agent.now_playing() if host == MUSIC_LOCAL_NAME else json.loads(_remote(MUSIC_REMOTES[host], "/now"))
    except Exception as exc:  # asleep, off Tailscale, or Music permission missing
        log.debug("music status from %s failed: %r", host, exc)
        return None
    return {**status, "host": host}


def pick_active(statuses: list[dict | None]) -> dict | None:
    """The Mac with the sound card wins; then one that is playing; then one with a track loaded."""
    online = [s for s in statuses if s]
    if not online:
        return None

    def rank(s: dict) -> tuple:
        track = s.get("track")
        return (bool(s.get("sound_card")), bool(track) and track["state"] == "playing", bool(track))

    return max(online, key=rank)


def _art_path(host: str) -> Path:
    return OUT_DIR / f"artwork-{''.join(c if c.isalnum() else '_' for c in host)}.img"


def _artwork(host: str, track: dict) -> Path | None:
    """Fetch artwork once per track; returns the local file, or None."""
    path = _art_path(host)
    if not track["has_art"]:
        return None
    if _art_for.get(host) != track["id"] or not path.exists():
        try:
            if host == MUSIC_LOCAL_NAME:
                agent.save_artwork(path)
            else:
                path.write_bytes(_remote(MUSIC_REMOTES[host], "/art"))
            _art_for[host] = track["id"]
        except Exception as exc:
            log.warning("artwork from %s failed: %r", host, exc)
            return None
    return path


def hosts() -> list[str]:
    return [MUSIC_LOCAL_NAME, *MUSIC_REMOTES]


def get_now_playing() -> dict:
    """{'track': {...} or None, 'host': name}. Wrapped so 'nothing playing' isn't mistaken for a failed fetch."""
    active = pick_active(list(_pool.map(_status, hosts())))
    if not active:
        return {"track": None, "host": MUSIC_LOCAL_NAME}
    track = active.get("track")
    return {"track": {**track, "art": _artwork(active["host"], track)} if track else None, "host": active["host"]}


def control(action: str, host: str | None = None) -> None:
    host = host if host in hosts() else MUSIC_LOCAL_NAME
    if host == MUSIC_LOCAL_NAME:
        agent.control(action)
    else:
        _remote(MUSIC_REMOTES[host], "/control?" + urllib.parse.urlencode({"action": action}))
