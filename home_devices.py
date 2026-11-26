"""Home page devices: Smart Life (Tuya cloud) light switches and Panasonic Comfort Cloud air conditioners.

Loaders return plain dicts for drawing; controls take the ids/actions the Home page's buttons carry.
"""
import asyncio
import logging
import threading
from concurrent.futures import Future

import aiohttp
import tinytuya
from aio_panasonic_comfort_cloud import ApiClient
from aio_panasonic_comfort_cloud import constants as pcc

from config import PANASONIC_TOKEN_FILE, secret

log = logging.getLogger("dashboard")
NOT_A_LIGHT = {"switch_backlight", "switch_inching", "countdown"}
AC_TIMEOUT = 20
TEMP_STEP, TEMP_MIN, TEMP_MAX = 0.5, 16.0, 30.0
MODE_CYCLE = [pcc.OperationMode.Cool, pcc.OperationMode.Dry, pcc.OperationMode.Fan, pcc.OperationMode.Auto]
FAN_CYCLE = [pcc.FanSpeed.Auto, pcc.FanSpeed.Low, pcc.FanSpeed.LowMid, pcc.FanSpeed.Mid,
             pcc.FanSpeed.HighMid, pcc.FanSpeed.High]


# --- Smart Life lights -------------------------------------------------------

_tuya: tinytuya.Cloud | None = None
_gang_names: dict[str, dict[str, str]] = {}  # device id -> {switch code: name}; names rarely change


def tuya() -> tinytuya.Cloud:
    global _tuya
    if _tuya is None:
        if not secret("TUYA_ACCESS_ID"):
            raise RuntimeError("TUYA_ACCESS_ID not set in .secrets.env")
        _tuya = tinytuya.Cloud(apiRegion=secret("TUYA_REGION") or "us", apiKey=secret("TUYA_ACCESS_ID"),
                               apiSecret=secret("TUYA_ACCESS_SECRET"))
    return _tuya


def short_name(gang: str, room: str) -> str:
    """'Table Lights Kitchen' in room 'Kitchen' -> 'Table Lights'."""
    trimmed = gang.replace(room, "").strip(" -·")
    return trimmed or gang


def _names(dev_id: str) -> dict[str, str]:
    if dev_id not in _gang_names:
        result = tuya().cloudrequest(f"/v1.0/devices/{dev_id}/multiple-names").get("result") or []
        _gang_names[dev_id] = {r["identifier"]: r["name"] for r in result}
    return _gang_names[dev_id]


def get_lights() -> list[dict]:
    """[{'id', 'room', 'gangs': [{'code', 'name', 'on'}]}], in the app's device order."""
    rooms = []
    for dev in tuya().getdevices(verbose=False):
        status = tuya().getstatus(dev["id"]).get("result") or []
        names = _names(dev["id"])
        gangs = [{"code": s["code"], "name": short_name(names.get(s["code"], s["code"]), dev["name"]), "on": s["value"]}
                 for s in status
                 if isinstance(s.get("value"), bool) and s["code"].startswith("switch") and s["code"] not in NOT_A_LIGHT]
        if gangs:
            rooms.append({"id": dev["id"], "room": dev["name"], "gangs": gangs})
    return rooms


def set_light(dev_id: str, code: str, is_on: bool) -> None:
    result = tuya().sendcommand(dev_id, {"commands": [{"code": code, "value": is_on}]})
    if not result.get("success"):
        raise RuntimeError(f"Tuya refused {code}={is_on}: {result.get('msg')}")


# --- Panasonic air conditioners ---------------------------------------------

class PanasonicBridge:
    """The library is asyncio; the server is threaded. Run one event loop + logged-in client in a thread."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True, name="panasonic").start()
        self._api: ApiClient | None = None

    def _run(self, coro) -> object:
        future: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=AC_TIMEOUT)

    async def _client(self) -> ApiClient:
        if self._api is None:
            session = aiohttp.ClientSession()
            api = ApiClient(secret("PANASONIC_EMAIL"), secret("PANASONIC_PASSWORD"), session,
                            token_file_name=str(PANASONIC_TOKEN_FILE))
            await api.start_session()  # reuses and refreshes the token saved by panasonic_login.py
            self._api = api
        return self._api

    async def _states(self) -> list[dict]:
        api = await self._client()
        out = []
        for info in api.get_devices():
            p = (await api.get_device(info)).parameters
            out.append({"id": info.id, "name": info.name, "is_on": p.power == pcc.Power.On, "mode": p.mode.name,
                        "target": p.target_temperature, "room": p.inside_temperature, "fan": p.fan_speed.name})
        return out

    async def _control(self, device_id: str, action: str) -> None:
        api = await self._client()
        info = next(i for i in api.get_devices() if i.id == device_id)
        p = (await api.get_device(info)).parameters
        if action == "power":
            await api.set_device(info, power=pcc.Power.Off if p.power == pcc.Power.On else pcc.Power.On)
        elif action in ("warmer", "cooler"):
            step = TEMP_STEP if action == "warmer" else -TEMP_STEP
            await api.set_device(info, temperature=min(TEMP_MAX, max(TEMP_MIN, (p.target_temperature or 25) + step)))
        elif action == "mode":
            await api.set_device(info, mode=next_in(MODE_CYCLE, p.mode))
        elif action == "fan":
            await api.set_device(info, fanSpeed=next_in(FAN_CYCLE, p.fan_speed))
        else:
            raise ValueError(f"unknown AC action {action!r}")

    def states(self) -> list[dict]:
        return self._run(self._states())

    def control(self, device_id: str, action: str) -> None:
        self._run(self._control(device_id, action))


def next_in(cycle: list, current) -> object:
    """Next value after `current`, wrapping; the first one if `current` isn't in the cycle."""
    return cycle[(cycle.index(current) + 1) % len(cycle)] if current in cycle else cycle[0]


_bridge: PanasonicBridge | None = None


def panasonic() -> PanasonicBridge:
    global _bridge
    if _bridge is None:
        _bridge = PanasonicBridge()
    return _bridge


def get_acs() -> list[dict]:
    return panasonic().states()


# --- Home page actions -----------------------------------------------------------

def with_light(lights: list[dict], dev_id: str | None, code: str | None, is_on: bool) -> list[dict]:
    """New lights list with one gang (or, with dev_id None, every gang) set to is_on. Shows taps instantly."""
    return [{**room, "gangs": [{**g, "on": is_on} if dev_id is None or (room["id"] == dev_id and g["code"] == code)
                               else g for g in room["gangs"]]}
            for room in lights]


def run_home_action(action: dict, lights: list[dict] | None) -> tuple[str, object]:
    """Perform a Home page button; return (source name, new value or None to re-fetch)."""
    kind = action.get("kind")
    if kind == "light":
        set_light(action["id"], action["code"], action["on"])
        return "lights", with_light(lights or [], action["id"], action["code"], action["on"])
    if kind == "lights_off":
        for room in lights or []:
            on = [{"code": g["code"], "value": False} for g in room["gangs"] if g["on"]]
            if on:
                tuya().sendcommand(room["id"], {"commands": on})
        return "lights", with_light(lights or [], None, None, False)
    if kind == "ac":
        panasonic().control(action["id"], action["action"])
        return "acs", None
    raise ValueError(f"unknown home action {action!r}")


def with_ac(acs: list[dict], device_id: str, action: str) -> list[dict]:
    """New AC list showing what `action` will do, so the screen can update before Panasonic confirms."""
    def apply(ac: dict) -> dict:
        if ac["id"] != device_id:
            return ac
        if action == "power":
            return {**ac, "is_on": not ac["is_on"]}
        if action in ("warmer", "cooler"):
            step = TEMP_STEP if action == "warmer" else -TEMP_STEP
            return {**ac, "target": min(TEMP_MAX, max(TEMP_MIN, (ac["target"] or 25) + step))}
        if action == "mode":
            names = [m.name for m in MODE_CYCLE]
            return {**ac, "mode": names[(names.index(ac["mode"]) + 1) % len(names)] if ac["mode"] in names else names[0]}
        if action == "fan":
            names = [f.name for f in FAN_CYCLE]
            return {**ac, "fan": names[(names.index(ac["fan"]) + 1) % len(names)] if ac["fan"] in names else names[0]}
        return ac
    return [apply(ac) for ac in acs]


def predict(action: dict, latest: dict) -> tuple[str, list[dict]] | None:
    """(source, optimistic value) for a Home button, or None if there's nothing to predict yet."""
    kind = action.get("kind")
    if kind == "light" and latest.get("lights"):
        return "lights", with_light(latest["lights"], action["id"], action["code"], action["on"])
    if kind == "lights_off" and latest.get("lights"):
        return "lights", with_light(latest["lights"], None, None, False)
    if kind == "ac" and latest.get("acs"):
        return "acs", with_ac(latest["acs"], action["id"], action["action"])
    return None
