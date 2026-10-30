import logging
import threading
import time

import soco

log = logging.getLogger(__name__)


def step(main_volume: int, last_main: int | None, members: dict, ratios: dict, expected: dict) -> dict:
    changes = {}
    for uid, current in members.items():
        if uid not in ratios or current != expected.get(uid, current):
            ratios[uid] = current / main_volume if main_volume else ratios.get(uid, 1.0)
            expected[uid] = current
        if last_main is not None and main_volume != last_main:
            target = max(0, min(100, round(main_volume * ratios[uid])))
            if target != current:
                changes[uid] = target
                expected[uid] = target
    for uid in list(ratios):
        if uid not in members:
            ratios.pop(uid)
            expected.pop(uid, None)
    return changes


def _find(room: str):
    for zone in soco.discover(timeout=5) or []:
        if zone.player_name == room:
            return zone
    return None


def run(room: str, interval: float = 0.5) -> None:
    main, last_main, ratios, expected = None, None, {}, {}
    while True:
        try:
            main = main or _find(room)
            if main is None:
                time.sleep(30)
                continue
            volume = main.volume
            others = {m.uid: m for m in main.group.members if m.uid != main.uid}
            changes = step(volume, last_main, {uid: m.volume for uid, m in others.items()}, ratios, expected)
            for uid, target in changes.items():
                others[uid].volume = target
            last_main = volume
            time.sleep(interval)
        except Exception as e:
            log.warning("Sonos follow: %s", e)
            main, last_main = None, None
            time.sleep(10)


def start(room: str) -> None:
    threading.Thread(target=run, args=(room,), daemon=True, name="sonos-follow").start()
