"""One-time Panasonic Comfort Cloud login for accounts that sign in with Google (no password to store).

  .venv/bin/python panasonic_login.py start            -> prints a URL to open in your browser
  .venv/bin/python panasonic_login.py finish 'URL'     -> paste the panasonic-iot-cfc://... URL you were sent to
  .venv/bin/python panasonic_login.py test             -> lists your AC units (read-only)

The token is saved to .panasonic-token (git-ignored) and refreshed automatically by the dashboard afterwards.
"""
import asyncio
import os
import sys

import aiohttp
from aio_panasonic_comfort_cloud import ApiClient

from config import PANASONIC_TOKEN_FILE, ROOT, secret

VERIFIER_FILE = ROOT / ".panasonic-verifier"  # short-lived, deleted after finish


async def flush(api: ApiClient) -> None:
    # shortcut: the library saves tokens in background tasks with no public flush; wait on them before exiting
    await asyncio.gather(*list(getattr(api._settings, "_pending_saves", ())))


def client(session: aiohttp.ClientSession) -> ApiClient:
    # Google-login accounts have no password; the saved token is what authenticates
    return ApiClient(secret("PANASONIC_EMAIL"), secret("PANASONIC_PASSWORD"), session,
                     token_file_name=str(PANASONIC_TOKEN_FILE))


async def start() -> None:
    async with aiohttp.ClientSession() as session:
        url, verifier = client(session).get_browser_authorization_url()
    VERIFIER_FILE.write_text(verifier)
    os.chmod(VERIFIER_FILE, 0o600)
    print("1. Open this URL in a browser and sign in with Google:\n")
    print(url)
    print("\n2. After signing in, copy the address starting with panasonic-iot-cfc:// (see README),")
    print("   then run:  .venv/bin/python panasonic_login.py finish 'panasonic-iot-cfc://...'")


async def finish(redirect: str) -> None:
    if not VERIFIER_FILE.exists():
        sys.exit("Run 'start' first.")
    async with aiohttp.ClientSession() as session:
        api = client(session)
        await api._settings.is_ready()
        await api.complete_browser_authentication(redirect.strip(), VERIFIER_FILE.read_text().strip())
        await flush(api)
    VERIFIER_FILE.unlink()
    os.chmod(PANASONIC_TOKEN_FILE, 0o600)
    print("Logged in. Token saved to .panasonic-token")
    await test()


async def test() -> None:
    async with aiohttp.ClientSession() as session:
        api = client(session)
        await api.start_session()
        await flush(api)
        devices = api.get_devices()
        print(f"{len(devices)} device(s):")
        for info in devices:
            dev = await api.get_device(info)
            p = dev.parameters
            print(f"  - {info.name}: power={p.power.name} mode={p.mode.name} set={p.target_temperature}°C "
                  f"room={p.inside_temperature}°C fan={p.fan_speed.name}")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "start":
        asyncio.run(start())
    elif action == "finish" and len(sys.argv) > 2:
        asyncio.run(finish(sys.argv[2]))
    elif action == "test":
        asyncio.run(test())
    else:
        sys.exit(__doc__)
