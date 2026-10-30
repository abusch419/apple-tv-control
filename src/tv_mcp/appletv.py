import asyncio
import io
import json
import sys
import tempfile
import urllib.request

import pyatv
from PIL import Image as PILImage
from pyatv.const import Protocol

from src.tv_mcp.settings import TUNNELD_URL, TVS

BUTTONS = {
    "up", "down", "left", "right", "select", "menu", "home", "home_hold",
    "play", "pause", "stop", "next", "previous",
    "skip_forward", "skip_backward", "volume_up", "volume_down",
}

_SCREENSHOT = (
    "import sys, pymobiledevice3.dtx._reader as r; r.MAX_BUFFERED_SIZE = 256 << 20; "
    "from pymobiledevice3.__main__ import main; sys.argv[0] = 'pymobiledevice3'; sys.exit(main())"
)


class AppleTV:
    def __init__(self, tv: dict):
        self.tv = tv
        self._atv = None
        self._lock = asyncio.Lock()

    async def _connect(self):
        loop = asyncio.get_running_loop()
        found = await pyatv.scan(loop, identifier=self.tv["id"], timeout=5)
        if not found:
            raise RuntimeError(f"{self.tv['name']} isn't answering on the network. Is it on?")
        conf = found[0]
        conf.set_credentials(Protocol.Companion, self.tv["companion"])
        return await pyatv.connect(conf, loop)

    async def _run(self, fn, timeout: float = 15):
        async with self._lock:
            for attempt in (1, 2):
                try:
                    if self._atv is None:
                        self._atv = await asyncio.wait_for(self._connect(), 15)
                    return await asyncio.wait_for(fn(self._atv), timeout)
                except Exception:
                    if self._atv is not None:
                        self._atv.close()
                    self._atv = None
                    if attempt == 2:
                        raise

    async def press(self, buttons: list[str]) -> None:
        bad = [b for b in buttons if b not in BUTTONS and not b.startswith("wait:")]
        if bad:
            raise ValueError(f"Unknown buttons {bad}. Use: {sorted(BUTTONS)} or wait:<seconds>")

        async def go(atv):
            for b in buttons:
                if b.startswith("wait:"):
                    await asyncio.sleep(min(float(b[5:]), 30))
                else:
                    await getattr(atv.remote_control, b)()
                    await asyncio.sleep(0.5)
        waits = sum(min(float(b[5:]), 30) for b in buttons if b.startswith("wait:"))
        await self._run(go, timeout=15 + waits + len(buttons))

    async def type_text(self, text: str) -> None:
        await self._run(lambda atv: atv.keyboard.text_set(text))

    async def wake(self) -> None:
        await self._run(lambda atv: atv.power.turn_on())

    async def launch(self, bundle_id: str) -> None:
        await self._run(lambda atv: atv.apps.launch_app(bundle_id))

    async def apps(self) -> list[tuple[str, str]]:
        async def go(atv):
            return [(a.name, a.identifier) for a in await atv.apps.app_list()]
        return await self._run(go)

    async def screenshot(self) -> bytes:
        err = b""
        for rsd in 3 * await asyncio.to_thread(_tunnels_for, self.tv["udid"]):
            with tempfile.NamedTemporaryFile(suffix=".png") as f:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-c", _SCREENSHOT, "developer", "dvt", "screenshot", "--rsd", *rsd, f.name,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                try:
                    _, err = await asyncio.wait_for(proc.communicate(), timeout=30)
                except asyncio.TimeoutError:
                    proc.kill()
                    continue
                if proc.returncode == 0:
                    img = PILImage.open(f.name).convert("RGB")
                    break
        else:
            raise RuntimeError(f"Screenshot failed: {err.decode()[-400:]}")
        img.thumbnail((1280, 720))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        return buf.getvalue()


def _tunnels_for(udid: str) -> list[list[str]]:
    try:
        with urllib.request.urlopen(TUNNELD_URL, timeout=5) as r:
            tunnels = json.load(r)
    except OSError:
        raise RuntimeError("The screen connection service (tunneld) isn't running. See README: Troubleshooting.")
    others = {t["udid"] for t in TVS} - {udid}
    entries = tunnels.get(udid) or [e for k, v in tunnels.items() if k not in others for e in v]
    if not entries:
        raise RuntimeError("No screen connection to this TV yet. It reconnects on its own within a minute; if not, see README: Troubleshooting.")
    return [[e["tunnel-address"], str(e["tunnel-port"])] for e in entries]
