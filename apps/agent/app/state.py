from typing import Annotated, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class RetrievedItem(TypedDict, total=False):
    id: str
    type: str  # "product" | "faq" | "shop_info"
    content: str
    score: float
    metadata: dict


# Sentinel a node returns to wipe retrieved_raw at the start of a turn.
RESET_CONTEXT = None


def accumulate_retrieved(existing: list, new) -> list:
    """Reducer for retrieved_raw.

    - `None` → reset to an empty list (start of a new turn).
    - a list → append (parallel fan-out branches accumulate).

    Only plain lists / None ever flow through here, so it stays msgpack-
    serializable for the Postgres checkpointer.
    """
    if new is None:
        return []
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

    # Raw retrieval accumulated across the retrieval steps of a turn; reset at
    # the start of each turn via the None sentinel.
    retrieved_raw: Annotated[list[RetrievedItem], accumulate_retrieved]
    # Output of the SQL filter step: the product ids that satisfy the
    # customer's hard constraints, which the vector step then ranks within.
    # Per-turn scratch — whichever node ranks the turn's context
    # (vector_search_explore / vector_search_product) clears it once it has been
    # read, so it isn't checkpointed.
    candidate_ids: list[str]
    # How to read candidate_ids: "none" (no constraints), "ids" (scope to
    # them), "inline" (too many to list — re-apply filters in SQL), or
    # "relaxed" (nothing matched; searching unscoped so we can offer the
    # closest alternatives). See graph.FILTER_* .
    filter_status: Optional[str]
    # The predicates that actually survived progressive relaxation — the
    # classifier's guessed category/brand may have been dropped to keep the
    # customer's price range enforceable.
    filter_effective: dict
    # The predicates relaxation actually threw away this turn. `filter_status`
    # alone cannot express this: dropping `category` but keeping a price still
    # reports FILTER_IDS, which is indistinguishable from a clean match. The
    # prompt needs the difference to stay honest about what it searched for.
    filters_dropped: list[str]
    # The customer asked for something this shop does not carry — either the
    # classifier found no matching category in the shop's vocabulary, or every
    # retrieved product was too far from the query to be a real answer.
    out_of_catalog: Optional[bool]
    # Whether the client should render buy buttons for this turn. False on the
    # closing turns that are explicitly told not to push (a customer who said
    # "let me think" was still shown five purchase buttons). Per-turn: reset by
    # analyze_intent and set by handle_purchase.
    buy_actions: Optional[bool]
    # Explicit ordering the customer asked for ("cheapest", "most expensive").
    # Vector similarity cannot express a superlative, so these are resolved by
    # SQL ORDER BY instead. "price_asc" | "price_desc".
    sort: Optional[str]
    # Final ranked context the generation nodes consume. No reducer = plain
    # replace; the ranking node of each path (vector_search_explore /
    # vector_search_product) overwrites it wholesale.
    retrieved_context: list[RetrievedItem]
    # The products most recently shown to the customer, so later ordinal
    # references ("the second one") can resolve to a concrete product.
    # No reducer = plain replace; it survives across turns until re-set.
    shown_products: list[RetrievedItem]
    # Products the customer rejected; excluded from subsequent searches until a
    # new topic clears the list.
    excluded_product_ids: list[str]
    explore_filters: dict
    intent: Optional[str]

    # Buyer profiling
    stage: Optional[str]  # "browsing" | "considering" | "ready_to_buy"
    value_driver: Optional[str]  # "low_price" | "high_quality" |
    # "best_price_in_quality" | "best_quality_in_price"

    # Sales behavior
    objection: Optional[str]  # "price" | "uncertainty" | "delay"
