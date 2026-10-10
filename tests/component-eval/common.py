"""What the component evaluations share: paths, the environment, the provider
check, and where results are written."""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
COMPARISON = REPO_ROOT / "tests" / "comparison-eval"
for path in (REPO_ROOT / "apps" / "agent", COMPARISON, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_environment() -> None:
    """Hosted models only, as in the comparison benchmark."""
    os.environ["USE_LOCAL_MODELS"] = "false"
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")


async def providers_ready() -> bool:
    """The comparison benchmark's pre-flight check: one tiny request to every
    provider the run can use. LLM calls go to whichever chat provider the
    environment puts first (CHAT_PROVIDER_ORDER)."""
    import run_comparison

    return await run_comparison._provider_is_up(False)


def switch_off(name: str) -> None:
    from app import breaker

    gate = breaker.breaker(name)
    gate.reset_seconds = float("inf")
    for _ in range(gate.failure_threshold):
        gate.record_failure()


def switch_on(name: str) -> None:
    from app import breaker

    breaker.breaker(name).reset()


def out_dir(given: str, name: str) -> Path:
    path = Path(given) if given else (
        REPO_ROOT / "reports" / "component-eval" / f"{datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}-{name}"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    # utf-8-sig so Excel opens the Persian columns correctly.
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def percent(part: int, whole: int) -> float | str:
    return round(100 * part / whole, 1) if whole else ""
