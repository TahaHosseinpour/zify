"""Unit tests for maybe_summarize — the token-capping conversation compaction
that runs on every single turn but only does work past SUMMARY_TRIGGER."""

from langchain_core.messages import AIMessage, HumanMessage

from app import graph as G


def messages(n):
    return [
        HumanMessage(content=f"پیام {i}", id=f"m{i}") if i % 2 == 0
        else AIMessage(content=f"پاسخ {i}", id=f"m{i}")
        for i in range(n)
    ]


class TestMaybeSummarize:
    async def test_below_trigger_does_nothing_and_calls_no_llm(self, monkeypatch):
        calls = []

        async def fake_ainvoke(msgs):
            calls.append(msgs)
            return AIMessage(content="خلاصه")

        monkeypatch.setattr(G, "llm", type("L", (), {"ainvoke": staticmethod(fake_ainvoke)})())

        state = {"messages": messages(G.SUMMARY_TRIGGER)}
        result = await G.maybe_summarize(state)
        assert result == {}
        assert calls == []

    async def test_above_trigger_summarizes_and_removes_old_messages(self, monkeypatch):
        async def fake_ainvoke(msgs):
            return AIMessage(content="خلاصه فشرده")

        monkeypatch.setattr(G, "llm", type("L", (), {"ainvoke": staticmethod(fake_ainvoke)})())

        total = G.SUMMARY_TRIGGER + 5
        state = {"messages": messages(total)}
        result = await G.maybe_summarize(state)

        assert result["summary"] == "خلاصه فشرده"
        # Everything except the last KEEP_RECENT gets a RemoveMessage.
        assert len(result["messages"]) == total - G.KEEP_RECENT
        removed_ids = {m.id for m in result["messages"]}
        kept_ids = {m.id for m in state["messages"][-G.KEEP_RECENT:]}
        assert not (removed_ids & kept_ids)

    async def test_previous_summary_is_folded_into_the_next_one(self, monkeypatch):
        seen_prompts = []

        async def fake_ainvoke(msgs):
            seen_prompts.append(msgs[0].content)
            return AIMessage(content="خلاصه جدید")

        monkeypatch.setattr(G, "llm", type("L", (), {"ainvoke": staticmethod(fake_ainvoke)})())

        state = {"messages": messages(G.SUMMARY_TRIGGER + 5), "summary": "خلاصه قبلی مهم"}
        await G.maybe_summarize(state)
        assert "خلاصه قبلی مهم" in seen_prompts[0]

    async def test_old_turns_are_sent_as_quoted_text_not_live_messages(self, monkeypatch):
        """Regression guard: passing the old turns as real HumanMessage/
        AIMessage objects made the model continue the dialogue (and invent
        products) instead of summarizing it. They must arrive as one HumanMessage
        containing a transcript."""
        seen = []

        async def fake_ainvoke(msgs):
            seen.extend(msgs)
            return AIMessage(content="خلاصه")

        monkeypatch.setattr(G, "llm", type("L", (), {"ainvoke": staticmethod(fake_ainvoke)})())

        state = {"messages": messages(G.SUMMARY_TRIGGER + 5)}
        await G.maybe_summarize(state)
        assert len(seen) == 1
        assert isinstance(seen[0], HumanMessage)
        assert "پیام 0" in seen[0].content  # the transcript is embedded as text

    async def test_boundary_at_exactly_the_trigger_does_nothing(self, monkeypatch):
        async def fake_ainvoke(msgs):
            raise AssertionError("should not be called at exactly the trigger")

        monkeypatch.setattr(G, "llm", type("L", (), {"ainvoke": staticmethod(fake_ainvoke)})())
        state = {"messages": messages(G.SUMMARY_TRIGGER)}
        result = await G.maybe_summarize(state)
        assert result == {}
