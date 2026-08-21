#!/usr/bin/env bash
# SW-GATE-137 reproducible runner: SELF_HOSTING_MULTI_LANE_PASS.
#
# Runs the five gate fixtures (parallel, conflict, SHA, review,
# coordinator-kill) plus the W3-L1 hermetic unit suites under `bash -eo
# pipefail`, and emits SELF_HOSTING_MULTI_LANE_PASS only when everything holds.
#
# Usage: bash scripts/gate_self_hosting_multilane.sh
set -eo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"

SUITES=(
  tests/unit/test_legacy_exec.py
  tests/unit/test_coordinator.py
  tests/unit/test_review.py
  tests/unit/test_selfhost.py
  tests/unit/test_doc_arch.py
  tests/gate_b06/test_self_hosting_multilane_gate.py
)

for suite in "${SUITES[@]}"; do
  "$PY" "$REPO_ROOT/$suite"
done

# The gate itself is the final, decisive fixture; its exit code is the verdict.
"$PY" "$REPO_ROOT/tests/gate_b06/test_self_hosting_multilane_gate.py"
