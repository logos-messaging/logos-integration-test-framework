"""Unit tests for `logos_integration_test_framework.waits`.

Drives a stub client whose `on_event` immediately fires crafted payloads
through the registered callback. Verifies:
- match-on-first-event,
- predicate-mismatch-then-match,
- timeout raises `EventTimeout`,
- predicate exceptions surface on the test thread (not swallowed by the
  daemon-thread handler the way they would inside the upstream callback),
- `error_callback` path delivers errors as raised exceptions on `.next()`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from logos_integration_test_framework import (
    EventTimeout,
    Waiter,
    subscribe,
    wait_for_event,
)


class _StubSubscription:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self, timeout: float = 5.0) -> None:
        self.cancelled = True


class _StubClient:
    """Mimics `LogoscoreClient.on_event`. Each registered callback can be
    fired manually via `.fire(payload)` / `.fire_error(exc)`.
    """

    def __init__(self) -> None:
        self.subs: list[
            tuple[
                str,
                str | None,
                Callable[[dict[str, Any]], None],
                Callable[[BaseException], None] | None,
            ]
        ] = []

    def on_event(
        self,
        module: str,
        event: str | None,
        callback: Callable[[dict[str, Any]], None],
        *,
        error_callback: Callable[[BaseException], None] | None = None,
    ) -> _StubSubscription:
        self.subs.append((module, event, callback, error_callback))
        return _StubSubscription()

    @property
    def latest_callback(self) -> Callable[[dict[str, Any]], None]:
        return self.subs[-1][2]

    @property
    def latest_error_callback(self) -> Callable[[BaseException], None] | None:
        return self.subs[-1][3]


def test_match_on_first_event() -> None:
    client = _StubClient()
    with subscribe(client, "delivery") as w:
        client.latest_callback({"kind": "X", "n": 1})
        got = w.next(timeout=1.0)
    assert got == {"kind": "X", "n": 1}


def test_predicate_skips_until_match() -> None:
    client = _StubClient()
    with subscribe(client, "delivery", "Sent") as w:
        client.latest_callback({"n": 1})
        client.latest_callback({"n": 2})
        client.latest_callback({"n": 3})
        got = w.next(lambda e: e["n"] == 3, timeout=1.0)
    assert got["n"] == 3


def test_timeout_with_no_events() -> None:
    client = _StubClient()
    with subscribe(client, "delivery") as w, pytest.raises(EventTimeout):
        w.next(timeout=0.05)


def test_timeout_when_predicate_never_matches() -> None:
    client = _StubClient()
    with subscribe(client, "delivery") as w:
        client.latest_callback({"n": 1})
        client.latest_callback({"n": 2})
        with pytest.raises(EventTimeout):
            w.next(lambda e: e["n"] == 99, timeout=0.05)


def test_predicate_exception_surfaces_on_test_thread() -> None:
    """Crucial: predicate runs in `.next`, not in the on_event callback,
    so a predicate raise reaches the test rather than being captured by
    upstream's `Subscription._pump`.
    """
    client = _StubClient()
    with subscribe(client, "delivery") as w:
        client.latest_callback({"n": 1})

        def boom(_: dict[str, Any]) -> bool:
            raise RuntimeError("predicate-boom")

        with pytest.raises(RuntimeError, match="predicate-boom"):
            w.next(boom, timeout=1.0)


def test_error_callback_surfaces_via_next() -> None:
    client = _StubClient()
    with subscribe(client, "delivery") as w:
        cb = client.latest_error_callback
        assert cb is not None
        cb(RuntimeError("watcher exploded"))
        with pytest.raises(RuntimeError, match="watcher exploded"):
            w.next(timeout=1.0)


def test_subscription_cancelled_on_exit() -> None:
    client = _StubClient()
    sub_holder: list[_StubSubscription] = []
    real_on_event = client.on_event

    def capture(*args: Any, **kwargs: Any) -> _StubSubscription:
        sub = real_on_event(*args, **kwargs)
        sub_holder.append(sub)
        return sub

    client.on_event = capture  # type: ignore[method-assign]
    with subscribe(client, "delivery"):
        pass
    assert sub_holder[0].cancelled is True


def test_wait_for_event_one_shot() -> None:
    client = _StubClient()
    # Schedule the event before calling wait_for_event by registering through
    # a wrapper that fires immediately upon subscription.
    real_on_event = client.on_event

    def fire_immediately(*args: Any, **kwargs: Any) -> _StubSubscription:
        sub = real_on_event(*args, **kwargs)
        client.latest_callback({"kind": "ok"})
        return sub

    client.on_event = fire_immediately  # type: ignore[method-assign]
    got = wait_for_event(client, "delivery", "Sent", timeout=1.0)
    assert got == {"kind": "ok"}


def test_waiter_type_exposed() -> None:
    """Surface check: the public `Waiter` class is the one yielded."""
    client = _StubClient()
    with subscribe(client, "delivery") as w:
        assert isinstance(w, Waiter)


def test_subscription_reused_across_next_calls() -> None:
    """The long-lived design must not re-call `on_event` per `.next()`."""
    client = _StubClient()
    with subscribe(client, "delivery") as w:
        client.latest_callback({"n": 1})
        client.latest_callback({"n": 2})
        first = w.next(timeout=1.0)
        second = w.next(timeout=1.0)
    assert first == {"n": 1}
    assert second == {"n": 2}
    assert len(client.subs) == 1


def test_event_none_propagates() -> None:
    """`subscribe(client, module)` must pass `event=None` to upstream."""
    client = _StubClient()
    with subscribe(client, "delivery"):
        pass
    assert client.subs[0][1] is None


def test_resume_after_timeout() -> None:
    """A `.next()` that timed out must not poison the queue."""
    client = _StubClient()
    with subscribe(client, "delivery") as w:
        with pytest.raises(EventTimeout):
            w.next(timeout=0.05)
        client.latest_callback({"n": 1})
        got = w.next(timeout=1.0)
    assert got == {"n": 1}
