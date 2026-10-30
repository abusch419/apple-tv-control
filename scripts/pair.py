import asyncio
import ipaddress
import secrets
import sys
from pathlib import Path

import pyatv
from plexapi.myplex import MyPlexPinLogin
from pyatv.const import Protocol
from pymobiledevice3.bonjour import browse_remotepairing_manual_pairing
from pymobiledevice3.exceptions import RemotePairingCompletedError
from pymobiledevice3.remote.tunnel_service import RemotePairingManualPairingService


ENV = Path(__file__).resolve().parents[1] / ".env"


def read_env() -> dict:
    if not ENV.exists():
        return {}
    return dict(line.split("=", 1) for line in ENV.read_text().splitlines() if "=" in line and not line.startswith("#"))


def write_env(values: dict) -> None:
    env = read_env() | values
    ENV.write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    ENV.chmod(0o600)


def ask(prompt: str) -> str:
    return input(f"\n>>> {prompt} ").strip()


async def pick_tv(loop):
    print("Looking for Apple TVs on this network...")
    tvs = [c for c in await pyatv.scan(loop, timeout=5) if "Apple TV" in str(c.device_info)]
    if not tvs:
        sys.exit("No Apple TV found. Make sure it's on and on the same Wi-Fi as this Mac.")
    for i, c in enumerate(tvs, 1):
        print(f"  {i}. {c.name}  ({c.address})")
    choice = ask("Which TV? Type its number:") if len(tvs) > 1 else "1"
    return tvs[int(choice) - 1]


async def pair_remote(loop, conf) -> str:
    handler = await pyatv.pair(conf, Protocol.Companion, loop)
    await handler.begin()
    handler.pin(int(ask(f"A 4-digit code is on {conf.name} now. Type it here:")))
    await handler.finish()
    await handler.close()
    if not handler.has_paired:
        sys.exit("That code didn't work. Run setup again.")
    return handler.service.credentials


async def pair_screen(conf) -> str:
    ask(f"On {conf.name}, open Settings > Remotes and Devices > Remote App and Devices, leave it on that screen, then press Enter here.")
    for _ in range(6):
        for answer in await browse_remotepairing_manual_pairing():
            if answer.properties.get("name") != conf.name:
                continue
            ipv4 = [a.full_ip for a in answer.addresses if ipaddress.ip_address(a.full_ip.split("%")[0]).version == 4]
            udid = answer.properties["identifier"]
            print("Found it. A code will appear on the TV; type it when asked.")
            async with RemotePairingManualPairingService(udid, (ipv4 or [answer.addresses[0].full_ip])[0], answer.port) as service:
                try:
                    await service.connect(autopair=True)
                except RemotePairingCompletedError:
                    pass
            return udid
        await asyncio.sleep(2)
    sys.exit("The TV isn't showing up for pairing. Check it's on the Remote App and Devices screen, then run setup again.")


def link_library() -> str:
    login = MyPlexPinLogin()
    ask(f"Media server: on any phone or computer, open your media server's device-link page and enter the code {login.pin} (press Enter here after).")
    login.run(timeout=300)
    login.waitForLogin()
    if not login.token:
        sys.exit("The media server wasn't linked. Run setup again.")
    return login.token


async def main():
    loop = asyncio.get_running_loop()
    env = read_env()
    n = 1
    while f"ATV_{n}_NAME" in env:
        n += 1

    conf = await pick_tv(loop)
    existing = next((k[:-5] for k, v in env.items() if k.endswith("_NAME") and v == conf.name), None)
    prefix = existing or f"ATV_{n}"

    credentials = await pair_remote(loop, conf)
    udid = await pair_screen(conf)
    write_env({
        f"{prefix}_NAME": conf.name,
        f"{prefix}_ID": conf.identifier,
        f"{prefix}_COMPANION": credentials,
        f"{prefix}_UDID": udid,
    })
    print(f"\n{conf.name} is paired. If the service is already running, restart the screen connection so it picks this TV up:")
    print("  sudo launchctl kickstart -k system/com.appletvcontrol.tunneld")

    if not env.get("LIBRARY_TOKEN") and ask("Do you have a media server library to link? (y/n)").lower().startswith("y"):
        write_env({"LIBRARY_TOKEN": link_library()})
        print("Media server linked.")
    if not env.get("TV_MCP_TOKEN"):
        write_env({"TV_MCP_TOKEN": secrets.token_hex(24)})


if __name__ == "__main__":
    asyncio.run(main())
