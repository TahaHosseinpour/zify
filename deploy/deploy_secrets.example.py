"""Template for deploy/deploy_secrets.py - copy this file to
deploy_secrets.py and fill in the real values. deploy_secrets.py is
gitignored (see deploy/.gitignore) so these never end up in git history;
group_data/production.py imports from it.

Named `deploy_secrets`, not `secrets`, so it can't shadow Python's stdlib
`secrets` module if deploy/ ever ends up on sys.path.
"""

# OpenAI (or an OpenAI-compatible gateway) - used by the agent for chat and
# embeddings. Required: without it, the agent starts but every LLM call fails.
openai_api_key = ""

# LangSmith tracing (https://smith.langchain.com) - optional, leave blank to
# run without tracing.
langsmith_api_key = ""

# Langfuse tracing (https://cloud.langfuse.com, or self-hosted - see
# langfuse_host in group_data/production.py) - optional, both must be set
# together or tracing stays off (apps/agent/app/tracing.py).
langfuse_public_key = ""
langfuse_secret_key = ""

# sms.ir OTP delivery for admin login - https://sms.ir/panel (کاربری > وب سرویس).
# Leave blank to keep SMS_MOCK on (OTP codes are printed/returned instead of texted).
smsir_api_key = ""
smsir_template_id = ""

# Telegram bot token from @BotFather.
telegram_bot_token = ""
