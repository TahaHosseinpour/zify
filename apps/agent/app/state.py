from typing import Annotated, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class RetrievedItem(TypedDict, total=False):
    id: str
    type: str  # "product" | "faq" | "shop_info"
    content: str
    score: float
    metadata: dict


class SetContext:
    """Reducer signal: replace the accumulated retrieved_context wholesale."""

    def __init__(self, items: list["RetrievedItem"]) -> None:
        self.items = items


# Sentinel used by nodes to wipe retrieved_context at the start of a turn.
RESET_CONTEXT = None


def merge_retrieved(existing: list, new) -> list:
    """Reducer for retrieved_context.

    - `None`  → reset to an empty list (start of a new turn).
    - SetContext(items) → replace the whole list (after fuse/rank).
    - a list → append (parallel fan-out branches accumulate).

    This stops retrieved items from piling up across conversation turns and
    being frozen into the checkpoint forever.
    """
    if new is None:
        return []
    if isinstance(new, SetContext):
        return list(new.items)
    return (existing or []) + list(new)


class SalesAgentState(TypedDict, total=False):
    # Conversation infrastructure
    messages: Annotated[list[BaseMessage], add_messages]
    shop_id: str
    mode: str  # "explore" | "product"
    product_id: Optional[str]

    # Long-term conversation memory: when `messages` grows too long, older
    # turns are collapsed into this running summary.
    summary: Optional[str]

    # Retrieval — reset every turn, never persisted across turns
    retrieved_context: Annotated[
        list[RetrievedItem], merge_retrieved
    ]
    # The products most recently shown to the customer, so later ordinal
    # references ("the second one") can resolve to a concrete product.
    # No reducer = plain replace; it survives across turns until re-set.
    shown_products: list[RetrievedItem]
    explore_filters: dict
    intent: Optional[str]

    # Buyer profiling
    stage: Optional[str]  # "browsing" | "considering" | "ready_to_buy"
    value_driver: Optional[str]  # "low_price" | "high_quality" |
    # "best_price_in_quality" | "best_quality_in_price"

    # Sales behavior
    objection: Optional[str]  # "price" | "uncertainty" | "delay"
