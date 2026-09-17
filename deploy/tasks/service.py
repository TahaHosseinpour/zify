"""Run the three apps with pm2, using the ecosystem.config.cjs already
committed at the repo root (apps admin/3010, agent/AGENT_PORT, bot - see that
file's own header comment for the port map).

Must run *after* `website()` - it always (re)starts against
`release_dir_path()`, which already points at a freshly built release by the
time this runs, as `cwd` (not through the `current` symlink) so there is no
ambiguity about which release's relative paths (`./apps/admin`,
`.venv/bin/python`, ...) pm2 resolves against - Node resolves `process.cwd()`
physically, so going through a symlink here would be one extra layer of
"does this resolve before or after the reload" to reason about for no
benefit.

Deletes each named app before starting it fresh, rather than
`pm2 startOrReload`: pm2 matches "reload" targets by app *name* and doesn't
necessarily re-pin a stale entry's `cwd`/script path to the one just passed
in, so if a previous deploy ever left pm2 pointed at a release directory
that a *later* deploy's `prepare_release()` then pruned (e.g. because that
deploy's own app_service() step never got to run - a real incident: an SSH
setup failure mid-pipeline did exactly this), every subsequent reload kept
failing with `spawn ENOENT` against a release that no longer exists, with pm2
still reporting the app as "online". Deleting and starting fresh every time
means pm2's process table always matches the release actually being
deployed, never a stale one - the trade-off is a real (if brief, well under a
second) restart instead of a reload, but fork-mode apps were never getting a
true zero-downtime reload from `startOrReload` anyway."""

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
        name="Start the Zify pm2 apps against the current release",
        commands=[
            # `|| true` - delete on an app pm2 has never heard of (first ever
            # deploy) exits non-zero, and that's fine, not an error.
            "pm2 delete ecosystem.config.cjs >/dev/null 2>&1 || true",
            "pm2 start ecosystem.config.cjs --update-env",
        ],
        _chdir=release_dir_path(),
    )

    server.shell(
        name="Persist the pm2 process list for the next reboot",
        commands=["pm2 save"],
    )
