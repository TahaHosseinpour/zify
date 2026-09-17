# agent-eval

Scenario-level tests for the sales agent's LangGraph state machine
(`apps/agent/app/graph.py`). Unlike the rest of the suite (`/tests/unit`,
`/tests/integration`), most of these call the **real** configured LLM - no
`fake_llm`-style stub on `app.graph.llm` / `structured_llm`. Only the layers
that would otherwise need a live Postgres/pgvector instance (shop lookup,
product/FAQ/shop-info retrieval) are stubbed, with canned rows supplied per
test case. The one exception is `test_retrieval_ranking.py` - pure ranking
logic, no LLM, no key needed (see below).

Auto-marked `eval` by `/tests/conftest.py`; run with `pytest -m eval` (or
`bun run test:agent-eval` from the repo root). Every LLM-calling test skips
(not fails) if `OPENAI_API_KEY` isn't set, or if a live call errors out - so
a quota outage shows up as a skip, not evidence the agent is broken.

## Layout

Six test files, each just iterates a list of cases and has no logic of its
own; scenarios live entirely in `cases/*.py`, decoupled from the test code.

|                     | one node                     | whole graph                     |
|---------------------|-------------------------------|----------------------------------|
| **deterministic**   | `test_node_deterministic.py`  | `test_graph_deterministic.py`    |
| **judge (jury)**    | `test_node_judge.py`          | `test_graph_judge.py`            |

Plus three cross-cutting files that didn't fit that 2x2:

- **`test_retrieval_ranking.py`** - the ranking/trimming nodes
  (`fuse_results_explore`, `fuse_context_product`) are pure Python over a
  `score` number, so they're tested directly with a curated 40-product pool
  (`cases/catalog_40.py`) instead of through a live vector search. No LLM
  call, no skip-on-no-key.
- **`test_graph_guardrail.py`** - adversarial/off-topic customer messages
  (prompt-leak attempts, "ignore your instructions", fake discounts, unearned
  authority claims, requests for payment details, unrelated tasks,
  competitor badmouthing) through the real graph, checking it doesn't comply
  or go off-script. Mostly judge cases, plus two deterministic ones (nothing
  fabricated when nothing was retrieved).

- **deterministic** - for outputs with one exact correct shape (a
  classification field, a boolean, a routed id, a ranked/trimmed list): a
  plain assertion. Each case carries an `expected` string (a human-readable
  statement of the required outcome) next to the `check` function that
  verifies it.
- **judge (jury)** - for outputs that are free-form prose (a sales reply):
  graded by a jury of LLM judges instead of an equality check. Each case
  carries a `rubric` (pass/fail checklist) *and* an `ideal` field - a concrete
  description of what a great reply looks like here - so the jury has a
  standard to compare against, not just abstract criteria.

```
tests/agent-eval/
  conftest.py                    per-suite fixtures: skip-if-no-key (except test_retrieval_ranking), the `graph` fixture
  helpers.py                     user_says/transcript builders, call_or_skip, retrieval stubs, assert_jury_passes
  judge/
    config.py                    JUDGE_MODELS + JURY_PASS_THRESHOLD - the jury's only config surface
    jury.py                      deliberate(): puts one reply to every configured judge, aggregates votes
  cases/
    types.py                     the 4 case dataclasses (shared shape, nothing else)
    catalog.py                   shared realistic product/FAQ fixtures for judge cases (real _product_content-shaped text)
    catalog_40.py                40-product pool + pool_with_scores() for retrieval-ranking cases
    node_deterministic_cases.py  NODE_DETERMINISTIC_CASES (analyze_intent)
    node_judge_cases.py          NODE_JUDGE_CASES (suggest_products/ask_question/product_agent/smalltalk_reply/handle_purchase)
    graph_deterministic_cases.py GRAPH_DETERMINISTIC_CASES
    graph_judge_cases.py         GRAPH_JUDGE_CASES
    retrieval_ranking_cases.py   RETRIEVAL_RANKING_CASES (fuse_results_explore/fuse_context_product)
    guardrail_cases.py           GUARDRAIL_DETERMINISTIC_CASES + GUARDRAIL_JUDGE_CASES
  test_node_deterministic.py
  test_node_judge.py
  test_graph_deterministic.py
  test_graph_judge.py
  test_graph_guardrail.py
  test_retrieval_ranking.py
```

## Adding or removing a scenario

Edit the relevant `cases/*_cases.py` list only - append a
`DeterministicNodeCase`/`JudgeNodeCase`/`DeterministicGraphCase`/`JudgeGraphCase`
(see `cases/types.py` for the fields) or delete one. No test file needs to
change; each one parametrizes over however many cases the list holds.

## The jury

`judge/config.py`:

```python
JUDGE_MODELS: list[str] = ["gpt-5-mini"]
JUDGE_TEMPERATURE = 0.0
JURY_PASS_THRESHOLD = 0.5
```

Every judge model shares the app's own `OPENAI_API_KEY`/`OPENAI_BASE_URL`
(same as `app/graph.py`'s `llm`) - only the model name differs per entry. Add
a second, *distinct* model to actually get jury diversity; duplicating one
model at temperature 0 just re-casts the same vote for no signal. A judge
that errors (bad model name, quota, network) abstains rather than counting as
a fail - see `JuryVerdict` in `judge/jury.py`. A verdict passes only when at
least `JURY_PASS_THRESHOLD` of the judges that responded voted pass.

## Cost

Every test except `test_retrieval_ranking.py` is a real API call
(deterministic node/graph cases: one call to the app's own chat/classifier
model; judge cases: one generation call plus one call per configured judge).
Keep that in mind before running the whole suite repeatedly - `pytest -m eval
-k <case id>` runs a single scenario.
