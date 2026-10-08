"""What a turn actually cost, recorded against its conversation.

A subscription is priced on the guarantee that no conversation costs more than
a fixed ceiling in model spend (packages/shared/src/plans.ts). The per-turn
limits elsewhere in this package keep a conversation under that ceiling by
construction; this module is what makes the guarantee checkable instead of
assumed. After every turn the real token counts of every model call — both LLM
calls, Jev, embeddings — are priced and added to `conversations."costToman"`,
which the gate (packages/db/src/billing.ts) reads before admitting the next
message. A conversation that somehow runs hot is closed by its own bill.

The same numbers go to `usage_records`, one row per turn: the audit trail.
"""

from __future__ import annotations

import os
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from .db import db

# USD per token. List prices of the models this deployment is configured for;
# override when the model (or the provider's markup) changes.
LLM_INPUT_USD = float(os.environ.get("PRICE_LLM_INPUT_PER_M", "0.15")) / 1_000_000
LLM_OUTPUT_USD = float(os.environ.get("PRICE_LLM_OUTPUT_PER_M", "0.60")) / 1_000_000
JEV_INPUT_USD = float(os.environ.get("PRICE_JEV_INPUT_PER_M", "0.042")) / 1_000_000
EMBEDDING_USD = float(os.environ.get("PRICE_EMBEDDING_PER_M", "0.02")) / 1_000_000

# The second providers (graph.py's failover chains). A turn they answered is
# priced at their rates, not the first provider's.
DEEPSEEK_INPUT_USD = float(os.environ.get("PRICE_DEEPSEEK_INPUT_PER_M", "0.15")) / 1_000_000
DEEPSEEK_OUTPUT_USD = float(os.environ.get("PRICE_DEEPSEEK_OUTPUT_PER_M", "0.60")) / 1_000_000
# DeepSeek charges double during its peak hours: 01:00-04:00 and 06:00-10:00
# UTC, Monday to Friday.
DEEPSEEK_PEAK_MULTIPLIER = float(os.environ.get("PRICE_DEEPSEEK_PEAK_MULTIPLIER", "2"))
_DEEPSEEK_PEAK_HOURS_UTC = ((1, 4), (6, 10))
FALLBACK_EMBEDDING_USD = float(os.environ.get("PRICE_GEMINI_EMBEDDING_PER_M", "0.15")) / 1_000_000

# Used until the `settings` table has been read, and whenever it can't be.
DEFAULT_USD_TOMAN = float(os.environ.get("USD_TOMAN", "300000"))
_RATE_TTL_SECONDS = 300

# Persian text runs about three characters to a token on these models. Only
# used for embeddings, whose API reports no usage through LangChain and whose
# cost is a rounding error either way.
_CHARS_PER_TOKEN = 3


@dataclass
class TurnMeter:
    """Token counts of the calls LangChain's callbacks never see."""

    jev_tokens: int = 0
    embedding_tokens: int = 0
    # The part of embedding_tokens the second provider embedded.
    fallback_embedding_tokens: int = 0


_meter: ContextVar[Optional[TurnMeter]] = ContextVar("turn_meter", default=None)


def start_turn() -> TurnMeter:
    """Begin metering the current request. Graph nodes run as tasks spawned
    from this context, so they all report into the same meter."""
    meter = TurnMeter()
    _meter.set(meter)
    return meter


def add_jev_tokens(tokens: int) -> None:
    meter = _meter.get()
    if meter is not None:
        meter.jev_tokens += max(0, int(tokens))


def add_embedding_text(text: str, fallback: bool = False) -> None:
    meter = _meter.get()
    if meter is not None:
        tokens = len(text) // _CHARS_PER_TOKEN + 1
        meter.embedding_tokens += tokens
        if fallback:
            meter.fallback_embedding_tokens += tokens


_rate: Optional[float] = None
_rate_read_at = 0.0


async def usd_toman() -> float:
    """The dollar rate every cost is converted with — a platform setting, so it
    can follow the market without a deploy."""
    global _rate, _rate_read_at
    now = time.monotonic()
    if _rate is not None and now - _rate_read_at < _RATE_TTL_SECONDS:
        return _rate
    try:
        rows = await db.query_raw("SELECT value FROM settings WHERE key = 'usd_toman'")
        _rate = float(rows[0]["value"]) if rows else DEFAULT_USD_TOMAN
    except Exception as err:  # noqa: BLE001 — never fail a turn over a setting
        print(f"[agent] metering: could not read usd_toman ({err}); using {DEFAULT_USD_TOMAN:,.0f}")
        _rate = DEFAULT_USD_TOMAN
    _rate_read_at = now
    return _rate


def _deepseek_peak(when: datetime) -> bool:
    when = when.astimezone(timezone.utc)
    return when.weekday() < 5 and any(start <= when.hour < end for start, end in _DEEPSEEK_PEAK_HOURS_UTC)


def llm_cost_usd(
    model: Optional[str], input_tokens: int, output_tokens: int, when: Optional[datetime] = None
) -> float:
    """What one LLM call cost, at the rates of the model that answered it."""
    if model and model.lower().startswith("deepseek"):
        rate = DEEPSEEK_PEAK_MULTIPLIER if _deepseek_peak(when or datetime.now(timezone.utc)) else 1.0
        return (input_tokens * DEEPSEEK_INPUT_USD + output_tokens * DEEPSEEK_OUTPUT_USD) * rate
    return input_tokens * LLM_INPUT_USD + output_tokens * LLM_OUTPUT_USD


def turn_cost_usd(
    input_tokens: int, output_tokens: int, meter: TurnMeter, llm_usd: Optional[float] = None
) -> float:
    """`llm_usd` is the LLM calls already priced one by one (each by its own
    model); without it the token totals are priced at the first provider's
    rates."""
    if llm_usd is None:
        llm_usd = llm_cost_usd(None, input_tokens, output_tokens)
    return (
        llm_usd
        + meter.jev_tokens * JEV_INPUT_USD
        + (meter.embedding_tokens - meter.fallback_embedding_tokens) * EMBEDDING_USD
        + meter.fallback_embedding_tokens * FALLBACK_EMBEDDING_USD
    )


def conversation_id_from_thread(thread_id: str) -> Optional[str]:
    """Thread ids are "<shopId>:<endUserId>:<conversationId>" (see
    packages/db/src/conversations.ts)."""
    parts = thread_id.split(":")
    return parts[2] if len(parts) >= 3 and parts[2] else None


async def record_turn(
    shop_id: str,
    thread_id: str,
    input_tokens: int,
    output_tokens: int,
    meter: TurnMeter,
    llm_usd: Optional[float] = None,
) -> Decimal:
    """Price the turn and persist it. Returns its cost in toman.

    Never raises: the customer already has their reply, and a failed write here
    must not turn it into an error. It is logged loudly instead, because an
    unrecorded turn is unbilled spend.
    """
    cost = Decimal(
        str(turn_cost_usd(input_tokens, output_tokens, meter, llm_usd) * await usd_toman())
    ).quantize(Decimal("0.01"))
    conversation_id = conversation_id_from_thread(thread_id)
    try:
        if conversation_id:
            await db.execute_raw(
                'UPDATE conversations SET "costToman" = "costToman" + $1::numeric WHERE id = $2',
                str(cost),
                conversation_id,
            )
        await db.execute_raw(
            """INSERT INTO usage_records
                 (id, "shopId", "conversationId", "inputTokens", "outputTokens",
                  "jevTokens", "embeddingTokens", "costToman")
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8::numeric)""",
            uuid.uuid4().hex,
            shop_id,
            conversation_id,
            input_tokens,
            output_tokens,
            meter.jev_tokens,
            meter.embedding_tokens,
            str(cost),
        )
    except Exception as err:  # noqa: BLE001
        print(f"[agent] metering: FAILED to record a turn costing {cost} toman for shop {shop_id}: {err}")
    return cost
