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


def main() -> None:
    fields = {
        "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
        "avalai_api_key": os.environ.get("AVALAI_API_KEY", ""),
        "langsmith_api_key": os.environ.get("LANGSMITH_API_KEY", ""),
        "langfuse_public_key": os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
        "langfuse_secret_key": os.environ.get("LANGFUSE_SECRET_KEY", ""),
        "smsir_api_key": os.environ.get("SMSIR_API_KEY", ""),
        "smsir_template_id": os.environ.get("SMSIR_TEMPLATE_ID", ""),
        "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    }

    lines = [f"{name} = {value!r}" for name, value in fields.items()]

    dest = Path(__file__).resolve().parent / "deploy_secrets.py"
    dest.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
