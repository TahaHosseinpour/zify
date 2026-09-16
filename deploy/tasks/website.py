"""Ship the app and bring it up to date on the server.

The build genuinely has to happen *somewhere* - Next.js needs compiling,
Prisma needs both its JS and Python clients generated, and the agent needs a
real Python venv. Building on the server (rather than shipping a pre-built
artifact from a Windows dev machine) keeps this simple and avoids
cross-platform build/binary mismatches, at the cost of the server needing
Node/Bun/uv (installed in `tasks/system.py`) and every deploy taking as long
as `bun install && uv sync && next build` does.

Same atomic-release shape as valida's deploy: each deploy unpacks into its own
`releases/<id>/` directory (id = hash of the packaged source, so an unchanged
push uploads nothing and skips the rebuild entirely) and only swaps the
`current` symlink once that release has fully built - `tasks/service.py`
starts pm2 against the release directory directly (not through the symlink),
so a half-built release is never served. Making room for that build (pruning
what `current` no longer needs, and bailing out early when the disk is too
tight anyway) is `prepare_release()`, which the deploy runs before anything
else. A `.build-complete` marker (written only after every step below
succeeds) is what "fully built" means, so a deploy that died partway through
retries from scratch next time instead of being mistaken for done.
"""

import hashlib
import subprocess
import tarfile
from pathlib import Path

from paths import ARTIFACTS_DIR, PROJECT_DIR, TEMPLATES_DIR
from pyinfra import host
from pyinfra.api import deploy
from pyinfra.facts.files import Directory, File
from pyinfra.operations import files, server


def _tracked_files() -> list[Path]:
    """Everything `git` tracks in the project - naturally excludes
    node_modules, .venv, .next, deploy/.artifacts, .env, etc via .gitignore."""

    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_DIR,
        check=True,
        capture_output=True,
    )
    names = result.stdout.decode("utf-8").split("\0")
    return [PROJECT_DIR / n for n in names if n]


def _build_archive() -> tuple[Path, str]:
    """Pack the tracked source tree into a tarball; return its path and the
    release id (a hash of the packaged content, so identical pushes are a
    no-op)."""

    sources = sorted(_tracked_files())
    if not sources:
        raise RuntimeError("`git ls-files` returned nothing - run this from a git checkout.")

    digest = hashlib.sha256()
    for path in sources:
        digest.update(path.relative_to(PROJECT_DIR).as_posix().encode())
        digest.update(path.read_bytes())
    release_id = digest.hexdigest()[:12]

    archive = ARTIFACTS_DIR / f"zify-{release_id}.tar.gz"
    if archive.exists():
        return archive, release_id

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    partial = archive.with_suffix(".partial")

    with tarfile.open(partial, "w:gz") as tar:
        for path in sources:
            info = tar.gettarinfo(str(path), arcname=path.relative_to(PROJECT_DIR).as_posix())
            # Normalise everything Windows-specific or time-dependent, so the
            # same tree always produces the same bytes.
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            info.mode = 0o644
            with path.open("rb") as handle:
                tar.addfile(info, handle)

    partial.replace(archive)
    return archive, release_id


_RELEASE: tuple[Path, str] | None = None


def _release() -> tuple[Path, str]:
    """`_build_archive()` memoised - several tasks need the release id, and
    hashing the whole tree twice is pure waste."""

    global _RELEASE
    if _RELEASE is None:
        _RELEASE = _build_archive()
    return _RELEASE


def release_dir_path() -> str:
    """The concrete (non-symlinked) path of the release being deployed right
    now. `tasks/service.py` starts pm2 against this directly rather than
    through `current`, so there is no ambiguity about which release's `cwd`
    pm2 resolves - see its own comment."""

    _, release_id = _release()
    return f"{host.data.get('web_root')}/releases/{release_id}"


@deploy("Prepare release")
def prepare_release():
    """Free the space the build needs, then refuse to continue if there still
    isn't enough. Runs first, before anything else in the deploy - see the
    header of templates/prepare-release.sh.j2 for why the pruning has to
    happen before the build, not after it."""

    _, release_id = _release()

    files.template(
        name="Upload the release preflight script",
        src=str(TEMPLATES_DIR / "prepare-release.sh.j2"),
        dest="/tmp/zify-prepare-release.sh",
        mode="700",
        web_root=host.data.get("web_root"),
        release_id=release_id,
        keep_releases=host.data.get("keep_releases", 2),
        min_free_mb=host.data.get("min_free_disk_mb", 4000),
    )

    server.shell(
        name="Prune old releases and check free disk",
        commands=["/tmp/zify-prepare-release.sh"],
    )


@deploy("Website")
def website():
    archive, release_id = _release()

    web_root = host.data.get("web_root")
    owner = host.data.get("site_user")

    releases_dir = f"{web_root}/releases"
    release_dir = release_dir_path()
    remote_archive = f"/tmp/zify-{release_id}.tar.gz"
    marker = f"{release_dir}/.build-complete"

    files.directory(
        name="Ensure the releases directory",
        path=releases_dir,
        mode="755",
    )

    already_built = bool(host.get_fact(File, path=marker))

    if not already_built:
        if not host.get_fact(Directory, path=release_dir):
            files.put(
                name=f"Upload release {release_id}",
                src=str(archive),
                dest=remote_archive,
                mode="600",
            )

            files.directory(
                name=f"Ensure the release directory for {release_id}",
                path=release_dir,
                mode="755",
            )

            server.shell(
                name=f"Unpack release {release_id}",
                commands=[
                    f"tar -xzf {remote_archive} -C {release_dir}",
                    f"chown -R {owner}:{owner} {release_dir}",
                    f"rm -f {remote_archive}",
                ],
            )

        # All three apps read a single shared root .env at both build time
        # (Prisma, Next's build-time NEXT_PUBLIC_* inlining) and runtime -
        # see apps/admin/next.config.ts, apps/agent/main.py and
        # apps/telegram-bot/package.json's `start` script, which all resolve
        # it relative to their own location back up to this file. Prisma CLI
        # additionally looks for .env next to its own schema, hence the
        # second link.
        files.link(
            name=f"Link the shared .env into release {release_id}",
            path=f"{release_dir}/.env",
            target=f"{web_root}/shared/.env",
            symbolic=True,
        )
        files.link(
            name=f"Link the shared .env into release {release_id}'s packages/db",
            path=f"{release_dir}/packages/db/.env",
            target=f"{web_root}/shared/.env",
            symbolic=True,
        )

        build_swapfile = f"{web_root}/.build-swap"
        build_swap_mb = host.data.get("build_swap_mb", 2048)

        server.shell(
            name=f"Install, generate, migrate, build and seed release {release_id}",
            commands=[
                # This server carries no permanent swap on purpose (see
                # group_data's `build_swap_mb` comment) - `bun install` +
                # `uv sync` + `next build` back to back is the one point in
                # this deploy that actually needs the headroom, so a swapfile
                # is made just for this shell and `trap ... EXIT` removes it
                # again whether the build succeeds or dies partway through.
                # If a previous run crashed before its own trap fired, the
                # `swapon --show` check below just reuses what's already there
                # instead of erroring on a second `mkswap`.
                f'SWAPFILE="{build_swapfile}" && '
                "trap 'swapoff \"$SWAPFILE\" 2>/dev/null || true; rm -f \"$SWAPFILE\"' EXIT && "
                'if ! swapon --show=NAME --noheadings 2>/dev/null | grep -qx "$SWAPFILE"; then '
                f'fallocate -l {build_swap_mb}M "$SWAPFILE" 2>/dev/null || '
                f'dd if=/dev/zero of="$SWAPFILE" bs=1M count={build_swap_mb} status=none; '
                'chmod 600 "$SWAPFILE" && mkswap "$SWAPFILE" >/dev/null && swapon "$SWAPFILE"; '
                "fi && "
                # apps/agent/.venv/bin is put on PATH *before* it exists (uv
                # sync creates it two steps down) so `bunx prisma generate`
                # can find the `prisma-client-py` generator script it
                # installs there - see packages/db/prisma/schema.prisma's
                # python_client generator block.
                'export PATH="$(pwd)/apps/agent/.venv/bin:/usr/local/bin:$PATH" && '
                "bun install --frozen-lockfile && "
                "(cd apps/agent && uv sync --frozen) && "
                "(cd packages/db && bunx prisma generate) && "
                "(cd packages/db && bunx prisma migrate deploy) && "
                "(cd apps/admin && bun run build) && "
                "(cd packages/db && bunx prisma db seed) && "
                "touch .build-complete",
            ],
            _chdir=release_dir,
        )

    # The atomic part: swapping this symlink is what nginx's static-asset
    # alias (tasks/nginx.py) reads through. pm2 (tasks/service.py) is started
    # against release_dir directly, not through this symlink.
    files.link(
        name=f"Point current at release {release_id}",
        path=f"{web_root}/current",
        target=release_dir,
        symbolic=True,
    )
