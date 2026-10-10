"""Jury configuration for LLM-as-judge evals.

Every judge shares the app's own OPENAI_API_KEY / OPENAI_BASE_URL (see
apps/agent/app/graph.py) - only the *model* differs per judge. Add, remove or
swap an entry here to change the jury's size or composition; nothing else in
the eval suite (jury.py, or any test file) needs to change.

Pick models your OPENAI_BASE_URL actually serves - an unavailable model just
makes that one judge abstain (see jury.py), so a bad entry here degrades the
jury rather than breaking every eval test.
"""

import os

# A model whose name starts with "deepseek" is asked through DEEPSEEK_BASE_URL
# (see jury.py); any other through OPENAI_BASE_URL. JUDGE_MODELS in the
# environment, comma-separated, replaces the list.
JUDGE_MODELS: list[str] = [
    m.strip()
    for m in (os.environ.get("JUDGE_MODELS") or os.environ.get("DEEPSEEK_CHAT_MODEL") or "deepseek-v4.1-flash").split(",")
    if m.strip()
]

# At JUDGE_TEMPERATURE=0, the same model voting more than once always casts
# the same vote - it buys no real jury diversity, just N-1 wasted calls. Add
# a second *distinct* cheap model here for an actual jury; don't duplicate
# this one.

JUDGE_TEMPERATURE = 0.0

# A rubric passes only when at least this fraction of the jury's *counted*
# votes (judges that didn't error out) vote pass. 0.5 = strict majority - a
# 1-1 tie among 2 judges fails.
JURY_PASS_THRESHOLD = 0.5
