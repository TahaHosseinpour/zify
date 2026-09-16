"""Zify deploy - run with:

    python -m pyinfra deploy/inventory.py deploy/deploy.py --ssh-password-prompt

See deploy/README.md. Everything here is declarative: run it as often as you
like, it only changes what is actually out of date.
"""

import sys
from pathlib import Path

# pyinfra only puts the working directory on sys.path, so make `tasks` and
# `paths` importable no matter which directory the deploy is started from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tasks.database import database  # noqa: E402
from tasks.nginx import https, nginx  # noqa: E402
from tasks.service import app_service  # noqa: E402
from tasks.system import base_system, firewall  # noqa: E402
from tasks.website import prepare_release, website  # noqa: E402

# First, because everything below it needs disk: this prunes the releases the
# server no longer serves and stops the deploy outright if there still isn't
# room to build. A full disk here doesn't just fail the build - it takes
# PostgreSQL down with it, and the deploy then fails in `database()` with a
# socket error that looks like something else entirely.
prepare_release()

base_system()
database()

# The app is built (bun install, uv sync, prisma generate/migrate, next
# build, seed) and only then told to serve, so neither pm2 nor nginx ever
# come up against a half-ready release.
website()
app_service()
nginx()

https()
firewall()
