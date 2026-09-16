"""Base state every Zify server needs before the site can be served: base
apt packages, Node.js (safety net - see group_data's comment), Bun (what the
apps actually run on), uv (the agent's Python/venv manager), and your SSH key.

Bun and uv both install into $HOME (root's home, since site_user is root) via
their official install scripts, which is *not* necessarily on PATH for every
future non-interactive `server.shell` call or for the systemd unit `pm2
startup` writes later. Rather than chase that through every task file, this
symlinks the handful of binaries actually invoked by bare name (`bun`, in
ecosystem.config.cjs; `pm2`, everywhere in tasks/service.py) into
/usr/local/bin, which is on PATH everywhere, including systemd's default
service PATH."""

from pathlib import Path

from pyinfra import host
from pyinfra.api import deploy
from pyinfra.facts.deb import DebPackages
from pyinfra.facts.files import File
from pyinfra.operations import apt, server


@deploy("Base system")
def base_system():
    apt.packages(
        name="Install base packages",
        packages=["ca-certificates", "curl", "unzip", "gzip", "tar", "gnupg", "openssl"],
        update=True,
        # Skip `apt update` when the cache was refreshed in the last hour, so
        # repeat deploys don't pay for it every time.
        cache_time=3600,
    )

    timezone = host.data.get("server_timezone")
    if timezone:
        server.timezone(
            name=f"Set the timezone to {timezone}",
            timezone=timezone,
        )

    public_key_file = host.data.get("ssh_public_key_file")
    if public_key_file:
        key_path = Path(public_key_file).expanduser()
        if not key_path.exists():
            raise RuntimeError(
                f"SSH public key not found: {key_path}\n"
                "Generate one with `ssh-keygen -t ed25519`, or set "
                "`ssh_public_key_file = None` in deploy/group_data/production.py "
                "to keep using password authentication.",
            )

        # Appends to authorized_keys - `delete_keys` stays False so any key the
        # provider, or another project's deploy (e.g. valida's), put there
        # survives.
        server.user_authorized_keys(
            name="Install the local SSH public key for root",
            user=host.data.get("ssh_user", "root"),
            public_keys=[key_path.read_text().strip()],
            delete_keys=False,
        )

    node_major = host.data.get("node_major_version", 20)
    installed = host.get_fact(DebPackages)
    if "nodejs" not in installed:
        # NodeSource's setup script adds their apt repo + signing key and
        # calls `apt update` itself, so this is a one-shot bootstrap - once
        # nodejs is installed, later deploys skip straight past it.
        server.shell(
            name=f"Add the NodeSource apt repo for Node.js {node_major}.x",
            commands=[
                f"curl -fsSL https://deb.nodesource.com/setup_{node_major}.x | bash -",
            ],
        )
        apt.packages(
            name="Install Node.js",
            packages=["nodejs"],
            update=True,
        )

    if not host.get_fact(File, path="/usr/local/bin/bun"):
        server.shell(
            name="Install Bun",
            commands=["curl -fsSL https://bun.sh/install | bash"],
        )
        server.shell(
            name="Put bun/bunx on the system PATH",
            commands=[
                "ln -sf /root/.bun/bin/bun /usr/local/bin/bun",
                "ln -sf /root/.bun/bin/bunx /usr/local/bin/bunx",
            ],
        )

    if not host.get_fact(File, path="/usr/local/bin/uv"):
        server.shell(
            name="Install uv",
            commands=["curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh"],
        )

    if not host.get_fact(File, path="/usr/local/bin/pm2"):
        server.shell(
            name="Install pm2",
            commands=["/usr/local/bin/bun install -g pm2"],
        )
        server.shell(
            name="Put pm2 on the system PATH",
            commands=["ln -sf /root/.bun/bin/pm2 /usr/local/bin/pm2"],
        )


@deploy("Firewall")
def firewall():
    """ufw with only SSH, HTTP and HTTPS reachable. Opt-in via group data -
    see the warning in group_data/production.py about this being a shared box."""

    if not host.data.get("configure_firewall"):
        return

    apt.packages(
        name="Install ufw",
        packages=["ufw"],
    )

    ssh_port = host.data.get("ssh_port", 22)

    # ufw's own commands are idempotent (it skips rules that already exist), so
    # these run every deploy and simply report "Skipping adding existing rule".
    server.shell(
        name="Allow SSH, HTTP and HTTPS",
        commands=[
            f"ufw allow {ssh_port}/tcp",
            "ufw allow 80/tcp",
            "ufw allow 443/tcp",
        ],
    )

    server.shell(
        name="Enable ufw",
        commands=["ufw --force enable"],
    )
