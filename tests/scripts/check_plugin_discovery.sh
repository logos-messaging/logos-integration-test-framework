#!/usr/bin/env bash
# Verify the pytest11 entry-point auto-loads fixtures into a fresh consumer venv.
#
# What this proves: a downstream consumer who runs `pip install
# logos-integration-test-framework` (no `pytest_plugins` declarations, no
# `from ... import ...`) can still use `local_daemon` as a fixture in their
# tests because pytest discovered the plugin via dist-info entry-points.
#
# Why a separate venv: the dev venv already has the package as an editable
# install, so a local pytest run there proves nothing new — the entry-point
# *would* be found, but so would a stray `pytest_plugins` line in our own
# `tests/conftest.py`. A clean venv removes that ambiguity.
#
# This script is not run in CI yet; first downstream consumer to land theirs
# (chat-module) exercises the same code path for real.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

VENV_DIR="$TMPDIR_ROOT/venv"
TESTPROJ_DIR="$TMPDIR_ROOT/consumer"

echo "==> Creating fresh venv at $VENV_DIR"
python3.12 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip

echo "==> Installing the framework from $REPO_ROOT (non-editable)"
"$VENV_DIR/bin/pip" install --quiet "$REPO_ROOT"

echo "==> Installing pytest in the consumer venv"
"$VENV_DIR/bin/pip" install --quiet "pytest>=8.0"

echo "==> Writing a minimal consumer test that uses the auto-loaded fixture"
mkdir -p "$TESTPROJ_DIR"
cat > "$TESTPROJ_DIR/test_consumer.py" <<'PY'
def test_local_daemon_fixture_is_visible(local_daemon):
    # Will skip if `logoscore` binary isn't on PATH or LOGOS_MODULES_DIR is unset.
    # Important: we just need pytest to *recognise* `local_daemon` as a fixture.
    # If the entry-point auto-load failed, pytest would error with
    # "fixture 'local_daemon' not found" — that's the regression we catch here.
    pass
PY

echo "==> Collecting (no execution) — proves the fixture is recognised"
cd "$TESTPROJ_DIR"
"$VENV_DIR/bin/pytest" --collect-only -q test_consumer.py

echo "==> Running with skip-friendly env (no logoscore binary expected)"
"$VENV_DIR/bin/pytest" -q test_consumer.py || rc=$?
rc=${rc:-0}
# Acceptable outcomes: exit 0 (passed) or exit 5 (no tests) or skipped (which is exit 0 in pytest).
# An exit code of 1 (failures) or 4 (collection error → fixture-not-found) means broken plugin.
case "$rc" in
  0) echo "==> OK — fixture resolved (test ran or skipped)";;
  5) echo "==> No tests collected — unexpected"; exit 1;;
  *) echo "==> FAIL — pytest exit $rc (likely fixture not found via entry-point)"; exit "$rc";;
esac
