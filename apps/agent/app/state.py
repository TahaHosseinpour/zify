from typing import Annotated, Optional, TypedDict, Union

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


class SalesAgentState(TypedDict):
    # زیرساخت مکالمه
    messages: Annotated[list[BaseMessage], add_messages]
    shop_id: str
    mode: str  # "explore" | "product"
    product_id: Optional[str]

    # retrieval — reset every turn, never persisted across turns
    retrieved_context: Annotated[
        list[RetrievedItem], merge_retrieved
    ]
    explore_filters: dict
    intent: Optional[str]

    # تشخیص خریدار
    stage: Optional[str]  # "browsing" | "considering" | "ready_to_buy"
    value_driver: Optional[str]  # "low_price" | "high_quality" |
    # "best_price_in_quality" | "best_quality_in_price"

    # رفتار فروش
    objection: Optional[str]  # "price" | "uncertainty" | "delay"
