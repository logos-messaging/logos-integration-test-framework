# logos-integration-test-framework

Pytest plugin + helpers for writing integration tests against a `logoscore` daemon. Built on top of [`logos-co/logos-logoscore-py`](https://github.com/logos-co/logos-logoscore-py).

## What's in the box

```
src/logos_integration_test_framework/
├── __init__.py     # exports: subscribe, wait_for_event, Waiter, EventTimeout
├── waits.py        # Queue-backed adapters over LogoscoreClient.on_event
└── fixtures.py     # pytest fixtures: local_daemon, local_client, docker_daemon, docker_client
                    # (auto-loaded via pytest11 entry-point — no import needed)
```

That's the whole package. Client / transport / topology layers live upstream in `logoscore-py` — don't reimplement them.

## Install (consumer-side)

In your module's test repo (e.g. `logos-chat-module/tests/integration/`):

```toml
# pyproject.toml
[project.optional-dependencies]
test = [
    "logos-integration-test-framework @ git+https://github.com/logos-messaging/logos-integration-test-framework.git@<commit-sha>",
    "pytest>=8.0",
]
```

Pin a commit SHA, not a branch. Then `pip install -e '.[test]'` and the four daemon/client fixtures are immediately available in your tests — no `pytest_plugins` declaration needed.

## Writing a test (consumer)

Open the subscription **before** triggering the action — the upstream `logoscore watch` subprocess takes a moment to come live, and events fired before that window are lost. A short sleep or a known-pumped sentinel event is enough.

```python
import time

from logos_integration_test_framework import subscribe

def test_my_module(local_client):  # local_client comes from the auto-loaded plugin
    local_client.load_module("my_module")
    with subscribe(local_client, "my_module", "DoneEvent") as w:
        time.sleep(0.3)  # let the watcher come live
        request_id = local_client.call("my_module", "do_something", "arg")
        event = w.next(
            predicate=lambda e: e["data"][0] == request_id,
            timeout=10.0,
        )
    assert event["event"] == "DoneEvent"
```

Multiple waits in one test — re-use the same subscription:

```python
def test_two_waits(local_client):
    with subscribe(local_client, "my_module") as w:
        time.sleep(0.3)
        local_client.call("my_module", "fire", "first")
        first = w.next(lambda e: e["data"][0] == 1, timeout=5.0)
        local_client.call("my_module", "fire", "second")
        second = w.next(lambda e: e["data"][0] == 2, timeout=5.0)
    assert first != second
```

Predicate exceptions surface on the test thread (unlike exceptions raised inside an upstream `on_event` callback, which the watcher's pump catches and routes to `error_callback`).

The one-shot `wait_for_event(...)` is a convenience for cases where the trigger has *already* happened and the event is still in flight; for the more common subscribe-then-trigger pattern, use `subscribe(...)` directly.

## Fixtures

| Fixture | Scope | Provides | Skip condition |
|---|---|---|---|
| `local_daemon` | module | `logoscore.LogoscoreDaemon` (local subprocess) | `logoscore` not on `PATH` or `LOGOS_MODULES_DIR` unset / missing |
| `local_client` | function | `LogoscoreClient` from `local_daemon` | (inherits) |
| `docker_daemon` | module | `logoscore.LogoscoreDockerDaemon` (containerised) | `docker` CLI absent, image absent, `LOGOSCORE_IMAGE`/`LOGOS_MODULES_DIR` unset |
| `docker_client` | function | `LogoscoreClient` from `docker_daemon` | (inherits) |

Default scopes are `module` for daemons (function-scope is too slow given upstream's `startup_timeout=15.0`; session-scope hides cross-test leaks) and `function` for clients (`client.stop()` would otherwise poison every later test in the module). Override per-test with `pytest.fixture(scope=...)` if needed.

The `docker_*` fixtures need the `docker` CLI on `PATH` — upstream `LogoscoreDockerDaemon` shells out to it (it does not use docker-py). The fixture skips automatically if the binary is absent.

To opt out of the auto-loaded plugin in a particular run: `pytest -p no:logos_integration_test_framework`.

## Contributing to this repo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'    # ← required: registers the pytest11 entry-point
pytest tests/unit -q       # 13 tests: surface check + waits.py
```

`pip install -e '.[dev]'` is **required** before `pytest` — otherwise the entry-point isn't registered and the smoke test (`tests/test_smoke.py`) won't see the `local_*` fixtures. CI does this automatically.

Lint / type / unit runs are gated in `.github/workflows/unit.yml` (Python 3.11 + 3.12). Direct pushes to `master` are rejected by branch-protection rules; merge via PR with green CI.

## Related

- [`logos-co/logos-logoscore-py`](https://github.com/logos-co/logos-logoscore-py) — the Python wrapper this builds on (`LogoscoreDaemon` / `LogoscoreDockerDaemon` / `LogoscoreClient`).
- [`logos-co/logos-test-framework`](https://github.com/logos-co/logos-test-framework) — **different layer**: a C++ unit-test framework for module internals (gtest-style, link-time mock substitution). No overlap with this Python package.
