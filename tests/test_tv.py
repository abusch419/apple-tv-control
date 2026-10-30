import asyncio

import pytest

from src.tv_mcp import history
from src.tv_mcp.appletv import AppleTV


def test_history_roundtrip(tmp_path):
    db = history.connect(str(tmp_path / "h.db"))
    a = history.add(db, "FROM", 2022, "Home server", "2026-10-25", "S1E1")
    history.add(db, "Midnight Mass", 2021, "Netflix", "2026-10-26")
    history.rate(db, a, "liked", "loved the ending")
    import os, stat
    assert stat.S_IMODE(os.stat(tmp_path / "h.db").st_mode) == 0o600
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
    assert appletv._tunnels_for("KITCHEN") == [["k", "1"]]


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
    import pwd
    owner = pwd.getpwuid(server.ROOT.stat().st_uid)
    assert calls[-3:] == [("setgroups", ([],)), ("setgid", (owner.pw_gid,)), ("setuid", (owner.pw_uid,))]


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


def test_roku_pause_never_resumes_a_paused_show(monkeypatch):
    from src.tv_mcp.roku import Roku
    sent = []
    r = Roku({"name": "g", "host": "h", "player_id": "p"})
    monkeypatch.setattr(r, "_call", lambda path, method="GET": '<player state="pause">' if method == "GET" else sent.append(path) or "")
    asyncio.run(r.press(["pause"]))
    assert sent == []


def test_ask_runs_claude_with_no_tools_and_a_minimal_env(monkeypatch):
    from src.tv_mcp import server
    seen = {}

    class Proc:
        returncode = 0
        async def communicate(self, _):
            return b"ok", b""

    async def fake_exec(*args, **kw):
        seen.update(args=args, env=kw["env"], cwd=kw["cwd"])
        return Proc()

    class Req:
        async def json(self):
            return {"text": "play FROM"}

    monkeypatch.setattr(server, "CLAUDE_CODE_OAUTH_TOKEN", "oauth")
    monkeypatch.setattr(server.asyncio, "create_subprocess_exec", fake_exec)
    asyncio.run(server.ask(Req()))
    a = seen["args"]
    assert a[a.index("--tools") + 1] == "" and "--strict-mcp-config" in a and a[a.index("--allowedTools") + 1] == "mcp__tv__*"
    assert set(seen["env"]) == {"HOME", "PATH", "CLAUDE_CODE_OAUTH_TOKEN"}
    assert a[a.index("--setting-sources") + 1] == ""
    assert seen["env"]["HOME"] == seen["cwd"] and not seen["cwd"].startswith(str(server.Path.home()))


def test_server_drops_root_and_refuses_to_start_without_a_token(monkeypatch):
    from src.tv_mcp import server
    dropped = []
    monkeypatch.setattr(server, "TOKEN", "")
    monkeypatch.setattr(server, "_drop_root", lambda: dropped.append(1))
    monkeypatch.setattr(server, "_exit_when_code_changes", lambda: None)
    monkeypatch.setattr(server.uvicorn, "run", lambda *a, **k: None)
    with pytest.raises(SystemExit):
        server.main()
    assert dropped


def test_unknown_tv_name_is_an_error_not_the_default_tv(monkeypatch):
    from src.tv_mcp import server
    monkeypatch.setattr(server, "remotes", {"Living room": object(), "Kids": object()})
    with pytest.raises(ValueError):
        server._tv("garage")


def test_auth_refuses_an_empty_token():
    from src.tv_mcp.server import BearerAuth
    with pytest.raises(ValueError):
        BearerAuth(None, "")


def test_roku_play_does_not_toggle_while_buffering(monkeypatch):
    from src.tv_mcp.roku import Roku
    sent = []
    r = Roku({"name": "g", "host": "h", "player_id": "p"})
    monkeypatch.setattr(r, "_call", lambda path, method="GET": '<player state="buffer">' if method == "GET" else sent.append(path) or "")
    asyncio.run(r.press(["play"]))
    assert sent == []


def test_ask_runs_one_at_a_time(monkeypatch):
    from src.tv_mcp import server

    class Req:
        async def json(self):
            return {"text": "x"}

    async def go():
        monkeypatch.setattr(server, "CLAUDE_CODE_OAUTH_TOKEN", "oauth")
        async with server._ask_lock:
            return await asyncio.wait_for(server.ask(Req()), 2)
    assert asyncio.run(go()).status_code == 409


def test_library_refresh_keeps_servers_when_the_account_service_is_down(monkeypatch):
    from src.tv_mcp import library

    class Acct:
        def resources(self):
            raise ConnectionError
    monkeypatch.setattr(library, "account", lambda: Acct())
    monkeypatch.setattr(library, "_servers", {"home": "srv"})
    monkeypatch.setattr(library, "_loaded_at", 0.0)
    assert library.servers() == {"home": "srv"}


def test_library_play_opens_the_library_app_on_the_roku_first(monkeypatch):
    from src.tv_mcp import server
    from src.tv_mcp.roku import Roku
    done = []
    r = Roku({"name": "g", "host": "h", "player_id": "p"})

    async def apps():
        return [("Netflix", "12"), ("Media Free Movies", "13535")]

    async def note(*a):
        done.append(a)

    async def status():
        return "ok"
    monkeypatch.setattr(r, "apps", apps)
    monkeypatch.setattr(r, "wake", lambda: note("wake"))
    monkeypatch.setattr(r, "launch", lambda i: note("launch", i))
    monkeypatch.setattr(r, "status", status)
    monkeypatch.setattr(server, "remotes", {"g": r})
    monkeypatch.setattr(server, "LIBRARY_APP", "media")
    monkeypatch.setattr(server.library, "play_on", lambda *a: done.append(("play",)) or "X")
    monkeypatch.setattr(server.asyncio, "sleep", lambda s: note())
    asyncio.run(server.library_play("srv", 1, "g"))
    assert done[:3] == [("wake",), ("launch", "13535"), ()] and ("play",) in done


def test_roku_pause_is_sent_when_the_state_is_unknown(monkeypatch):
    from src.tv_mcp.roku import Roku
    sent = []
    r = Roku({"name": "g", "host": "h", "player_id": "p"})
    monkeypatch.setattr(r, "_call", lambda path, method="GET": '<player state="close">' if method == "GET" else sent.append(path) or "")
    asyncio.run(r.press(["pause"]))
    assert sent == ["/keypress/Play"]


def test_server_only_serves_through_the_token_check(monkeypatch):
    from src.tv_mcp import server
    served = []
    monkeypatch.setattr(server, "TOKEN", "t")
    monkeypatch.setattr(server, "SONOS_FOLLOW_ROOM", "")
    monkeypatch.setattr(server, "_drop_root", lambda: None)
    monkeypatch.setattr(server.threading, "Thread", lambda **k: type("T", (), {"start": lambda self: None})())
    monkeypatch.setattr(server.uvicorn, "run", lambda app, **k: served.append(app))
    server.main()
    assert isinstance(served[0], server.BearerAuth)


def test_a_failed_screenshot_after_a_press_is_not_an_error(monkeypatch):
    from src.tv_mcp import server

    class TV:
        async def press(self, b):
            pass

        async def screenshot(self):
            raise RuntimeError("tunnel down")
    monkeypatch.setattr(server, "remotes", {"t": TV()})
    real_sleep = asyncio.sleep
    monkeypatch.setattr(server.asyncio, "sleep", lambda s: real_sleep(0))
    assert asyncio.run(server.press(["select"], "t")).startswith("Sent.")


def test_sonos_group_slider_moving_both_keeps_their_new_share():
    from src.tv_mcp.sonos_follow import step
    ratios, expected = {}, {}
    step(40, None, {"roam": 20}, ratios, expected)
    assert step(60, 40, {"roam": 30}, ratios, expected) == {}
    assert step(30, 60, {"roam": 30}, ratios, expected) == {"roam": 15}


def test_tv_names_prefer_an_exact_match_and_accept_the_roku_label(monkeypatch):
    from src.tv_mcp import server
    kids, bedroom = object(), object()
    monkeypatch.setattr(server, "remotes", {"Kids Bedroom": kids, "Bedroom": bedroom})
    assert server._tv("bedroom") is bedroom
    assert server._tv("Bedroom (Roku)") is bedroom
