"""Run the three apps with pm2, using the ecosystem.config.cjs already
committed at the repo root (apps admin/3010, agent/AGENT_PORT, bot - see that
file's own header comment for the port map).

Must run *after* `website()` - it always reloads, on the assumption that
`release_dir_path()` already points at a freshly built release by the time
this runs. `pm2 startOrReload` is invoked with the concrete release
directory as `cwd` (not through the `current` symlink) so there is no
ambiguity about which release's relative paths (`./apps/admin`,
`.venv/bin/python`, ...) pm2 resolves against - Node resolves `process.cwd()`
physically, so going through a symlink here would be one extra layer of
"does this resolve before or after the reload" to reason about for no
benefit."""

from pyinfra.api import deploy
from pyinfra.operations import server
from tasks.website import release_dir_path


@deploy("App service (pm2)")
def app_service():
    # Registers the systemd unit that relaunches pm2 (and everything it was
    # running) on boot. Safe to run every deploy - it just rewrites the same
    # unit file. `pm2 save` below is what actually persists a process list
    # for that unit to restore.
    server.shell(
        name="Register pm2 with systemd",
        commands=["pm2 startup systemd -u root --hp /root >/dev/null 2>&1 || true"],
    )

    server.shell(
        name="Start/reload the Zify pm2 apps",
        commands=["pm2 startOrReload ecosystem.config.cjs --update-env"],
        _chdir=release_dir_path(),
    )

    server.shell(
        name="Persist the pm2 process list for the next reboot",
        commands=["pm2 save"],
    )
