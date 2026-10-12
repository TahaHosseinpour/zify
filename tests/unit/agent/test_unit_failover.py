"""Unit tests for provider failover: the circuit breaker, the chat chain, the
embedding chain and the per-provider pricing.

Nothing here touches the network. Providers are fakes that answer, fail or
stream on command.
"""

import asyncio
from datetime import datetime, timezone
from typing import Annotated, Any, AsyncIterator, TypedDict

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app import breaker as B
from app import graph as G
from app import intent as jev
from app import metering
from app.breaker import CircuitBreaker
from app.failover import ChatLink, FailoverChat, ProvidersUnavailable, Vector
from app.usage import TokenUsageCallback
from tests.conftest import item


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class TestCircuitBreaker:
    def make(self):
        clock = Clock()
        return CircuitBreaker("t", failure_threshold=3, reset_seconds=30, clock=clock), clock

    def test_stays_closed_below_the_threshold(self):
        b, _ = self.make()
        b.record_failure()
        b.record_failure()
        assert b.state == B.CLOSED
        assert b.allow()

    def test_opens_after_consecutive_failures_and_refuses_calls(self):
        b, _ = self.make()
        for _ in range(3):
            b.record_failure()
        assert b.state == B.OPEN
        assert not b.allow()

    def test_a_success_resets_the_failure_count(self):
        b, _ = self.make()
        b.record_failure()
        b.record_failure()
        b.record_success()
        b.record_failure()
        b.record_failure()
        assert b.state == B.CLOSED

    def test_half_open_lets_exactly_one_trial_through(self):
        b, clock = self.make()
        for _ in range(3):
            b.record_failure()
        clock.now = 30
        assert b.state == B.HALF_OPEN
        assert b.allow()
        assert not b.allow()

    def test_a_successful_trial_closes_it(self):
        b, clock = self.make()
        for _ in range(3):
            b.record_failure()
        clock.now = 30
        assert b.allow()
        b.record_success()
        assert b.state == B.CLOSED
        assert b.allow()

    def test_a_failed_trial_reopens_it_for_a_full_wait(self):
        b, clock = self.make()
        for _ in range(3):
            b.record_failure()
        clock.now = 30
        assert b.allow()
        b.record_failure()
        assert b.state == B.OPEN
        clock.now = 59
        assert not b.allow()
        clock.now = 60
        assert b.allow()

    def test_a_cancelled_trial_frees_the_slot(self):
        b, clock = self.make()
        for _ in range(3):
            b.record_failure()
        clock.now = 30
        assert b.allow()
        b.release()
        assert b.allow()

    def test_available_does_not_claim_the_trial(self):
        b, clock = self.make()
        for _ in range(3):
            b.record_failure()
        assert not b.available()
        clock.now = 30
        assert b.available()
        assert b.available()
        assert b.allow()

    def test_a_bad_request_is_not_the_providers_fault(self):
        class Err(Exception):
            def __init__(self, status):
                self.status_code = status

        assert not B.is_provider_fault(Err(400))
        assert not B.is_provider_fault(Err(404))
        assert B.is_provider_fault(Err(429))
        assert B.is_provider_fault(Err(401))
        assert B.is_provider_fault(Err(504))
        assert B.is_provider_fault(TimeoutError())


class FakeModel:
    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.calls = 0
        self.max_tokens = 300

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return AIMessage(content=self.reply)


class TestFailoverChat:
    async def test_the_first_provider_answers_when_it_is_healthy(self):
        first, second = FakeModel("اول"), FakeModel("دوم")
        chat = FailoverChat([ChatLink("a", first), ChatLink("b", second)])
        assert (await chat.ainvoke([])).content == "اول"
        assert second.calls == 0

    async def test_the_second_provider_answers_when_the_first_fails(self):
        first, second = FakeModel(error=TimeoutError("no bytes")), FakeModel("دوم")
        chat = FailoverChat([ChatLink("a", first), ChatLink("b", second)])
        assert (await chat.ainvoke([])).content == "دوم"

    async def test_a_provider_that_keeps_failing_is_skipped_without_being_called(self):
        first, second = FakeModel(error=TimeoutError()), FakeModel("دوم")
        chat = FailoverChat([ChatLink("a", first), ChatLink("b", second)])
        for _ in range(B.FAILURE_THRESHOLD):
            await chat.ainvoke([])
        assert first.calls == B.FAILURE_THRESHOLD
        await chat.ainvoke([])
        await chat.ainvoke([])
        assert first.calls == B.FAILURE_THRESHOLD
        assert second.calls == B.FAILURE_THRESHOLD + 2

    async def test_the_last_error_surfaces_when_every_provider_fails(self):
        chat = FailoverChat(
            [ChatLink("a", FakeModel(error=TimeoutError("a"))), ChatLink("b", FakeModel(error=RuntimeError("b")))]
        )
        with pytest.raises(RuntimeError, match="b"):
            await chat.ainvoke([])

    async def test_all_breakers_open_fails_fast(self):
        first = FakeModel(error=TimeoutError())
        chat = FailoverChat([ChatLink("a", first)])
        for _ in range(B.FAILURE_THRESHOLD):
            with pytest.raises(TimeoutError):
                await chat.ainvoke([])
        with pytest.raises(ProvidersUnavailable):
            await chat.ainvoke([])
        assert first.calls == B.FAILURE_THRESHOLD

    async def test_a_bad_request_fails_over_but_does_not_count_against_the_provider(self):
        class BadRequest(Exception):
            status_code = 400

        first, second = FakeModel(error=BadRequest()), FakeModel("دوم")
        chat = FailoverChat([ChatLink("a", first), ChatLink("b", second)])
        for _ in range(B.FAILURE_THRESHOLD + 2):
            await chat.ainvoke([])
        assert first.calls == B.FAILURE_THRESHOLD + 2

    def test_it_reports_the_reply_ceiling_of_the_real_model(self):
        assert FailoverChat([ChatLink("a", FakeModel("x"))]).max_tokens == 300

    def test_structured_output_uses_each_providers_own_method(self):
        seen = []

        class Model:
            def __init__(self, name):
                self.name = name

            def with_structured_output(self, schema, **kwargs):
                seen.append((self.name, kwargs))
                return self

        FailoverChat(
            [ChatLink("a", Model("a")), ChatLink("b", Model("b"), structured_method="function_calling")]
        ).with_structured_output(dict)
        assert seen == [("a", {}), ("b", {"method": "function_calling"})]

    def test_the_graphs_models_are_chains(self):
        assert isinstance(G.llm, FailoverChat)
        assert isinstance(G.structured_llm, FailoverChat)


class StreamingFake(BaseChatModel):
    """A chat model that streams `tokens`, then fails if `fail_after` says so."""

    tokens: list[str]
    fail_after: int = -1  # raise once this many tokens have gone out; -1 = never

    @property
    def _llm_type(self) -> str:
        return "streaming-fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        raise NotImplementedError

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        if self.fail_after >= 0:
            raise TimeoutError("provider down")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="".join(self.tokens)))])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        for sent, token in enumerate(self.tokens):
            if sent == self.fail_after:
                raise TimeoutError("stream dropped")
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=token))
            if run_manager:
                await run_manager.on_llm_new_token(token, chunk=chunk)
            yield chunk
        if self.fail_after == len(self.tokens):
            raise TimeoutError("stream dropped")


class _State(TypedDict):
    messages: Annotated[list, add_messages]


def _graph_around(chat: FailoverChat):
    async def reply(state: _State) -> dict:
        return {"messages": [await chat.ainvoke(state["messages"])]}

    return StateGraph(_State).add_node("reply", reply).add_edge(START, "reply").add_edge("reply", END).compile()


async def _streamed_text(graph, callbacks=None) -> str:
    text = ""
    async for chunk, _meta in graph.astream(
        {"messages": [HumanMessage(content="سلام")]}, {"callbacks": callbacks or []}, stream_mode="messages"
    ):
        text += chunk.content
    return text


class TestFailoverWhileStreaming:
    """The nodes call `llm.ainvoke(...)` and LangGraph streams the tokens out
    through callbacks inherited from the graph run. The chain adds a callback
    of its own, which must not displace those."""

    async def test_tokens_still_stream_through_the_chain(self):
        chat = FailoverChat([ChatLink("a", StreamingFake(tokens=["سلام", " ", "دوست"]))])
        assert await _streamed_text(_graph_around(chat)) == "سلام دوست"

    async def test_callbacks_of_the_graph_run_still_see_the_call(self):
        class Seen(BaseCallbackHandler):
            ended = 0

            def on_llm_end(self, response, **kwargs):
                Seen.ended += 1

        chat = FailoverChat([ChatLink("a", StreamingFake(tokens=["x"]))])
        await _streamed_text(_graph_around(chat), callbacks=[Seen()])
        assert Seen.ended == 1

    async def test_a_failure_before_the_first_token_moves_to_the_next_provider(self):
        chat = FailoverChat(
            [
                ChatLink("a", StreamingFake(tokens=["اول"], fail_after=0)),
                ChatLink("b", StreamingFake(tokens=["دوم"])),
            ]
        )
        assert await _streamed_text(_graph_around(chat)) == "دوم"

    async def test_a_failure_after_text_went_out_does_not_restart_the_reply(self):
        second = StreamingFake(tokens=["دوم"])
        chat = FailoverChat(
            [ChatLink("a", StreamingFake(tokens=["اول", " نیمه"], fail_after=1)), ChatLink("b", second)]
        )
        with pytest.raises(TimeoutError):
            await _streamed_text(_graph_around(chat))
        assert B.breaker("b-chat").state == B.CLOSED
        # Counted against the first provider all the same.
        assert B.breaker("a-chat")._failures == 1


class FakeEmbedder:
    def __init__(self, vec=None, error=None):
        self.vec = vec
        self.error = error
        self.calls = 0

    async def aembed_query(self, text):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.vec)


@pytest.fixture
def embedders(monkeypatch):
    def install(primary, fallback):
        monkeypatch.setattr(G, "embeddings", primary)
        monkeypatch.setattr(G, "fallback_embeddings", fallback)

    for cache in (G._embed_cache, G._fallback_embed_cache, G._embed_inflight):
        cache.clear()
    yield install
    for cache in (G._embed_cache, G._fallback_embed_cache, G._embed_inflight):
        cache.clear()


class TestEmbeddingFailover:
    async def test_the_primary_vector_reads_the_primary_column(self, embedders):
        embedders(FakeEmbedder([1.0]), FakeEmbedder([2.0]))
        vec = await G.embed("کفش")
        assert vec.space is G.PRIMARY_SPACE
        assert G._space_of(vec).column == "embedding"

    async def test_the_fallback_vector_reads_its_own_column(self, embedders):
        embedders(FakeEmbedder(error=TimeoutError()), FakeEmbedder([2.0]))
        vec = await G.embed("کفش")
        assert vec.space is G.GEMINI_SPACE
        assert vec[0] == 2.0
        assert len(vec) == G.EMBEDDING_DIM

    async def test_the_two_spaces_never_share_a_cache_entry(self, embedders):
        primary = FakeEmbedder(error=TimeoutError())
        embedders(primary, FakeEmbedder([2.0]))
        assert (await G.embed("کفش")).space is G.GEMINI_SPACE
        primary.error, primary.vec = None, [1.0]
        vec = await G.embed("کفش")
        assert vec.space is G.PRIMARY_SPACE
        assert vec[0] == 1.0

    async def test_a_dead_primary_is_skipped_once_its_breaker_opens(self, embedders):
        primary = FakeEmbedder(error=TimeoutError())
        embedders(primary, FakeEmbedder([2.0]))
        for n in range(B.FAILURE_THRESHOLD + 3):
            await G.embed(f"متن {n}")
        assert primary.calls == B.FAILURE_THRESHOLD
        assert G.active_space() is G.GEMINI_SPACE

    async def test_without_a_second_provider_the_error_surfaces(self, embedders):
        embedders(FakeEmbedder(error=TimeoutError()), None)
        with pytest.raises(TimeoutError):
            await G.embed("کفش")

    async def test_a_plain_list_is_treated_as_the_primary_space(self):
        assert G._space_of([0.1, 0.2]) is G.PRIMARY_SPACE

    async def test_fallback_embedding_is_metered_as_such(self, embedders):
        embedders(FakeEmbedder(error=TimeoutError()), FakeEmbedder([2.0]))
        meter = metering.start_turn()
        await G.embed("کفش ورزشی")
        assert meter.fallback_embedding_tokens > 0
        assert meter.fallback_embedding_tokens <= meter.embedding_tokens


class FakeRows:
    def __init__(self):
        self.sql = []

    async def query_raw(self, sql, *params):
        self.sql.append(sql)
        return []


class TestColumnAwareSql:
    @pytest.fixture
    def rows(self, monkeypatch):
        fake = FakeRows()
        monkeypatch.setattr(G, "db", fake)
        return fake

    async def test_every_search_reads_the_column_of_the_query_vector(self, rows):
        vec = Vector([0.0] * G.EMBEDDING_DIM, G.GEMINI_SPACE)
        await G.vector_search_products("s1", vec, 5)
        await G.vector_search_products("s1", vec, 5, candidate_ids=["p1"])
        await G.vector_search_faq("s1", vec)
        await G.vector_search_shop_info("s1", vec)
        assert len(rows.sql) == 4
        for sql in rows.sql:
            assert "embedding_gemini <=> $1::vector" in sql
            assert "embedding_gemini IS NOT NULL" in sql
            assert "embedding <=>" not in sql
            assert "embedding IS NOT NULL" not in sql

    async def test_a_plain_list_reads_the_primary_column(self, rows):
        await G.vector_search_products("s1", [0.0] * G.EMBEDDING_DIM, 5)
        assert "embedding <=> $1::vector" in rows.sql[0]
        assert "embedding IS NOT NULL" in rows.sql[0]

    def test_the_filter_step_counts_rows_of_the_space_in_use(self, monkeypatch):
        monkeypatch.setattr(G, "fallback_embeddings", FakeEmbedder([1.0]))
        where, _, _ = G._product_where("s1", None, None, 1)
        assert "embedding IS NOT NULL" in where
        for _ in range(B.FAILURE_THRESHOLD):
            G._embedding_breaker(G.PRIMARY_SPACE).record_failure()
        where, _, _ = G._product_where("s1", None, None, 1)
        assert "embedding_gemini IS NOT NULL" in where


def gemini_item(id_, score):
    return {**item(id_, score=score), "space": G.GEMINI_SPACE.name}


class TestThresholdsPerSpace:
    def test_the_gemini_floor_is_far_below_the_openai_one(self):
        # 0.45 is a strong match in the primary space and no match at all in
        # the second one.
        assert G._drop_irrelevant([item("a", score=0.45)], None) != []
        assert G._drop_irrelevant([gemini_item("a", 0.45)], None) == []
        assert G._drop_irrelevant([gemini_item("a", 0.30)], None) != []

    def test_the_gemini_gap_is_narrower(self):
        rows = [gemini_item("a", 0.25), gemini_item("b", 0.29), gemini_item("c", 0.33)]
        assert [r["id"] for r in G._within_gap(rows)] == ["a", "b"]
        plain = [item("a", score=0.25), item("b", score=0.29), item("c", score=0.33)]
        assert len(G._within_gap(plain)) == 3


class TestPricing:
    OFF_PEAK = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)  # a Thursday
    PEAK = datetime(2026, 10, 8, 7, 0, tzinfo=timezone.utc)
    WEEKEND = datetime(2026, 10, 10, 7, 0, tzinfo=timezone.utc)  # a Saturday

    def test_the_first_provider_keeps_its_price(self):
        assert metering.llm_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000) == pytest.approx(0.75)
        assert metering.llm_cost_usd(None, 1_000_000, 1_000_000) == pytest.approx(0.75)

    def test_deepseek_costs_double_in_its_peak_hours(self):
        assert metering.llm_cost_usd("deepseek-v4-flash", 1_000_000, 1_000_000, self.OFF_PEAK) == pytest.approx(0.75)
        assert metering.llm_cost_usd("deepseek-v4-flash", 1_000_000, 1_000_000, self.PEAK) == pytest.approx(1.5)
        assert metering.llm_cost_usd("deepseek-v4-flash", 1_000_000, 1_000_000, self.WEEKEND) == pytest.approx(0.75)

    def test_the_second_gateways_deepseek_has_its_own_flat_price(self, monkeypatch):
        monkeypatch.setattr(metering, "AVALAI_ON", True)
        monkeypatch.setattr(metering, "AVALAI_CHAT_MODEL", "deepseek-v4.1-flash")
        # $0.30 in and $1.20 out per million, at any hour.
        assert metering.llm_cost_usd("deepseek-v4.1-flash", 1_000_000, 1_000_000, self.OFF_PEAK) == pytest.approx(1.5)
        assert metering.llm_cost_usd("deepseek-v4.1-flash", 1_000_000, 1_000_000, self.PEAK) == pytest.approx(1.5)

    def test_without_the_second_gateway_that_model_is_priced_as_deepseek(self, monkeypatch):
        monkeypatch.setattr(metering, "AVALAI_ON", False)
        assert metering.llm_cost_usd("deepseek-v4.1-flash", 1_000_000, 1_000_000, self.OFF_PEAK) == pytest.approx(0.75)

    def test_an_account_out_of_credit_counts_against_the_provider(self):
        class OutOfCredit(Exception):
            status_code = 402

        assert B.is_provider_fault(OutOfCredit())

    def test_the_peak_windows_end_where_they_say(self):
        def at(hour):
            return metering._deepseek_peak(datetime(2026, 10, 8, hour, 0, tzinfo=timezone.utc))

        assert [h for h in range(24) if at(h)] == [1, 2, 3, 6, 7, 8, 9]

    def test_fallback_embedding_tokens_are_priced_at_the_fallback_rate(self):
        meter = metering.TurnMeter(embedding_tokens=1_000_000, fallback_embedding_tokens=1_000_000)
        assert metering.turn_cost_usd(0, 0, meter) == pytest.approx(0.15)

    def test_a_priced_llm_total_replaces_the_token_estimate(self):
        assert metering.turn_cost_usd(1_000_000, 1_000_000, metering.TurnMeter(), llm_usd=1.5) == pytest.approx(1.5)

    def test_the_usage_callback_prices_each_call_by_its_model(self, monkeypatch):
        from langchain_core.outputs import LLMResult

        monkeypatch.setattr(metering, "_deepseek_peak", lambda when: True)

        def result(model):
            message = AIMessage(
                content="x",
                usage_metadata={"input_tokens": 1_000_000, "output_tokens": 0, "total_tokens": 1_000_000},
                response_metadata={"model_name": model},
            )
            return LLMResult(generations=[[ChatGeneration(message=message)]])

        cb = TokenUsageCallback()
        cb.on_llm_end(result("gpt-4o-mini"))
        cb.on_llm_end(result("deepseek-flash"))
        assert cb.input_tokens == 2_000_000
        assert cb.llm_usd == pytest.approx(0.15 + 0.30)


class TestJevBreaker:
    async def test_jev_is_not_called_while_its_breaker_is_open(self, monkeypatch):
        def no_network():
            raise AssertionError("Jev must not be called")

        monkeypatch.setattr(jev, "_http", no_network)
        for _ in range(B.FAILURE_THRESHOLD):
            B.breaker("jev").record_failure()
        with pytest.raises(jev.JevUnavailable, match="circuit breaker"):
            await jev.ask({}, {})
