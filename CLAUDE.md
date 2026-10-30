# tv-remote: agent notes

An MCP server ("tv") that lets Claude pick something to watch and start it on an Apple TV or Roku. People say what they feel like; Claude does the rest.

## Rules
- Zero friction for the people watching: never ask them to do setup or manage the watch diary. When a manual step is truly needed, ask for one action at a time.
- Look before you act. Take a screenshot after every step; never steer a TV blind. If screenshots are black, find out why before pressing anything.
- When someone says "leave it" or "don't touch the TV", stop until they ask again.
- This repo is public. No personal data, names, tokens or diary entries in tracked files. Secrets live in `.env` (gitignored).
- Each install keeps its own diary (`history.db`, gitignored).
- Ask before anything public (new repo, release notes aside from version bumps the owner asked for).

## Decisions
- Runs on an always-on Mac as two root LaunchDaemons (tunneld for screenshots, mcp on port 8790). The server restarts itself when its code changes.
- Media library first, streaming apps second.
- Rokus are driven by Roku's network remote and get library titles pushed straight to the library app; they can't screenshot.
- Product and docs never name the media server brand; it only appears in the library dependency.
- Grouped Sonos speakers follow the soundbar as a share of its volume.

## Rejected
- Xcode or developer-mode tooling beyond pymobiledevice3's tunnel.
- Pushing library titles to the Apple TV's library app: it doesn't answer reliably (works on Roku).
- Falling back to another TV's screen connection (showed the wrong TV).
