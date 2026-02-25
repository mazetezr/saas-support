#!/usr/bin/env bash
# run_local.sh — Start Cloudflare Tunnel + Bot together.
# Kills the tunnel when the bot stops (or Ctrl+C).
#
# Usage: bash run_local.sh

set -e

CLOUDFLARED="/c/Program Files (x86)/cloudflared/cloudflared.exe"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== SaaS Support Bot — Local Dev ===${NC}"
echo ""

# --- Verify cloudflared ---
if [ ! -f "$CLOUDFLARED" ]; then
    echo -e "${RED}cloudflared not found at: $CLOUDFLARED${NC}"
    echo "Install: winget install Cloudflare.cloudflared"
    exit 1
fi

# --- Cleanup on exit ---
TUNNEL_PID=""

cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    if [ -n "$TUNNEL_PID" ] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
        echo "Stopping cloudflared tunnel (PID $TUNNEL_PID)..."
        kill "$TUNNEL_PID" 2>/dev/null
        wait "$TUNNEL_PID" 2>/dev/null
    fi
    echo -e "${GREEN}Done.${NC}"
}

trap cleanup EXIT INT TERM

# --- Start Cloudflare Tunnel in background ---
echo -e "${GREEN}[1/2] Starting Cloudflare Tunnel...${NC}"
echo "      webhook.thejarvisbot.com -> localhost:8080"
echo ""

"$CLOUDFLARED" tunnel run support-bot &
TUNNEL_PID=$!

# Wait for tunnel to initialize
sleep 3

if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo -e "${RED}Cloudflare tunnel failed to start!${NC}"
    exit 1
fi

echo -e "${GREEN}Tunnel running (PID $TUNNEL_PID)${NC}"
echo ""

# --- Start the bot ---
echo -e "${GREEN}[2/2] Starting bot...${NC}"
echo ""

cd "$PROJECT_DIR"
source venv/Scripts/activate
python -m bot

# When bot exits, cleanup() will kill the tunnel
