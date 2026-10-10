"""The jury for free-text replies.

One judge model by default (JUDGE_MODELS below); with more than one, a scenario
passes only if all of them pass it - one "no" is a "no". Each judge sees the customer's side of the conversation, the reply being
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


# For a scenario that carries its own reference (Scenario.reference): the judge
# is not shown the shop's catalog, only the facts that decide this one
# conversation, and the rubric says which product the reply has to introduce.
JUDGE_REFERENCE_SYSTEM_PROMPT = (
    "You are a strict, fair evaluator of a Persian-language sales assistant for an online shop. "
    "You are given the facts that matter for ONE conversation (the reference), the conversation, the "
    "assistant's final reply with anything attached to it, an example of an ideal reply, and a "
    "rubric. Decide whether the final reply satisfies EVERY item of the rubric.\n"
    "- Judge only the final reply; earlier turns are context.\n"
    "- The reference is not the whole catalog. A name, price, feature or link that appears in the "
    "reference must match it exactly. A product that does not appear in the reference is not "
    "automatically invented - but where the rubric says which product must be introduced, or which "
    "must not be, follow the rubric; and a policy, discount or guarantee that the reference does not "
    "state is invented.\n"
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


def _prompt(
    catalog: str, transcript: str, reply: str, attachments: str, rubric: str, ideal: str, partial: bool = False
) -> str:
    return (
        f"### {'اطلاعات مرجع این گفت‌وگو' if partial else 'کاتالوگ کامل فروشگاه (مرجع حقیقت)'}\n{catalog}\n\n"
        f"### گفت‌وگو تا پیش از پاسخ نهایی\n{transcript or '(این اولین پیام است)'}\n\n"
        f"### پاسخ نهایی که باید داوری شود\n{reply}\n\n"
        f"### ضمیمه‌های همین پاسخ (آنچه مشتری زیر پیام می‌بیند)\n{attachments or '(هیچ)'}\n\n"
        f"### نمونه‌ی یک پاسخ ایده‌آل\n{ideal}\n\n"
        f"### معیار پذیرش - پاسخ باید همه‌ی این موارد را برآورده کند\n{rubric}\n"
    )


# One judge: the DeepSeek model the agent itself answers with locally, which
# reads a Persian reply against a rubric more reliably than the two smaller
# models that used to sit here (they needed each other's agreement, and 19 of
# their 220 verdicts still had to be corrected by hand). JUDGE_MODELS in
# the environment, comma-separated, puts a different jury in its place; with
# more than one judge a reply passes only when all of them pass it.
JUDGE_MODELS = [
    m.strip()
    for m in (os.environ.get("JUDGE_MODELS") or os.environ.get("DEEPSEEK_CHAT_MODEL") or "deepseek-v4.1-flash").split(",")
    if m.strip()
]


def _judge(model: str):
    if model.lower().startswith("deepseek"):
        # Same settings as the agent's own DeepSeek link (app/graph.py): the
        # reasoning phase is switched off and the verdict comes back as a
        # function call.
        return ChatOpenAI(
            model=model,
            temperature=0,
            api_key=os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL"),
            extra_body={"thinking": {"type": "disabled"}},
        ).with_structured_output(Verdict, method="function_calling")
    return ChatOpenAI(
        model=model,
        temperature=0,
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_BASE_URL"),
    ).with_structured_output(Verdict)


async def _ask(model: str, prompt: str, partial: bool = False) -> Vote:
    try:
        verdict: Verdict = await _judge(model).ainvoke(
            [SystemMessage(content=JUDGE_REFERENCE_SYSTEM_PROMPT if partial else JUDGE_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        return Vote(model, verdict.passed, verdict.reasoning)
    except Exception as exc:  # noqa: BLE001 - a judge outage is reported, not hidden
        return Vote(model, None, f"داور خطا داد: {type(exc).__name__}: {exc}")


async def deliberate(
    catalog: str, transcript: str, reply: str, attachments: str, rubric: str, ideal: str, partial: bool = False
) -> JuryResult:
    """`catalog` is the whole shop, or - with `partial` - only the reference
    the scenario carries."""
    prompt = _prompt(catalog, transcript, reply, attachments, rubric, ideal, partial)
    return JuryResult(list(await asyncio.gather(*(_ask(model, prompt, partial) for model in JUDGE_MODELS))))
