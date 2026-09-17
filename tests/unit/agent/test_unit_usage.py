"""Unit tests for usage.py's lazy window-reset logic - pure function, no DB
needed. usage_status/increment_input_tokens themselves are covered by
test_functional_server.py's TestUsageQuotaGate (mocked) and by
test_db_integration.py (real DB) for the actual read/write path."""

from datetime import datetime, timedelta, timezone

from app import usage as U


class TestLazyReset:
    def test_still_within_window_keeps_the_running_count(self):
        now = datetime.now(timezone.utc)
        reset_at = now + timedelta(days=1)
        used, new_reset_at = U._lazy_reset(now, reset_at, timedelta(days=7), 5_000)
        assert used == 5_000
        assert new_reset_at == reset_at

    def test_expired_window_resets_to_zero_and_rolls_forward(self):
        now = datetime.now(timezone.utc)
        reset_at = now - timedelta(seconds=1)  # already in the past
        window = timedelta(days=7)
        used, new_reset_at = U._lazy_reset(now, reset_at, window, 19_999)
        assert used == 0
        assert new_reset_at == now + window

    def test_exactly_at_the_boundary_counts_as_expired(self):
        now = datetime.now(timezone.utc)
        used, new_reset_at = U._lazy_reset(now, now, timedelta(days=30), 40_000)
        assert used == 0
        assert new_reset_at == now + timedelta(days=30)


class TestUsageStatusOverLimit:
    def test_under_both_limits_is_not_over_limit(self):
        now = datetime.now(timezone.utc)
        status = U.UsageStatus(
            weekly_used=U.WEEKLY_INPUT_TOKEN_LIMIT - 1, weekly_reset_at=now + timedelta(days=1),
            monthly_used=U.MONTHLY_INPUT_TOKEN_LIMIT - 1, monthly_reset_at=now + timedelta(days=10),
        )
        assert status.over_limit is False

    def test_weekly_at_the_cap_is_over_limit(self):
        now = datetime.now(timezone.utc)
        status = U.UsageStatus(
            weekly_used=U.WEEKLY_INPUT_TOKEN_LIMIT, weekly_reset_at=now + timedelta(days=1),
            monthly_used=0, monthly_reset_at=now + timedelta(days=10),
        )
        assert status.over_limit is True

    def test_monthly_at_the_cap_is_over_limit_even_if_weekly_is_fine(self):
        now = datetime.now(timezone.utc)
        status = U.UsageStatus(
            weekly_used=0, weekly_reset_at=now + timedelta(days=1),
            monthly_used=U.MONTHLY_INPUT_TOKEN_LIMIT, monthly_reset_at=now + timedelta(days=10),
        )
        assert status.over_limit is True


class TestTokenUsageCallback:
    def test_sums_input_tokens_across_multiple_llm_calls(self):
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, LLMResult

        cb = U.TokenUsageCallback()

        def result_with(input_tokens):
            message = AIMessage(content="x", usage_metadata={
                "input_tokens": input_tokens, "output_tokens": 1, "total_tokens": input_tokens + 1,
            })
            return LLMResult(generations=[[ChatGeneration(message=message)]])

        cb.on_llm_end(result_with(120))
        cb.on_llm_end(result_with(340))
        assert cb.input_tokens == 460

    def test_missing_usage_metadata_is_treated_as_zero(self):
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, LLMResult

        cb = U.TokenUsageCallback()
        message = AIMessage(content="x")  # no usage_metadata at all
        cb.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]))
        assert cb.input_tokens == 0
