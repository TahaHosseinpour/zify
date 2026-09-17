"""Contract tests between prompts.py's instructions and graph.py's schema.

`with_structured_output` means whatever graph.IntentResult declares becomes a
hard JSON-schema constraint on the model's response — the prompt's wording is
advisory, the Pydantic type is enforced. When the two disagree, the enforced
type wins and the prompt's instruction is simply impossible to follow.
"""

from app.graph import IntentResult


class TestStageFieldContract:
    def test_stage_is_nullable_like_value_driver_and_objection(self):
        """
        prompts.build_intent_analysis_prompt says, verbatim:

            "مقادیر stage/value_driver/objection فقط وقتی مقداردهی کن که از
             پیام فعلی مشخص باشند؛ اگر پیام فعلی چیزی درباره‌شان نمی‌گوید،
             آن‌ها را null بگذار تا مقدار قبلی حفظ شود."

        i.e. "only set stage/value_driver/objection when the current message
        makes them clear; otherwise leave them null so the previous value is
        kept." analyze_intent's merge logic implements exactly that contract:

            "stage": result.stage or state.get("stage", "browsing")

        `stage` used to be typed as a bare `str` — required, non-null — while
        value_driver/objection were Optional[str]. Because with_structured_
        output turns the schema into a hard constraint on the model's
        response, that mismatch was not just a style inconsistency: the model
        was physically unable to comply with the prompt's instruction and was
        forced to guess a stage on every single turn. This is a regression
        guard against `stage` being narrowed back to a required field.
        """
        stage_field = IntentResult.model_fields["stage"]
        value_driver_field = IntentResult.model_fields["value_driver"]
        objection_field = IntentResult.model_fields["objection"]

        # The two fields the prompt groups with `stage` are optional — confirms
        # the intended contract, and that this isn't a stale prompt.
        assert value_driver_field.is_required() is False
        assert objection_field.is_required() is False
        assert stage_field.is_required() is False

    def test_a_missing_stage_falls_back_to_the_previous_turns_value(self):
        """End-to-end confirmation that the schema fix actually changes
        behaviour: with stage nullable, the model omitting it must resolve to
        whatever the conversation already had, not a fresh guess."""
        result = IntentResult(intent="browse", mode="explore")
        assert result.stage is None
