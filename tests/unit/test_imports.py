"""CI-runnable surface check.

Catches upstream surface drift (e.g. PR #1 force-push removing a symbol)
before any fixture-dependent test fails opaquely. Runs anywhere — no
binary, no docker, no env vars.
"""

from __future__ import annotations


def test_logoscore_surface() -> None:
    # `issue_token` / `revoke_token` / `list_tokens` are deliberately not
    # surfaced — we don't call them, and the master-branch fallback path
    # (after PR #1 merges, or if we re-pin to @master before merge) may
    # not export them yet. Adding them here would make a one-line re-pin
    # break the import smoke spuriously.
    from logoscore import (  # noqa: F401
        CONTAINER_TCP_PORT,
        DaemonNotRunningError,
        LogoscoreClient,
        LogoscoreDaemon,
        LogoscoreDockerDaemon,
        LogoscoreError,
        MethodError,
        ModuleError,
        Subscription,
        docker_available,
        image_present,
        pick_free_port,
    )


def test_logos_integration_test_framework_surface() -> None:
    from logos_integration_test_framework import (  # noqa: F401
        EventTimeout,
        Waiter,
        subscribe,
        wait_for_event,
    )
