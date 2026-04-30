"""Blocking event-wait helpers over `LogoscoreClient.on_event`.

Upstream's `on_event` is callback-based and runs the callback on a background
thread. Pytest scenarios want blocking semantics ("wait for an event matching
predicate, with a timeout") and need exceptions raised in predicate to fail
the test loudly, not get swallowed by the daemon thread's exception handler.

The pattern is: callback enqueues raw payloads; the test thread dequeues and
evaluates the predicate. Errors from the watcher subprocess are surfaced
through `error_callback` and re-raised on the next `.next()` call.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from queue import Empty, Queue
from typing import Any, Literal, Protocol

__all__ = ["EventTimeout", "Predicate", "Waiter", "subscribe", "wait_for_event"]

_QueueItem = (
    tuple[Literal["event"], dict[str, Any]] | tuple[Literal["error"], BaseException]
)


class _ClientLike(Protocol):
    def on_event(
        self,
        module: str,
        event: str | None,
        callback: Callable[[dict[str, Any]], None],
        *,
        error_callback: Callable[[BaseException], None] | None = ...,
    ) -> Any: ...


class EventTimeout(TimeoutError):
    """Raised when no matching event arrived within `timeout`."""


Predicate = Callable[[dict[str, Any]], bool]


class Waiter:
    """Yielded by `subscribe()`. Call `.next()` repeatedly within one subscription."""

    def __init__(self, queue: Queue[_QueueItem], module: str, event: str | None) -> None:
        self._queue = queue
        self._module = module
        self._event = event

    def next(
        self,
        predicate: Predicate | None = None,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        """Block until an event matching `predicate` arrives, or `timeout` elapses.

        Predicate runs on the test thread (after the dequeue) — exceptions raised
        inside it propagate to the test, unlike exceptions raised inside the
        upstream callback (which the watcher's `_pump` catches and routes through
        `error_callback`).
        """
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EventTimeout(
                    f"no matching event for {self._module}/{self._event} within {timeout}s"
                )
            try:
                slot = self._queue.get(timeout=remaining)
            except Empty as exc:
                raise EventTimeout(
                    f"no matching event for {self._module}/{self._event} within {timeout}s"
                ) from exc
            if slot[0] == "error":
                raise slot[1]
            payload = slot[1]
            if predicate is None or predicate(payload):
                return payload


@contextmanager
def subscribe(
    client: _ClientLike,
    module: str,
    event: str | None = None,
) -> Iterator[Waiter]:
    """Open one `LogoscoreClient.on_event` subscription, yield a `Waiter`.

    Re-using a single subscription across multiple `.next()` calls avoids
    paying the watcher-subprocess startup cost (a fresh `logoscore watch`
    subprocess) per wait.

    NB: upstream's `Subscription.start()` returns immediately after
    `Popen(...)` + `thread.start()`. The watcher needs a moment to come
    live and start emitting NDJSON; events fired in that window are lost.
    If your trigger is a synchronous local action (e.g. `client.call(...)`
    that emits an event before returning), open the subscription, wait
    briefly (typical: 0.2-0.5s, or use a known-pumped sentinel event),
    then trigger.
    """
    queue: Queue[_QueueItem] = Queue()

    def _on_event(payload: dict[str, Any]) -> None:
        queue.put(("event", payload))

    def _on_error(exc: BaseException) -> None:
        queue.put(("error", exc))

    sub = client.on_event(module, event, _on_event, error_callback=_on_error)
    try:
        yield Waiter(queue, module, event)
    finally:
        # tight teardown — upstream default is 5.0s twice; we accept harder
        # kills to keep test feedback fast on flake.
        sub.cancel(timeout=1.0)


def wait_for_event(
    client: _ClientLike,
    module: str,
    event: str | None = None,
    *,
    predicate: Predicate | None = None,
    timeout: float,
) -> dict[str, Any]:
    """One-shot convenience: open a subscription, wait once, close."""
    with subscribe(client, module, event) as w:
        return w.next(predicate, timeout=timeout)
