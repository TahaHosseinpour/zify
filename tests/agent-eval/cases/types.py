"""Case shapes shared by every file under cases/.

A test file (test_node_deterministic.py, test_node_judge.py,
test_graph_deterministic.py, test_graph_judge.py) parametrizes over a list of
these and never hardcodes how many there are or what they contain - adding or
removing a scenario is purely an edit to one of the cases/*_cases.py files.

Every case carries its expected/desired outcome as data, not just as
assertion code: `expected` for the deterministic cases (a human-readable
statement of what must be true, next to the `check` that actually verifies
it) and `ideal` for the judge cases (a concrete description of what a great
reply looks like, given to the jury alongside `rubric` so it has a standard
to compare against instead of just a checklist).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class DeterministicNodeCase:
    """A single node, called directly, whose output has an exact expected
    shape (a classification, a flag, a routed field) - checked with a plain
    assertion, not a judge."""

    id: str
    node: str  # attribute name on app.graph, e.g. "analyze_intent"
    state: dict[str, Any]
    expected: str  # human-readable statement of the required outcome
    check: Callable[[dict], None]  # gets the node's returned update dict; raises AssertionError on failure


@dataclass
class JudgeNodeCase:
    """A single node, called directly, whose output is free text - graded by
    the jury against `rubric` (checklist) and `ideal` (a concrete example of
    what a great reply looks like) rather than compared for equality."""

    id: str
    node: str
    state: dict[str, Any]
    rubric: str
    ideal: str
    faq: list = field(default_factory=list)  # only consumed by ask_question
    shop_info: list = field(default_factory=list)  # only consumed by ask_question


@dataclass
class DeterministicGraphCase:
    """A full turn through the compiled graph (retrieval stubbed, everything
    else real) whose final state has fields checkable by a plain assertion."""

    id: str
    input_state: dict[str, Any]
    expected: str
    check: Callable[[dict], None]  # gets the graph's final state
    retrieval: dict[str, list] = field(default_factory=dict)


@dataclass
class JudgeGraphCase:
    """A full turn through the compiled graph, graded by the jury against
    `rubric` and `ideal` on the reply the customer would actually see."""

    id: str
    input_state: dict[str, Any]
    rubric: str
    ideal: str
    retrieval: dict[str, list] = field(default_factory=dict)
