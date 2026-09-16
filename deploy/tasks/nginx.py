"""nginx: reverse-proxy the admin app (the only one of the three that's a web
server - the agent is internal-only, the bot has no HTTP surface at all),
serve its built static assets directly, and optionally put HTTPS in front."""

from paths import TEMPLATES_DIR
from pyinfra import host
from pyinfra.api import deploy
from pyinfra.facts.files import Directory
from pyinfra.operations import apt, files, server, systemd


@deploy("Nginx")
def nginx():
    apt.packages(
        name="Install nginx",
        packages=["nginx"],
    )

    domain = host.data.get("site_domain")
    # Whether a cert already exists - `https()` below is what obtains one, but
    # it runs *after* this task, so this checks the state left by a previous
    # deploy. First deploy after DNS points here: renders HTTP-only, `https()`
    # gets the cert; next deploy: this sees it and renders the HTTPS block
    # itself, which is what keeps it from being wiped every time this
    # `files.template` call re-renders the file (see the template's header).
    https_ready = bool(domain) and bool(
        host.get_fact(Directory, path=f"/etc/letsencrypt/live/{domain}")
    )

    # This is a *named* vhost on a shared box that also runs valida (and
    # possibly other sites) - it deliberately does not claim `default_server`,
    # so without `site_domain` set it answers on no name at all yet (some
    # other vhost owns the bare-IP/default response). Once DNS points a
    # domain here, this starts answering for that name specifically.
    site_config = files.template(
        name="Write the Zify site config",
        src=str(TEMPLATES_DIR / "zify.conf.j2"),
        dest="/etc/nginx/sites-available/zify.conf",
        mode="644",
        # nginx's `server_name` takes space-separated names - the previous
        # ad-hoc nginx config (/etc/nginx/sites-available/zifyai.ir, replaced
        # by this one) answered on both the apex and `www.`, and the existing
        # certificate covers both, so this keeps that.
        server_name=f"{domain} www.{domain}" if domain else "zify.invalid",
        cert_domain=domain,
        web_root=host.data.get("web_root"),
        app_port=host.data.get("app_port"),
        https_ready=https_ready,
    )

    site_enabled = files.link(
        name="Enable the Zify site",
        path="/etc/nginx/sites-enabled/zify.conf",
        target="/etc/nginx/sites-available/zify.conf",
    )

    systemd.service(
        name="Ensure nginx runs at boot",
        service="nginx",
        running=True,
        enabled=True,
    )

    if site_config.will_change or site_enabled.will_change:
        # Fail the deploy on a broken config instead of on the reload, which
        # would leave nginx serving the old config with no clear error.
        server.shell(
            name="Validate the nginx config",
            commands=["nginx -t"],
        )
        systemd.service(
            name="Reload nginx",
            service="nginx",
            reloaded=True,
        )


@deploy("HTTPS")
def https():
    """Let's Encrypt certificate - runs only once both data keys are set."""

    domain = host.data.get("site_domain")
    email = host.data.get("letsencrypt_email")
    if not domain or not email:
        return

    apt.packages(
        name="Install certbot",
        packages=["certbot", "python3-certbot-nginx"],
    )

    # certbot renews itself from a systemd timer, so this is only about the
    # first issuance.
    if not host.get_fact(Directory, path=f"/etc/letsencrypt/live/{domain}"):
        server.shell(
            name=f"Obtain a certificate for {domain}",
            commands=[
                "certbot --nginx --non-interactive --agree-tos --redirect "
                f"--email {email} --domain {domain} --domain www.{domain}",
            ],
        )
