#!/usr/bin/env bash
# Connects a Claude Pro or Max plan to this deployment, the way the desktop app's "Claude plan" choice
# does: the Claude Agent SDK harness runs as the picked Bot, and the built-in Bots answer through it.
#
#   claude setup-token                 # on your own machine, signed in to your Claude plan
#   bash scripts/setup-claude-plan.sh  # paste the sk-ant-oat... token when asked
#   bash scripts/start.sh
#
# The token can also be passed as CLAUDE_CODE_OAUTH_TOKEN in the environment. It is written to .env,
# which git ignores, and nowhere else.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
IMAGE="openbot-agent-claude-sdk:latest"
PORT=4212

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }

if [ ! -f "$ENV_FILE" ]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
  green "Created .env from .env.example."
fi

# Replaces the key's line, or appends one. Values are written as given, without quoting.
upsert() {
  local name="$1" value="$2" tmp
  tmp="$(mktemp)"
  grep -vE "^$name=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$name" "$value" >> "$tmp"
  cat "$tmp" > "$ENV_FILE"
  rm -f "$tmp"
}

current() {
  grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true
}

TOKEN="${CLAUDE_CODE_OAUTH_TOKEN:-}"
if [ -z "$TOKEN" ]; then
  echo "Run \`claude setup-token\` on a machine where you are signed in to your Claude plan,"
  echo "then paste the token it prints (it starts with sk-ant-oat). Input is hidden."
  read -rs -p "Token: " TOKEN
  echo
fi
TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
case "$TOKEN" in
  sk-ant-oat*) ;;
  sk-ant-api*)
    red "That is an API key, not a plan token. Put it in ANTHROPIC_API_KEY instead, or run \`claude setup-token\`."
    exit 1 ;;
  *)
    red "That does not look like a token from \`claude setup-token\` (expected sk-ant-oat...)."
    exit 1 ;;
esac

if ! docker info >/dev/null 2>&1; then
  red "Docker is not running. Start it and run this again."
  exit 1
fi
echo "Building the Claude Agent SDK Bot ($IMAGE)..."
docker build -q -f "$ROOT/agent-claude-sdk/Dockerfile" -t "$IMAGE" "$ROOT" >/dev/null
green "Built $IMAGE."

# The plan, and nothing that would outrank it. The SDK prefers ANTHROPIC_API_KEY over the OAuth
# token, so a stale key would quietly bill instead of the plan; the server refuses a ChatGPT plan
# alongside this one.
upsert CLAUDE_CODE_OAUTH_TOKEN "$TOKEN"
upsert ANTHROPIC_API_KEY ""
upsert CHATGPT_AUTH_FILE ""

# The picked harness, as the desktop app writes it for an installed image.
upsert PICKED_HARNESS_SOURCE installed
upsert PICKED_HARNESS_IMAGE "$IMAGE"
upsert PICKED_HARNESS_PORT "$PORT"
upsert PICKED_HARNESS_NAME "Claude"
upsert PICKED_HARNESS_KIND remote-ag-ui
upsert PICKED_HARNESS_URL "http://127.0.0.1:$PORT"

# Shared by the server and the harness. start.sh would mint one too, but the harness is started from
# the same .env, so writing it here keeps the two from ever disagreeing.
if [ -z "$(current MANAGED_AGENT_TOKEN)" ]; then
  upsert MANAGED_AGENT_TOKEN "$(openssl rand -base64 32)"
fi

green "Claude plan connected. Next:"
if [ -z "$(current INTELLIGENCE_API_KEY)" ]; then
  echo "  1. INTELLIGENCE_API_KEY is still empty: see README → Quick start, step 2."
  echo "  2. bash scripts/start.sh"
else
  echo "  bash scripts/start.sh"
fi
