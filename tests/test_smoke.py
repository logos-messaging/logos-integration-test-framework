"""End-to-end smoke against a real `logoscore` binary.

Skipped without the binary + `LOGOS_MODULES_DIR` (the `local_*` fixtures
auto-skip; they're auto-loaded by the `pytest11` entry-point declared in
`pyproject.toml`). Not part of CI yet — runs locally for human verification.
"""

from __future__ import annotations

import pytest
from logoscore import LogoscoreClient

from logos_integration_test_framework import EventTimeout, wait_for_event


def test_local_client_status(local_client: LogoscoreClient) -> None:
    status = local_client.status()
    assert isinstance(status, dict)


def test_wait_for_event_drives_watcher(local_client: LogoscoreClient) -> None:
    """End-to-end check that `wait_for_event` actually spawns the watcher.

    No module is loaded so no event will ever fire; we just need to confirm
    the helper drives `logoscore watch` against the real daemon and reaches
    its timeout cleanly (no hangs, no exceptions other than `EventTimeout`).
    """
    with pytest.raises(EventTimeout):
        wait_for_event(local_client, "nonexistent-module", timeout=1.0)
