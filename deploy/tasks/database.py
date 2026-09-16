"""PostgreSQL: installed directly with apt (no Docker on the VPS - see
deploy/README.md), plus pgvector (the `vector` extension Prisma's migrations
need - packages/db/prisma/migrations/0001_init_pgvector) and the one-time
secret generation + role/database setup in templates/setup-env.sh.j2."""

from paths import TEMPLATES_DIR
from pyinfra import host
from pyinfra.api import deploy
from pyinfra.facts.files import Directory
from pyinfra.operations import apt, files, server, systemd


def _public_app_url() -> str:
    """Best guess at the site's public URL for NEXT_PUBLIC_APP_URL. Mirrors
    tasks/nginx.py's own https_ready check - on the very first deploy after
    DNS points here, this still says http:// until the *next* deploy sees the
    certificate, same lag as nginx's own template (see its header comment)."""

    domain = host.data.get("site_domain")
    if not domain:
        return f"http://{host.name}"

    https_ready = bool(host.get_fact(Directory, path=f"/etc/letsencrypt/live/{domain}"))
    return f"{'https' if https_ready else 'http'}://{domain}"


@deploy("Database")
def database():
    apt.packages(
        name="Install PostgreSQL",
        packages=["postgresql", "postgresql-contrib"],
        update=True,
        cache_time=3600,
    )

    systemd.service(
        name="Ensure PostgreSQL runs at boot",
        service="postgresql",
        running=True,
        enabled=True,
    )

    # ...and the step above is not enough on its own: `postgresql.service` is
    # a meta-unit that reads as "active" even when its clusters are down, so
    # this asks pg_isready and starts the real postgresql@<version>-<cluster>
    # units when it has to. See templates/ensure-postgres.sh.j2.
    files.template(
        name="Upload the PostgreSQL readiness script",
        src=str(TEMPLATES_DIR / "ensure-postgres.sh.j2"),
        dest="/tmp/zify-ensure-postgres.sh",
        mode="700",
        web_root=host.data.get("web_root"),
        startup_timeout=host.data.get("postgres_startup_timeout", 30),
    )

    server.shell(
        name="Ensure PostgreSQL is accepting connections",
        commands=["/tmp/zify-ensure-postgres.sh"],
    )

    # pgvector: packaged (postgresql-<N>-pgvector) on recent Debian/Ubuntu,
    # built from source as a fallback where it isn't - e.g. this server's
    # Ubuntu ships PostgreSQL 14, which has no such package at all. See the
    # script's own header for why building from source is safe here.
    files.template(
        name="Upload the pgvector install script",
        src=str(TEMPLATES_DIR / "ensure-pgvector.sh.j2"),
        dest="/tmp/zify-ensure-pgvector.sh",
        mode="700",
    )

    server.shell(
        name="Install pgvector for the installed PostgreSQL version",
        commands=["/tmp/zify-ensure-pgvector.sh"],
    )

    script = files.template(
        name="Upload the env/database setup script",
        src=str(TEMPLATES_DIR / "setup-env.sh.j2"),
        dest="/tmp/zify-setup-env.sh",
        mode="700",
        web_root=host.data.get("web_root"),
        site_user=host.data.get("site_user"),
        db_name=host.data.get("db_name"),
        db_user=host.data.get("db_user"),
        app_port=host.data.get("app_port"),
        agent_port=host.data.get("agent_port"),
        public_app_url=_public_app_url(),
        openai_api_key=host.data.get("openai_api_key"),
        openai_base_url=host.data.get("openai_base_url"),
        openai_chat_model=host.data.get("openai_chat_model"),
        openai_embedding_model=host.data.get("openai_embedding_model"),
        langsmith_tracing=host.data.get("langsmith_tracing"),
        langsmith_endpoint=host.data.get("langsmith_endpoint"),
        langsmith_api_key=host.data.get("langsmith_api_key"),
        langsmith_project=host.data.get("langsmith_project"),
        langfuse_host=host.data.get("langfuse_host"),
        langfuse_public_key=host.data.get("langfuse_public_key"),
        langfuse_secret_key=host.data.get("langfuse_secret_key"),
        sms_mock=host.data.get("sms_mock"),
        smsir_api_key=host.data.get("smsir_api_key"),
        smsir_template_id=host.data.get("smsir_template_id"),
        telegram_bot_token=host.data.get("telegram_bot_token"),
        bot_username=host.data.get("bot_username"),
        admin_mobile=host.data.get("admin_mobile"),
        admin_password=host.data.get("admin_password"),
    )

    # Runs every deploy on purpose - the script itself is idempotent (see its
    # header): secrets are generated once and kept, role/database/extension
    # creation is guarded by existence checks.
    server.shell(
        name="Ensure the app database, role and extension exist",
        commands=["/tmp/zify-setup-env.sh"],
    )
