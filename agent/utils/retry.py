"""Exponential-backoff retry decorators (sync + async)."""
from __future__ import annotations

import asyncio
import functools
import time
from typing import Awaitable, Callable, TypeVar

import structlog

log = structlog.get_logger()
T = TypeVar("T")
_Excs = tuple[type[BaseException], ...]


def retry(
    max_attempts: int = 3, base_delay: float = 2.0, exceptions: _Excs = (Exception,)
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry a sync callable up to max_attempts, sleeping base_delay ** attempt between tries."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> T:
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        raise
                    delay = base_delay ** attempt
                    log.warning("retry.attempt", fn=fn.__name__, attempt=attempt, delay=delay, error=str(exc))
                    time.sleep(delay)
            raise RuntimeError("unreachable")  # pragma: no cover

        return wrapper

    return decorator


def aretry(
    max_attempts: int = 3, base_delay: float = 2.0, exceptions: _Excs = (Exception,)
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Async counterpart of :func:`retry` for coroutine functions."""

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: object, **kwargs: object) -> T:
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_attempts:
                        raise
                    delay = base_delay ** attempt
                    log.warning("retry.attempt", fn=fn.__name__, attempt=attempt, delay=delay, error=str(exc))
                    await asyncio.sleep(delay)
            raise RuntimeError("unreachable")  # pragma: no cover

        return wrapper

    return decorator
