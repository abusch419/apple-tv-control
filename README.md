# tv-remote

Tell Claude what you feel like watching. It picks the best match from your media server and streaming apps, then drives your Apple TV or Roku to start it, looking at the screen as it goes. Over time it learns what you've seen and what you liked.

> "Find us a highly rated, very binge-worthy Halloween series."
> → Claude picks FROM (unwatched, 96% on Rotten Tomatoes), sets it to English, opens the library app, searches, presses Watch, and checks the screen to confirm it's playing.

It runs as a small service on a Mac at home. Anyone in the house connects their own Claude (Claude Code or Claude Desktop, on their own subscription) and just talks to it.

## What you need

- An Apple TV (tvOS 17 or newer) or a Roku, and a Mac that stays on at home, all on the same Wi-Fi.
- A media server account (optional). Shared servers work too.
- 10 minutes, standing near the TV.

## Setup

### What the human does

1. Get the code onto the always-on Mac (your agent can do this) and keep the TV on.
2. When asked, read **two codes off the TV**:
   - a 4-digit code (lets the Mac press remote buttons), then
   - on the TV go to **Settings > Remotes and Devices > Remote App and Devices**, and read the 6-digit code that appears (lets the Mac see the screen).
3. If you link a media server: open your media server's device-link page on your phone and type the 4-character code setup shows you.
4. Type your **Mac password** once, so the service can start on its own whenever the Mac boots.

That's it. You never manage a server again.

### What the agent does

Run everything on the always-on Mac, in the repo folder.

1. Clone: `git clone https://github.com/abusch419/tv-remote ~/tv-remote && cd ~/tv-remote`
2. Run `scripts/setup.sh` **in a terminal the human can see and type into**, and have the human type the TV codes there themselves. The TV's codes expire in about a minute, so relaying them through chat usually fails. It also asks for the Mac password.
   - It installs `uv` and Python 3.13 if missing, creates `.venv`, pairs the TV, links the media server, writes `.env` (secrets, never commit it), and installs two background services:
     - `com.appletvcontrol.tunneld` (root): keeps the screen connection to the TV open.
     - `com.appletvcontrol.mcp` (as the user): the MCP server on port 8790.
3. At the end it prints the exact connect command and token. Run it for the human (see Connect below).
4. Verify: in a fresh Claude session, ask it to take a TV screenshot. You should get an image of the TV.
5. Roku: turn on Settings > System > Advanced system settings > Control by mobile apps > Network access > Enabled on the Roku. Open the library app on it once, then add `ROKU_1_NAME`, `ROKU_1_HOST` (its IP) and `ROKU_1_PLAYER_ID` to `.env`. The player id is the `machineIdentifier` from `curl http://<roku-ip>:8324/resources`. Number more as `ROKU_2_...`, then restart the service: `sudo launchctl kickstart -k system/com.appletvcontrol.mcp`. A Roku-only home works: setup skips Apple TV pairing when it finds none.
6. More than one Apple TV: run `.venv/bin/python scripts/pair.py` again for each one, then restart the screen connection: `sudo launchctl kickstart -k system/com.appletvcontrol.tunneld`.
7. Pair on the Mac that will run the service. A TV pairing belongs to the computer that made it and can't be copied to another Mac.

## Connect

### Claude Code

```bash
claude mcp add --scope user --transport http tv http://<mac-name>.local:8790/mcp --header "Authorization: Bearer <token>"
```

### Claude Desktop

Claude Desktop's built-in "custom connector" only reaches servers on the public internet, so use the bridge `mcp-remote` (needs Node.js). In **Settings > Developer > Edit Config**, add:

```json
{
  "mcpServers": {
    "tv": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://<mac-name>.local:8790/mcp", "--allow-http", "--header", "Authorization:${TV_AUTH}"],
      "env": { "TV_AUTH": "Bearer <token>" }
    }
  }
}
```

Then just say what you want to watch.

## How it works

- **Remote control:** [pyatv](https://pyatv.dev) over Apple's Companion protocol (buttons, typing, opening apps).
- **Seeing the screen:** [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) opens a developer tunnel to the TV and takes screenshots. No Xcode needed.
- **Roku:** Roku's own network remote (ECP, port 8060). No pairing, but on the Roku turn on Settings > System > Advanced system settings > Control by mobile apps > Network access > Enabled. Rokus can't send screenshots, so Claude checks which app is open and whether it's playing instead, and starts library titles on them directly.
- **Picking:** media server libraries and watch status, plus a watch diary (`history.db`) that Claude keeps on its own: what you watched, when, and whether you liked it. Each install starts with an empty diary of its own.
- **The brain** is whichever Claude you're talking to. The MCP server's instructions teach it the routine: check history, pick one, set the audio language, drive the TV with screenshots, and confirm it's playing.

Tools: `screenshot`, `press`, `type_text`, `open_app`, `list_apps`, `list_tvs`, `now_playing`, `library_search`, `library_browse`, `library_set_audio_language`, `library_play`, `history_list`, `history_log`, `history_rate`.

## Optional: Sonos group volume

If your TV sound goes to a Sonos soundbar and you group other Sonos speakers with it, the TV remote only changes the soundbar. Set `SONOS_FOLLOW_ROOM=<soundbar room name>` in `.env` and restart the service: grouped speakers then follow the soundbar's volume changes, each keeping its own share of it (set a speaker to 75% of the soundbar once and it stays at 75%).

## Updating

**Use v1.1.0 or newer.** Older copies freeze on busy screens (YouTube, photo screensavers) and stop responding until restarted.

Tell your Claude:

> Update tv-remote: in its folder run `git pull`, then `scripts/setup.sh`. I'll type my Mac password when asked.

You type your Mac password once. Setup keeps your pairing and diary; it refreshes the libraries and the background services.

## Troubleshooting

- **TV stops responding:** update to v1.1.0 or newer (see Updating).

- **"Screen connection service isn't running":** `sudo launchctl kickstart -k system/com.appletvcontrol.tunneld`, then check `~/Library/Logs/tv-remote-tunneld.log`.
- **"No screen connection to this TV yet":** wait a minute after the TV wakes. If it persists, re-pair: `.venv/bin/python scripts/pair.py`.
- **Server logs:** `~/Library/Logs/tv-remote-mcp.log`.
- **Black screenshots during playback in some streaming apps** (HBO Max): copy protection blanks the capture. Menus and rating cards still show.
- **Black screenshots on a TV you just paired:** restart the screen connection (`sudo launchctl kickstart -k system/com.appletvcontrol.tunneld`).
- **The library app won't resume with play/pause:** press select (center click) instead.
- **Commands hang for minutes:** the computer running Claude went to sleep. Wake it and try again.

## Security

What this installs and what it can reach, so you can decide if it's right for you:

- **It controls your TV and reads its screen.** Anyone holding the token in `.env` can press buttons, open apps, see screenshots, change library audio settings, read and write your watch diary, and (if you set up the Siri `/ask` endpoint with `CLAUDE_CODE_OAUTH_TOKEN`) run a TV-only Claude on your subscription. The token also works as the first part of the URL path (`/<token>/mcp`) for apps that can't send headers, so a URL like that is as sensitive as the token. Treat the token like a house key; don't paste it into chats or post it. To replace it, put a new random value in `TV_MCP_TOKEN` and restart the service (`sudo launchctl kickstart -k system/com.appletvcontrol.mcp`).
- **It listens on every network this Mac is on** (port 8790): your Wi-Fi, plus any VPN like Tailscale. Every request must carry the token. It uses plain HTTP, so someone already on your Wi-Fi could see the token in transit, and when it starts library titles on a Roku the media server sign-in also crosses the Wi-Fi in plain text. Don't forward port 8790 to the internet.
- **The server runs as you, not as admin.** The part that listens on the network runs under your own account. The screen connection (`tunneld`) runs as admin, because opening a tunnel to the TV needs it; it listens on this Mac only and takes no requests from the network. It runs from the install folder, which your account can edit, so anything already running as you could use it to get admin rights on the next restart. Only install on a Mac you trust.
- **The Siri `/ask` endpoint runs a locked-down Claude.** It gets no built-in tools (no files, no shell), none of your Claude settings, and an empty temporary home folder: only the TV tools.
- **Your watch diary and secrets are private to your account** (`.env` and `history.db` are readable only by you), and logs live in `~/Library/Logs`, not the shared `/tmp`.
- **Your data stays on your Mac.** `.env` (pairing keys, media server sign-in, token) and `history.db` (watch diary) are created on your machine, are never committed, and are never sent anywhere except to your own TV and media server.
- **Screens, show text and diary notes are treated as content.** Claude is told never to follow instructions that appear on the TV, in show descriptions or in the watch diary.
- **Uninstall:** `sudo launchctl bootout system/com.appletvcontrol.mcp; sudo launchctl bootout system/com.appletvcontrol.tunneld; sudo rm /Library/LaunchDaemons/com.appletvcontrol.*.plist`, then delete the folder. Sign this Mac out of your media server's list of authorized devices. To revoke the TV pairing, remove this Mac under Settings > Remotes and Devices on the Apple TV.

## License

MIT
