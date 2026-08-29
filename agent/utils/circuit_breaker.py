"""A minimal circuit breaker: stop calling a failing dependency after N consecutive failures."""
from __future__ import annotations

import time
from enum import Enum
from typing import Callable, TypeVar

T = TypeVar("T")


class State(str, Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """After `failure_threshold` consecutive failures the circuit opens for `recovery_timeout` seconds."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0) -> None:
        self.threshold, self.timeout = failure_threshold, recovery_timeout
        self.failures, self.state, self.opened_at = 0, State.CLOSED, 0.0

    def call(self, fn: Callable[..., T], *args: object, **kwargs: object) -> T:
        """Invoke fn through the breaker; raise RuntimeError while the circuit is open."""
        if self.state is State.OPEN:
            if time.monotonic() - self.opened_at < self.timeout:
                raise RuntimeError(f"Circuit open for {getattr(fn, '__name__', 'callable')}")
            self.state = State.HALF_OPEN
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self.failures += 1
            if self.failures >= self.threshold:
                self.state, self.opened_at = State.OPEN, time.monotonic()
            raise
        self.failures, self.state = 0, State.CLOSED
        return result
