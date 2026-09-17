"""Writes deploy/deploy_secrets.py from environment variables, for the deploy
job in .github/workflows/ci-deploy.yml.

deploy_secrets.py is gitignored on purpose (see deploy_secrets.example.py)
and group_data/production.py refuses to import without it, so CI has to
materialize it from repo secrets before `npm run deploy` can run. Run
locally, this only ever produces a file full of empty strings - it's meant
for CI, not as a replacement for deploy_secrets.example.py.
"""

import os
from pathlib import Path


def parse_admin_users(raw: str) -> list[tuple[str, str]]:
    """"09120000000:pw1,09120000001:pw2" -> [("09120000000", "pw1"), ...],
    matching deploy_secrets.example.py's admin_users shape."""

    pairs = []
    for item in filter(None, (p.strip() for p in raw.split(","))):
        mobile, _, password = item.partition(":")
        pairs.append((mobile.strip(), password.strip()))
    return pairs


def main() -> None:
    admin_users = parse_admin_users(os.environ.get("ADMIN_USERS", ""))

    fields = {
        "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
        "langsmith_api_key": os.environ.get("LANGSMITH_API_KEY", ""),
        "langfuse_public_key": os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
        "langfuse_secret_key": os.environ.get("LANGFUSE_SECRET_KEY", ""),
        "smsir_api_key": os.environ.get("SMSIR_API_KEY", ""),
        "smsir_template_id": os.environ.get("SMSIR_TEMPLATE_ID", ""),
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    }

    lines = [f"{name} = {value!r}" for name, value in fields.items()]
    lines.append(f"admin_users = {admin_users!r}")

    dest = Path(__file__).resolve().parent / "deploy_secrets.py"
    dest.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
