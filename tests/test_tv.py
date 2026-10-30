import asyncio

import pytest

from src.tv_mcp import history
from src.tv_mcp.appletv import AppleTV


def test_history_roundtrip(tmp_path):
    db = history.connect(str(tmp_path / "h.db"))
    a = history.add(db, "FROM", 2022, "Home server", "2026-10-25", "S1E1")
    history.add(db, "Midnight Mass", 2021, "Netflix", "2026-10-26")
    history.rate(db, a, "liked", "loved the ending")
    rows = history.recent(db)
    assert [r["title"] for r in rows] == ["Midnight Mass", "FROM"]
    assert rows[1]["rating"] == "liked" and rows[1]["notes"] == "loved the ending"


def test_history_rejects_unknown_rating(tmp_path):
    db = history.connect(str(tmp_path / "h.db"))
    with pytest.raises(ValueError):
        history.rate(db, history.add(db, "X"), "meh")


def test_press_rejects_unknown_buttons_before_touching_tv():
    tv = AppleTV({"name": "t", "id": "x", "companion": "", "udid": ""})
    with pytest.raises(ValueError, match="Unknown buttons"):
        asyncio.run(tv.press(["up", "jump"]))


def test_tunnel_falls_back_to_the_only_tunnel(monkeypatch):
    import io, json
    from src.tv_mcp import appletv
    registry = {"OTHER-ID": [{"tunnel-address": "fd00::1", "tunnel-port": 1234}]}
    monkeypatch.setattr(appletv.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(registry).encode()))
    assert appletv._tunnels_for("SAVED-ID") == [["fd00::1", "1234"]]


def test_auth_accepts_header_or_secret_path_and_rejects_others():
    from src.tv_mcp.server import BearerAuth
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["path"])

    def call(path, headers=()):
        sent = []
        async def send(m):
            sent.append(m)
        asyncio.run(BearerAuth(app, "s3cret")({"type": "http", "path": path, "headers": list(headers)}, None, send))
        return sent[0]["status"] if sent else 200

    assert call("/mcp", [(b"authorization", b"Bearer s3cret")]) == 200
    assert call("/s3cret/mcp") == 200
    assert seen == ["/mcp", "/mcp"]
    assert call("/mcp") == 401
    assert call("/mcp", [(b"authorization", b"Bearer wrong")]) == 401
    assert call("/wrong/mcp") == 401
    assert call("/s3cretX/mcp") == 401
    assert seen == ["/mcp", "/mcp"]


def test_sonos_group_follows_main_speaker_keeping_ratio():
    from src.tv_mcp.sonos_follow import step
    ratios, expected = {}, {}
    assert step(40, None, {"roam": 30}, ratios, expected) == {}
    assert step(60, 40, {"roam": 30}, ratios, expected) == {"roam": 45}
    assert step(20, 60, {"roam": 45}, ratios, expected) == {"roam": 15}
    assert step(20, 20, {"roam": 10}, ratios, expected) == {}
    assert step(40, 20, {"roam": 10}, ratios, expected) == {"roam": 20}
    assert step(100, 40, {"roam": 20}, ratios, expected) == {"roam": 50}
    assert step(0, 100, {"roam": 50}, ratios, expected) == {"roam": 0}
    assert step(41, 0, {}, ratios, expected) == {} and ratios == {}


def test_screenshot_never_falls_back_to_another_paired_tv(monkeypatch):
    import io, json
    from src.tv_mcp import appletv
    tunnels = {"KITCHEN": [{"tunnel-address": "k", "tunnel-port": 1}], "OLD-ID": [{"tunnel-address": "o", "tunnel-port": 2}]}
    monkeypatch.setattr(appletv, "TVS", [{"udid": "KITCHEN"}, {"udid": "BASEMENT"}])
    monkeypatch.setattr(appletv.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(json.dumps(tunnels).encode()))
    assert appletv._tunnels_for("BASEMENT") == [["o", "2"]]
    assert appletv._tunnels_for("KITCHEN") == [["k", "1"], ["o", "2"]]


def test_roku_maps_buttons_and_rejects_unknown(monkeypatch):
    from src.tv_mcp.roku import Roku
    sent = []
    r = Roku({"name": "guest", "host": "h", "player_id": "p"})
    monkeypatch.setattr(r, "_call", lambda path, method="GET": sent.append((path, method)) or "")
    asyncio.run(r.press(["up", "select", "menu"]))
    assert sent == [("/keypress/Up", "POST"), ("/keypress/Select", "POST"), ("/keypress/Back", "POST")]
    with pytest.raises(ValueError, match="Unknown buttons"):
        asyncio.run(r.press(["jump"]))


def test_server_never_keeps_root(monkeypatch):
    from src.tv_mcp import server
    calls = []
    monkeypatch.setattr(server.os, "geteuid", lambda: 0)
    monkeypatch.setenv("HOME", "/tmp")
    for fn in ("setgroups", "setgid", "setuid", "chown"):
        monkeypatch.setattr(server.os, fn, lambda *a, fn=fn: calls.append((fn, a)))
    server._drop_root()
    owner = server.ROOT.stat()
    assert calls[-3:] == [("setgroups", ([],)), ("setgid", (owner.st_gid,)), ("setuid", (owner.st_uid,))]


def test_roku_play_never_toggles_a_playing_show(monkeypatch):
    from src.tv_mcp.roku import Roku
    sent = []
    r = Roku({"name": "guest", "host": "h", "player_id": "p"})
    def call(path, method="GET"):
        if method == "GET":
            return '<player state="play" error="false">'
        sent.append(path)
        return ""
    monkeypatch.setattr(r, "_call", call)
    asyncio.run(r.press(["play"]))
    assert sent == []
    asyncio.run(r.press(["pause"]))
    assert sent == ["/keypress/Play"]
