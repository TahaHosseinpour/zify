# Data for every host in the `production` group (see inventory.py).
# Read inside the deploy with `host.data.get("<key>")`.

import sys
from pathlib import Path

# group_data files are loaded by pyinfra before deploy.py gets a chance to
# put deploy/ on sys.path, so do it here too - this file needs to import
# deploy_secrets on its own.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import deploy_secrets as secrets
except ImportError as e:
    raise ImportError(
        "deploy/deploy_secrets.py is missing - copy "
        "deploy/deploy_secrets.example.py to deploy/deploy_secrets.py and "
        "fill in the real values (it's gitignored on purpose, see "
        "deploy/README.md)."
    ) from e

# Domain the site answers on (plus its `www.` alias - see tasks/nginx.py).
# `None` would mean the site only answers on whichever vhost on this shared
# box holds `default_server` (not this one). zifyai.ir already has a working
# Let's Encrypt certificate from the previous ad-hoc deploy at /root/zify -
# tasks/nginx.py picks that existing certificate up automatically (it only
# calls certbot when none is found), so this does not trigger a new
# issuance.
site_domain = "zifyai.ir"

# Where the app lives. Each deploy builds into <web_root>/releases/<id> (a
# full `bun install` + `next build` + `uv sync` there) and only then moves
# the <web_root>/current symlink, so pm2/nginx never pick up a half-built
# release. <web_root>/shared/.env holds the generated secrets (DB password,
# JWT secret) plus everything synced from this file and deploy_secrets.py,
# and persists across releases - see templates/setup-env.sh.j2. It is a
# single file shared by all three apps (admin, agent, bot), same as local
# dev's root .env - see apps/admin/next.config.ts, apps/agent/main.py and
# apps/telegram-bot/package.json, which all resolve it the same way.
web_root = "/var/www/zify"

# The app (pm2, tasks/service.py) and the build (tasks/website.py) both run
# as this user. Left as root for the same reason as valida's deploy (see its
# own group_data comment): small single-purpose VPS, harden later with a
# dedicated system user if this ever needs it.
site_user = "root"

# Each release carries its own full node_modules *and* a full Python venv
# (uv sync for the agent), so keep few of them around. The release being
# deployed and the one `current` points at are always kept regardless.
keep_releases = 2

# Size of the swapfile tasks/website.py creates for the duration of the build
# and removes right after (success or failure - see its own comment). This
# server has no permanent swap (deliberately - it's shared with other sites,
# and a permanent swapfile is one more thing to remember is there), and
# `bun install` + `uv sync` + `next build` running back to back on a ~2GB box
# can peak higher than that alone.
build_swap_mb = 2048

# Refuse to build when less than this much disk is free (after pruning old
# releases). Higher than valida's default: on top of node_modules, every
# release also gets a from-scratch `uv sync` venv (langgraph/langchain
# pull in a fair amount).
min_free_disk_mb = 4000

# How long to wait for a PostgreSQL cluster to start accepting connections
# before failing the deploy (seconds) - see templates/ensure-postgres.sh.j2.
postgres_startup_timeout = 30

# Install this public key into root's authorized_keys on the first run, so
# the password is only ever needed once. Set to None to skip. If this is the
# same machine that already deployed valida to this server, the key is
# probably already there and this is a no-op.
ssh_public_key_file = "~/.ssh/id_ed25519.pub"

server_timezone = "Asia/Tehran"

# --- App runtime ---

# Node.js major version installed via NodeSource (tasks/system.py). The apps
# themselves run on Bun (also installed there), but Node is kept as a safety
# net for any dependency whose install/build script shells out to a literal
# `node` rather than relying on Bun's shebang handling.
node_major_version = 20

# Ports the three services listen on (see ecosystem.config.cjs at the repo
# root, which pm2 runs as-is). `app_port` (admin, Next.js) is hard-coded to
# 3010 *in that file*, so changing it here alone does nothing - edit both.
# `agent_port` really is read from the shared .env at runtime
# (apps/agent/main.py reads AGENT_PORT), so changing it here is enough.
# nginx (tasks/nginx.py) only reverse-proxies the admin app; the agent and
# the bot are not publicly exposed.
app_port = 3010
agent_port = 3011

# --- Database (tasks/database.py) ---
#
# Matches local dev's docker-compose.yml naming (POSTGRES_USER/POSTGRES_DB)
# so the two are never confused. Installed with apt (no Docker on the VPS,
# same reasoning as valida's deploy), plus the `vector` extension (pgvector)
# that Prisma's migrations expect (packages/db/prisma/migrations/0001_init_pgvector).
db_name = "zify_db"
db_user = "zify"

# --- OpenAI / tracing config (non-secret) - see deploy_secrets.py for keys ---

openai_base_url = "https://api.tapsage.com/openai/v1"
openai_chat_model = "gpt-4o-mini"
openai_embedding_model = "text-embedding-3-small"

# Second providers the agent fails over to when the ones above stop answering
# (apps/agent/app/failover.py). Served by the same Metis key. Set a base URL
# to "" to turn that failover off.
deepseek_base_url = "https://api.metisai.ir/deepseek/v1"
deepseek_chat_model = "deepseek-v4-flash"
gemini_base_url = "https://api.metisai.ir/v1beta"
gemini_embedding_model = "gemini-embedding-001"

langsmith_tracing = True
langsmith_endpoint = "https://api.smith.langchain.com"
langsmith_project = "Zify"

# Always False on the server - USE_LOCAL_MODELS (apps/agent/app/graph.py) is a
# local-only escape hatch onto a laptop's own Ollama instance, and the
# production box doesn't even have a GPU to run one against. Committed
# explicitly (not just left unset) so it's visible here rather than relying
# on setup-env.sh.j2 simply never having written the key.
use_local_models = False

# Only used if deploy_secrets.langfuse_public_key/secret_key are set.
langfuse_host = "https://cloud.langfuse.com"

# --- SMS / bot config ---

# True until smsir_api_key (deploy_secrets.py) is filled in: OTP codes are
# then returned by the API instead of texted, same as local dev - see
# apps/admin's SMS_MOCK usage and valida's OTP_DEV_MODE for the same idea.
sms_mock = not bool(secrets.smsir_api_key)

bot_username = "zifyai_bot"

# --- Secrets (deploy/deploy_secrets.py, gitignored) ---
openai_api_key = secrets.openai_api_key
langsmith_api_key = secrets.langsmith_api_key
langfuse_public_key = secrets.langfuse_public_key
langfuse_secret_key = secrets.langfuse_secret_key
smsir_api_key = secrets.smsir_api_key
smsir_template_id = secrets.smsir_template_id
telegram_bot_token = secrets.telegram_bot_token

# Opt-in extras - both are off until you decide otherwise.
#
# configure_firewall: enables ufw with only SSH/HTTP/HTTPS open. This is a
# SHARED box (valida is already on it) - if you turn this on, double check
# nothing else on the server depends on a port this doesn't allow first.
configure_firewall = False
#
# letsencrypt_email: with `site_domain` set as well, certbot obtains and
# installs a certificate and turns on the HTTPS redirect. Fill in once the
# domain is known.
letsencrypt_email = None
