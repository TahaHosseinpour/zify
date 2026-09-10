"""Langfuse tracing for the sales agent.

Tracing is opt-in: without LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY the agent
behaves exactly as before and makes no network calls. When it is configured,
each /chat request becomes one Langfuse trace and every LLM call inside the
graph becomes a nested generation carrying its token usage. Langfuse derives
the cost server-side from the model name plus those token counts, so both
"tokens" and "cost" show up per trace without us computing anything here.

Callbacks are attached once, at the top-level graph invocation. LangChain
propagates them down to the per-node `llm.ainvoke` calls through the async
context, so individual nodes need no changes.
"""

from __future__ import annotations

import os
from typing import Any, Optional

_handler: Optional[Any] = None
_resolved = False


def _configured() -> bool:
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def get_handler() -> Optional[Any]:
    """Return the shared CallbackHandler, or None when tracing is off.

    Resolved once per process; the handler is safe to reuse across requests
    because per-trace data travels in the run config, not on the handler.
    """
    global _handler, _resolved
    if _resolved:
        return _handler
    _resolved = True

    if not _configured():
        print("[agent] langfuse: off (LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY not set)")
        return None

    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler
    except ImportError as err:  # noqa: BLE001 — optional dependency
        print(f"[agent] langfuse: off (import failed: {err})")
        return None

    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
    # Report an unreachable/misconfigured Langfuse loudly, but still attach the
    # handler: the SDK buffers in the background, so a blip at startup should
    # not disable tracing for the lifetime of the process.
    try:
        if get_client().auth_check():
            print(f"[agent] langfuse: tracing to {host}")
        else:
            print(f"[agent] langfuse: auth check failed for {host} — traces may be dropped")
    except Exception as err:  # noqa: BLE001 — never block startup on tracing
        print(f"[agent] langfuse: auth check errored for {host}: {err}")

    _handler = CallbackHandler()
    return _handler


def chat_config(
    thread_id: str,
    shop_id: str,
    mode: str,
    product_id: Optional[str] = None,
) -> dict:
    """Build the run config for a /chat graph invocation.

    Always carries the checkpointer's thread_id; adds Langfuse callbacks and
    trace attributes when tracing is enabled.
    """
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    handler = get_handler()
    if handler is None:
        return config

    # Thread ids look like "<shopId>:<endUserId>" (see server.reset_memory), so
    # the whole thread is the Langfuse session and the end user is its user_id.
    end_user_id = thread_id.split(":", 1)[1] if ":" in thread_id else thread_id

    tags = [f"mode:{mode}", f"shop:{shop_id}"]
    if product_id:
        tags.append("product-scoped")

    config["callbacks"] = [handler]
    config["run_name"] = "chat"
    config["metadata"] = {
        "langfuse_session_id": thread_id,
        "langfuse_user_id": end_user_id,
        "langfuse_tags": tags,
        "shop_id": shop_id,
        "mode": mode,
        "product_id": product_id,
    }
    return config


def flush() -> None:
    """Push buffered events before shutdown so no trace is lost."""
    if _handler is None:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception as err:  # noqa: BLE001 — shutdown must not fail on tracing
        print(f"[agent] langfuse: flush failed: {err}")
