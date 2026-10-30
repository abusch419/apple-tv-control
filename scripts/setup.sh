#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"

export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv -q --allow-existing --python 3.13 .venv
uv pip install -q --python .venv/bin/python -r requirements.txt

grep -q '^TV_MCP_TOKEN=' .env 2>/dev/null || .venv/bin/python scripts/pair.py
chmod 600 .env
[ -d "$HOME/.pymobiledevice3" ] && chmod -R go-rwx "$HOME/.pymobiledevice3"

sudo -v
[ -e history.db ] && sudo chown "$USER" history.db
sed -e "s|__REPO__|$REPO|g" -e "s|__HOME__|$HOME|g" scripts/tunneld.plist | sudo tee /Library/LaunchDaemons/com.appletvcontrol.tunneld.plist >/dev/null
sed -e "s|__REPO__|$REPO|g" -e "s|__HOME__|$HOME|g" -e "s|__USER__|$USER|g" scripts/mcp.plist | sudo tee /Library/LaunchDaemons/com.appletvcontrol.mcp.plist >/dev/null
for svc in tunneld mcp; do
  sudo launchctl bootout system/com.appletvcontrol.$svc 2>/dev/null || true
  while sudo launchctl print system/com.appletvcontrol.$svc >/dev/null 2>&1; do sleep 1; done
  sudo launchctl bootstrap system /Library/LaunchDaemons/com.appletvcontrol.$svc.plist
done

TOKEN=$(grep '^TV_MCP_TOKEN=' .env | cut -d= -f2)
HOST="$(scutil --get LocalHostName).local"
cat <<EOF

Done. The TV service is running and starts on its own whenever this Mac boots.

Connect Claude Code on any computer on this Wi-Fi:
  claude mcp add --scope user --transport http tv http://$HOST:8790/mcp --header "Authorization: Bearer $TOKEN"

Claude Desktop: see README "Connect Claude Desktop" and use
  URL:   http://$HOST:8790/mcp
  Token: $TOKEN
EOF
