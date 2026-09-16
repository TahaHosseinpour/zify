# Zify inventory - the servers pyinfra is allowed to touch.
#
# This is the same VPS the `valida` project already lives on (shared box, one
# nginx in front of several named vhosts - see tasks/nginx.py). Your SSH
# public key should already be authorized there from valida's first deploy;
# if it isn't (different machine, different key), pass
# `--ssh-password-prompt` on the first run and it will be installed.
#
# Per-host values here override the matching keys in group_data/production.py.

from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent

production = [
    (
        "181.41.194.141",
        {
            "ssh_user": "root",
            "ssh_port": 22,
            # Keepalives and timeouts - see the comments in deploy/ssh_config.
            "ssh_config_file": str(DEPLOY_DIR / "ssh_config"),
            # Ride out a flaky first connection instead of failing the deploy.
            "ssh_connect_retries": 3,
        },
    ),
]
