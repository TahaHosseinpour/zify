"""A jury of LLM judges for grading free-text agent replies against a rubric.

Used wherever a node's or the graph's output is prose, not a fixed field, so
no plain assertion can check it (see /tests/agent-eval/README.md for the
deterministic-vs-judge split). Each configured model in judge/config.py casts
one vote; the jury passes a reply only if enough of them agree it does.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from . import config

JUDGE_SYSTEM_PROMPT = (
    "You are a strict, impartial judge for a Persian-language sales chatbot. "
    "You will be given the conversation so far, one reply from the agent, a "
    "rubric, and a description of what an ideal reply looks like. Decide "
    "whether the reply satisfies every criterion in the rubric, using the "
    "ideal-reply description as your standard of comparison - the actual "
    "reply doesn't need to match it word for word, but it must accomplish "
    "the same thing. Be skeptical of hallucinated products, prices, links or "
    "claims not grounded in the conversation - inventing any of these is "
    "always a fail, even if the rubric doesn't say so explicitly. Judge only "
    "the given criteria, not writing style you personally would have "
    "preferred."
)


class Verdict(BaseModel):
    passed: bool
    reasoning: str


@dataclass
class JudgeVote:
    model: str
    # None = this judge errored (bad model name, quota, network) and is
    # excluded from the jury's vote rather than counted as a fail.
    passed: Optional[bool]
    reasoning: str


@dataclass
class JuryVerdict:
    votes: list[JudgeVote] = field(default_factory=list)

    @property
    def counted_votes(self) -> list[JudgeVote]:
        return [v for v in self.votes if v.passed is not None]

    @property
    def all_errored(self) -> bool:
        return len(self.votes) > 0 and not self.counted_votes

    @property
    def passed(self) -> bool:
        counted = self.counted_votes
        if not counted:
            return False
        pass_rate = sum(1 for v in counted if v.passed) / len(counted)
        return pass_rate >= config.JURY_PASS_THRESHOLD

    def explain(self) -> str:
        def label(v: JudgeVote) -> str:
            return "ERROR" if v.passed is None else ("PASS" if v.passed else "FAIL")

        return "\n".join(f"[{label(v)}] {v.model}: {v.reasoning}" for v in self.votes)


def _judge_prompt(rubric: str, ideal: str, transcript: str, reply: str) -> str:
    return (
        f"### Conversation so far\n{transcript or '(nothing yet)'}\n\n"
        f"### Reply being judged\n{reply}\n\n"
        f"### What an ideal reply looks like here\n{ideal}\n\n"
        f"### Rubric - the reply must satisfy ALL of these to pass\n{rubric}\n"
    )


async def _ask_one_judge(model: str, rubric: str, ideal: str, transcript: str, reply: str) -> JudgeVote:
    try:
        judge_llm = ChatOpenAI(
            model=model,
            temperature=config.JUDGE_TEMPERATURE,
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        ).with_structured_output(Verdict)
        verdict: Verdict = await judge_llm.ainvoke(
            [
                SystemMessage(content=JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=_judge_prompt(rubric, ideal, transcript, reply)),
            ]
        )
        return JudgeVote(model=model, passed=verdict.passed, reasoning=verdict.reasoning)
    except Exception as exc:  # noqa: BLE001
        return JudgeVote(model=model, passed=None, reasoning=f"judge errored: {type(exc).__name__}: {exc}")


async def deliberate(rubric: str, ideal: str, transcript: str, reply: str) -> JuryVerdict:
    """Put one reply to the whole configured jury and collect their votes."""
    votes = await asyncio.gather(
        *[_ask_one_judge(model, rubric, ideal, transcript, reply) for model in config.JUDGE_MODELS]
    )
    return JuryVerdict(votes=list(votes))
