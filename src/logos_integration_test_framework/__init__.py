"""pytest infrastructure for writing logoscore integration tests.

Public surface: blocking event-wait helpers (`subscribe`, `wait_for_event`,
`Waiter`, `EventTimeout`). Daemon/client pytest fixtures live in
`logos_integration_test_framework.fixtures` and auto-load via the `pytest11`
entry-point — no explicit import needed in consumer test files.
"""

from logos_integration_test_framework.waits import (
    EventTimeout,
    Waiter,
    subscribe,
    wait_for_event,
)

__all__ = ["EventTimeout", "Waiter", "subscribe", "wait_for_event"]
__version__ = "0.2.0"
