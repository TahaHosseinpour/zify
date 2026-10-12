"""Circuit breakers for the upstream model providers.

Every model call the agent makes goes to a provider that can stop answering
(the OpenAI route accepted connections and then returned nothing for hours).
Without a breaker each turn would wait out the full timeout on the dead
provider before trying the next one; with it, a provider that has just failed
several times in a row is skipped outright, and probed again with a single
request once it has had time to recover.

Three states:

- closed     normal; every call goes through.
- open       the provider failed `failure_threshold` times in a row; calls are
             refused without touching the network until `reset_seconds` pass.
- half-open  the wait is over; exactly one trial call is let through. Success
             closes the breaker, failure opens it for another full wait.
"""

from __future__ import annotations

import os
import time
from typing import Callable

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

FAILURE_THRESHOLD = int(os.environ.get("BREAKER_FAILURE_THRESHOLD", "3"))
RESET_SECONDS = float(os.environ.get("BREAKER_RESET_SECONDS", "30"))


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = FAILURE_THRESHOLD,
        reset_seconds: float = RESET_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._trial_in_flight = False

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return CLOSED
        if self._clock() - self._opened_at >= self.reset_seconds:
            return HALF_OPEN
        return OPEN

    def available(self) -> bool:
        """Whether a call would be let through right now, without claiming the
        half-open trial slot. For choosing a provider ahead of the call."""
        state = self.state
        return state == CLOSED or (state == HALF_OPEN and not self._trial_in_flight)

    def allow(self) -> bool:
        """Ask to make a call. A True answer must be followed by exactly one of
        record_success / record_failure / release."""
        state = self.state
        if state == CLOSED:
            return True
        if state == HALF_OPEN and not self._trial_in_flight:
            self._trial_in_flight = True
            return True
        return False

    def record_success(self) -> None:
        if self._opened_at is not None:
            print(f"[agent] breaker {self.name}: recovered - closed")
        self._failures = 0
        self._opened_at = None
        self._trial_in_flight = False

    def record_failure(self) -> None:
        was_trial = self._trial_in_flight
        self._trial_in_flight = False
        self._failures += 1
        if was_trial or self._failures >= self.failure_threshold:
            if self._opened_at is None or was_trial:
                print(
                    f"[agent] breaker {self.name}: open for {self.reset_seconds:.0f}s "
                    f"after {self._failures} consecutive failure(s)"
                )
            self._opened_at = self._clock()

    def release(self) -> None:
        """The call ended without saying anything about the provider's health
        (it was cancelled, or failed on our side). Frees the trial slot."""
        self._trial_in_flight = False

    def reset(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._trial_in_flight = False


_breakers: dict[str, CircuitBreaker] = {}


def breaker(name: str) -> CircuitBreaker:
    """The process-wide breaker for a provider. Shared by every caller of that
    provider, so the chat model and the intent model learn from each other's
    failures instead of each waiting out its own."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name)
    return _breakers[name]


def reset_all() -> None:
    for b in _breakers.values():
        b.reset()


# Statuses that say the *provider* is in trouble (or refuses us entirely), as
# opposed to this one request being wrong.
# 402 is the gateway saying the account is out of credit: every call will fail
# the same way until someone tops it up, so it has to open the breaker - left
# out, each message paid for a failed round trip to that provider first.
_PROVIDER_FAULT_STATUSES = {401, 402, 403, 408, 429}


def is_provider_fault(exc: BaseException) -> bool:
    """Whether an error should count against the provider's breaker.

    A 400/404/422 is our request being wrong; sending it again to the same
    healthy provider would fail the same way, so it says nothing about health.
    Everything without a status (connection refused, timeout, a dropped
    stream) and every 5xx does.
    """
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if not isinstance(status, int):
        return True
    return status >= 500 or status in _PROVIDER_FAULT_STATUSES
