import asyncio
import re
import urllib.parse
import urllib.request

KEYS = {
    "up": "Up", "down": "Down", "left": "Left", "right": "Right", "select": "Select", "menu": "Back",
    "home": "Home", "play": "Play", "pause": "Play", "skip_forward": "Fwd", "skip_backward": "Rev",
    "volume_up": "VolumeUp", "volume_down": "VolumeDown",
}


class Roku:
    def __init__(self, tv: dict):
        self.tv = tv
        self.base = f"http://{tv['host']}:8060"

    def _call(self, path: str, method: str = "GET") -> str:
        req = urllib.request.Request(self.base + path, method=method, data=b"" if method == "POST" else None)
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                return r.read().decode()
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise RuntimeError("The Roku blocks remote control. On it: Settings > System > Advanced system settings > Control by mobile apps > Network access > Enabled.")
            raise

    async def press(self, buttons: list[str]) -> None:
        bad = [b for b in buttons if b not in KEYS and not b.startswith("wait:")]
        if bad:
            raise ValueError(f"Unknown buttons {bad}. Use: {sorted(KEYS)} or wait:<seconds>")
        for b in buttons:
            if b.startswith("wait:"):
                await asyncio.sleep(min(float(b[5:]), 30))
            elif b in ("play", "pause") and await self._skip(b):
                continue
            else:
                await asyncio.to_thread(self._call, f"/keypress/{KEYS[b]}", "POST")
                await asyncio.sleep(0.5)

    async def _skip(self, button: str) -> bool:
        found = re.search(r'<player state="(\w+)"', await asyncio.to_thread(self._call, "/query/media-player"))
        state = found.group(1) if found else ""
        return state in ("play", "buffer", "startup") if button == "play" else state == "pause"

    async def type_text(self, text: str) -> None:
        for ch in text:
            await asyncio.to_thread(self._call, "/keypress/Lit_" + urllib.parse.quote(ch, safe=""), "POST")

    async def wake(self) -> None:
        await asyncio.to_thread(self._call, "/keypress/PowerOn", "POST")

    async def launch(self, app_id: str) -> None:
        await asyncio.to_thread(self._call, f"/launch/{app_id}", "POST")

    async def apps(self) -> list[tuple[str, str]]:
        xml = await asyncio.to_thread(self._call, "/query/apps")
        return [(name, app_id) for app_id, name in re.findall(r'<app id="(\d+)"[^>]*>([^<]+)</app>', xml)]

    async def status(self) -> str:
        app = await asyncio.to_thread(self._call, "/query/active-app")
        player = await asyncio.to_thread(self._call, "/query/media-player")
        name = re.search(r"<app[^>]*>([^<]+)</app>", app)
        state = re.search(r'<player state="(\w+)"', player)
        pos = re.search(r"<position>(\d+) ms", player)
        out = f"App: {name.group(1) if name else 'home screen'}. Player: {state.group(1) if state else 'idle'}"
        return out + (f" at {int(pos.group(1)) // 60000} min." if pos else ".")
