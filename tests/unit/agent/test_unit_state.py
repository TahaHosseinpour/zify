"""Unit tests for the state reducer in state.py."""

from app.state import accumulate_retrieved


class TestAccumulateRetrieved:
    def test_none_resets_to_empty_list(self):
        assert accumulate_retrieved(["stale", "data"], None) == []

    def test_none_resets_even_from_empty(self):
        assert accumulate_retrieved([], None) == []

    def test_a_list_appends_to_existing(self):
        assert accumulate_retrieved(["a"], ["b", "c"]) == ["a", "b", "c"]

    def test_parallel_branches_accumulate_in_call_order(self):
        # Simulates what LangGraph does across the fan-out: each branch's
        # return value is folded in via this reducer, one at a time.
        state = accumulate_retrieved([], None)  # start of turn
        state = accumulate_retrieved(state, ["from_sql_chain"])
        state = accumulate_retrieved(state, ["from_faq"])
        state = accumulate_retrieved(state, ["from_shop_info"])
        assert state == ["from_sql_chain", "from_faq", "from_shop_info"]

    def test_existing_none_is_treated_as_empty(self):
        assert accumulate_retrieved(None, ["a"]) == ["a"]
