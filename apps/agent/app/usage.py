"""Input-token usage quotas, per EndUser (per customer, not per shop - one
customer chatting a lot only costs that customer their own budget, not the
whole shop's). Enforced here, in server.py's `/chat`, before any LLM call
runs, and updated again after a turn completes with what it actually spent.

Mirrored for display in packages/db/src/usage.ts (admin panel + the Telegram
bot's usage button) - that side is read-only, this side is where the numbers
actually change, so keep both in sync if the limits or window lengths change.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from .db import db

WEEKLY_INPUT_TOKEN_LIMIT = 80_000
MONTHLY_INPUT_TOKEN_LIMIT = 200_000

_WEEK = timedelta(days=7)
_MONTH = timedelta(days=30)


class UsageStatus(NamedTuple):
    weekly_used: int
    weekly_reset_at: datetime
    monthly_used: int
    monthly_reset_at: datetime

    @property
    def over_limit(self) -> bool:
        return (
            self.weekly_used >= WEEKLY_INPUT_TOKEN_LIMIT
            or self.monthly_used >= MONTHLY_INPUT_TOKEN_LIMIT
        )


def _lazy_reset(now: datetime, reset_at: datetime, window: timedelta, used: int) -> tuple[int, datetime]:
    if now >= reset_at:
        return 0, now + window
    return used, reset_at


async def usage_status(end_user_id: str) -> UsageStatus:
    """Current usage, rolling forward any window that already expired -
    read-only, so an expired window reads as reset without writing anything.
    `increment_input_tokens` is what actually persists a roll-forward."""
    end_user = await db.enduser.find_unique(where={"id": end_user_id})
    if end_user is None:
        raise ValueError(f"usage_status: no EndUser with id {end_user_id}")

    now = datetime.now(timezone.utc)
    weekly_used, weekly_reset_at = _lazy_reset(now, end_user.weeklyResetAt, _WEEK, end_user.weeklyInputTokens)
    monthly_used, monthly_reset_at = _lazy_reset(
        now, end_user.monthlyResetAt, _MONTH, end_user.monthlyInputTokens
    )
    return UsageStatus(weekly_used, weekly_reset_at, monthly_used, monthly_reset_at)


class TokenUsageCallback(BaseCallbackHandler):
    """Sums `input_tokens` off every LLM call's `usage_metadata` for one turn.

    A fresh instance is created per `/chat` request (see server.py) and
    attached the same way tracing.py's Langfuse handler is - through the
    top-level graph invocation's `callbacks`, which LangChain propagates down
    to every nested `llm.ainvoke`/`structured_llm.ainvoke` call (intent
    classification, generation, the summarizer when it runs) without any
    per-node plumbing.
    """

    def __init__(self) -> None:
        self.input_tokens = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for generations in response.generations:
            for gen in generations:
                message = getattr(gen, "message", None)
                usage = getattr(message, "usage_metadata", None) if message else None
                if usage:
                    self.input_tokens += usage.get("input_tokens", 0) or 0


async def increment_input_tokens(end_user_id: str, tokens: int) -> None:
    """Add `tokens` to both counters, rolling forward any expired window
    first. Called once per turn, after the turn completes, with however many
    input tokens it actually spent (intent classification + generation +
    summarizer, when the summarizer ran)."""
    if tokens <= 0:
        return

    status = await usage_status(end_user_id)
    await db.enduser.update(
        where={"id": end_user_id},
        data={
            "weeklyInputTokens": status.weekly_used + tokens,
            "weeklyResetAt": status.weekly_reset_at,
            "monthlyInputTokens": status.monthly_used + tokens,
            "monthlyResetAt": status.monthly_reset_at,
        },
    )
