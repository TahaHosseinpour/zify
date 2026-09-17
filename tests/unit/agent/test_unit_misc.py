"""Small pure-function tests that didn't earn their own file: message-text
extraction, prompt assembly, and the defensive type-coercion branches in the
price helpers."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app import graph as G
from app.server import _to_float


class TestLastMessageText:
    def test_empty_messages_returns_empty_string(self):
        assert G.last_message_text({"messages": []}) == ""

    def test_extracts_content_from_a_langchain_message(self):
        state = {"messages": [HumanMessage(content="سلام")]}
        assert G.last_message_text(state) == "سلام"

    def test_extracts_content_from_a_plain_dict_message(self):
        # LangGraph can hand nodes plain dicts instead of BaseMessage objects
        # depending on the serialization path.
        state = {"messages": [{"content": "سلام از دیکشنری"}]}
        assert G.last_message_text(state) == "سلام از دیکشنری"

    def test_non_string_content_returns_empty_string_rather_than_crashing(self):
        state = {"messages": [HumanMessage(content=[{"type": "text", "text": "x"}])]}
        assert G.last_message_text(state) == ""

    def test_only_the_last_message_is_used(self):
        state = {"messages": [HumanMessage(content="اول"), AIMessage(content="دوم")]}
        assert G.last_message_text(state) == "دوم"


class TestBuildLlmMessages:
    def test_system_prompt_always_leads(self):
        msgs = G.build_llm_messages("system", [])
        assert isinstance(msgs[0], SystemMessage)
        assert msgs[0].content == "system"

    def test_summary_becomes_a_second_system_message_when_present(self):
        msgs = G.build_llm_messages("system", [], summary="خلاصه قبلی")
        assert len(msgs) == 2
        assert isinstance(msgs[1], SystemMessage)
        assert "خلاصه قبلی" in msgs[1].content

    def test_no_summary_means_no_extra_system_message(self):
        msgs = G.build_llm_messages("system", [])
        assert len(msgs) == 1

    def test_conversation_comes_after_summary_and_before_context(self):
        conv = [HumanMessage(content="پیام مشتری")]
        msgs = G.build_llm_messages("system", conv, "context", summary="خلاصه")
        contents = [m.content for m in msgs]
        assert contents == ["system", "خلاصه گفتگوی قبلی:\nخلاصه", "پیام مشتری", "context"]

    def test_blank_context_prompt_is_not_appended(self):
        msgs = G.build_llm_messages("system", [], context_prompt="   ")
        assert len(msgs) == 1

    def test_dynamic_context_is_always_last(self):
        """Ordering matters for OpenAI prefix caching: the per-turn content
        must be last so it can never invalidate the cached system+summary
        prefix."""
        msgs = G.build_llm_messages(
            "system", [HumanMessage(content="x")], "دینامیک", summary="خلاصه"
        )
        assert msgs[-1].content == "دینامیک"


class TestMalformedPriceIsIgnoredNotFatal:
    def test_relative_price_bound_ignores_a_non_numeric_price(self):
        shown = [{"id": "a", "type": "product", "metadata": {"price": "قیمت نامعتبر"}}]
        assert G._relative_price_bound("cheaper", shown) is None

    def test_relative_price_bound_skips_bad_prices_and_uses_the_rest(self):
        shown = [
            {"id": "a", "type": "product", "metadata": {"price": "بد"}},
            {"id": "b", "type": "product", "metadata": {"price": 5000}},
        ]
        key, value = G._relative_price_bound("cheaper", shown)
        assert (key, value) == ("maxPrice", 5000 - G.PRICE_EPSILON)


class TestToFloat:
    def test_none_stays_none(self):
        assert _to_float(None) is None

    def test_numeric_string_converts(self):
        assert _to_float("1000") == 1000.0

    def test_non_numeric_value_becomes_none_not_an_exception(self):
        assert _to_float("قیمت نامعتبر") is None

    def test_actual_float_passes_through(self):
        assert _to_float(1234.5) == 1234.5
