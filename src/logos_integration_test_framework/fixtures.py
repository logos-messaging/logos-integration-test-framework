"""Pytest fixtures wrapping `logoscore.LogoscoreDaemon` / `LogoscoreDockerDaemon`.

Auto-loaded as a pytest plugin via the `pytest11` entry-point declared in
`pyproject.toml`. Any project that installs `logos-integration-test-framework`
gets these fixtures available without `pytest_plugins` declarations.

Both daemon flavors auto-skip when their environmental requirements aren't
met (binary on PATH, image present, modules dir set, …) — there's no
in-package binary or image. Set `LOGOS_MODULES_DIR` (and `LOGOSCORE_IMAGE`
for the docker fixture) in CI/local env to enable.

Daemons are `module`-scope (function-scope pays the upstream
`startup_timeout=15.0` per test; session-scope hides cross-test state leakage).
Clients are `function`-scope on top of the shared daemon — `client()` is a
cheap construction, but `client.stop()` shells out `logoscore stop` to the
daemon, which would otherwise poison every later test in the module.

`logoscore` is imported **lazily** inside each fixture body. Many consumers
will only use `wait_for_event` and never touch a daemon fixture — eager
imports would charge them subprocess/Docker shim startup on every pytest run.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from logoscore import LogoscoreClient, LogoscoreDaemon, LogoscoreDockerDaemon


def _modules_dir_or_skip() -> Path:
    raw = os.environ.get("LOGOS_MODULES_DIR")
    if not raw:
        pytest.skip("LOGOS_MODULES_DIR not set")
    path = Path(raw)
    if not path.is_dir():
        pytest.skip(f"LOGOS_MODULES_DIR={raw!r} is not an existing directory")
    return path


@pytest.fixture(scope="module")
def local_daemon() -> Iterator[LogoscoreDaemon]:
    if shutil.which("logoscore") is None:
        pytest.skip("`logoscore` binary not on PATH")
    modules_dir = _modules_dir_or_skip()

    from logoscore import LogoscoreDaemon

    with LogoscoreDaemon(modules_dir=modules_dir) as daemon:
        yield daemon


@pytest.fixture
def local_client(local_daemon: LogoscoreDaemon) -> LogoscoreClient:
    return local_daemon.client()


@pytest.fixture(scope="module")
def docker_daemon() -> Iterator[LogoscoreDockerDaemon]:
    from logoscore import LogoscoreDockerDaemon, docker_available, image_present

    if not docker_available():
        pytest.skip("docker not available on host")
    image = os.environ.get("LOGOSCORE_IMAGE")
    if not image:
        pytest.skip("LOGOSCORE_IMAGE not set")
    if not image_present(image):
        pytest.skip(f"docker image {image!r} not present locally")
    modules_dir = _modules_dir_or_skip()

    with LogoscoreDockerDaemon(image=image, modules_dir=modules_dir) as daemon:
        yield daemon


@pytest.fixture
def docker_client(docker_daemon: LogoscoreDockerDaemon) -> Any:
    return docker_daemon.client(binary="logoscore")
