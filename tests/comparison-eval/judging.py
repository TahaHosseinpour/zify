"""The jury for free-text replies.

Two judge models, and a scenario passes only if *both* pass it - one "no" is a
"no". Each judge sees the customer's side of the conversation, the reply being
scored, whatever was attached to it (product cards, a buy button), the
scenario's acceptance criteria and an example of an ideal reply, and the shop's
whole catalog as ground truth.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

JUDGE_MODELS = ["gpt-4o-mini", "gpt-5-mini"]

JUDGE_SYSTEM_PROMPT = (
    "You are a strict, fair evaluator of a Persian-language sales assistant for an online shop. "
    "You are given the shop's complete catalog (the only source of truth), the conversation, the "
    "assistant's final reply with anything attached to it, an example of an ideal reply, and a "
    "rubric. Decide whether the final reply satisfies EVERY item of the rubric.\n"
    "- Judge only the final reply; earlier turns are context.\n"
    "- A product, price, feature, link or policy that is not in the catalog is invented.\n"
    "- The ideal reply is an illustration, not a template: a reply may differ in wording and "
    "still pass.\n"
    "- Do not add requirements the rubric does not state.\n"
    "Give your reasoning in Persian, in one or two sentences."
)


class Verdict(BaseModel):
    reasoning: str = Field(description="One or two sentences, in Persian.")
    passed: bool


@dataclass
class Vote:
    model: str
    passed: Optional[bool]  # None = the judge itself failed to answer
    reasoning: str


@dataclass
class JuryResult:
    votes: list[Vote]

    @property
    def errored(self) -> bool:
        return any(v.passed is None for v in self.votes)

    @property
    def passed(self) -> bool:
        return bool(self.votes) and all(v.passed is True for v in self.votes)


def _prompt(catalog: str, transcript: str, reply: str, attachments: str, rubric: str, ideal: str) -> str:
    return (
        f"### کاتالوگ کامل فروشگاه (مرجع حقیقت)\n{catalog}\n\n"
        f"### گفت‌وگو تا پیش از پاسخ نهایی\n{transcript or '(این اولین پیام است)'}\n\n"
        f"### پاسخ نهایی که باید داوری شود\n{reply}\n\n"
        f"### ضمیمه‌های همین پاسخ (آنچه مشتری زیر پیام می‌بیند)\n{attachments or '(هیچ)'}\n\n"
        f"### نمونه‌ی یک پاسخ ایده‌آل\n{ideal}\n\n"
        f"### معیار پذیرش - پاسخ باید همه‌ی این موارد را برآورده کند\n{rubric}\n"
    )


async def _ask(model: str, prompt: str) -> Vote:
    try:
        llm = ChatOpenAI(
            model=model,
            temperature=0,
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        ).with_structured_output(Verdict)
        verdict: Verdict = await llm.ainvoke(
            [SystemMessage(content=JUDGE_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        return Vote(model, verdict.passed, verdict.reasoning)
    except Exception as exc:  # noqa: BLE001 - a judge outage is reported, not hidden
        return Vote(model, None, f"داور خطا داد: {type(exc).__name__}: {exc}")


async def deliberate(
    catalog: str, transcript: str, reply: str, attachments: str, rubric: str, ideal: str
) -> JuryResult:
    prompt = _prompt(catalog, transcript, reply, attachments, rubric, ideal)
    return JuryResult(list(await asyncio.gather(*(_ask(model, prompt) for model in JUDGE_MODELS))))
