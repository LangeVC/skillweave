"""Integration tests for append-only receipts (SW1311-RECEIPT-001, criteria 1 & 8).

Proves the trace layer's immutable round lineage and append idempotency:

1. Two correction rounds and one integration round produce three immutable
   records with resolvable ids, parent relationships and unchanged prior
   digests.
8. Appending a duplicate record with the same id and bytes is idempotent while
   the same id with different bytes fails closed.

These are behavioural tests over the trace contracts — no text/source-presence
assertions, no harness, and no concrete provider/model name.
"""

import copy
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.trace.contracts import (  # noqa: E402
    AppendOnlyReceiptLog,
    DuplicateDigestError,
    JobResult,
    JobStatus,
    TaskVerdict,
    EvidenceAvailability,
    GateVerdict,
    RoundKind,
    new_append_only_round,
)


def _result(**kw) -> JobResult:
    base = dict(
        job_status=JobStatus.EXITED,
        task_verdict=TaskVerdict.DONE,
        evidence_available=EvidenceAvailability.RECORDED,
        gate_verdict=GateVerdict.PASS,
    )
    base.update(kw)
    return JobResult(**base)


# ── Criterion 1: three immutable records with linkage and unchanged digests ──


def test_two_corrections_and_one_integration_produce_three_immutable_records():
    log = AppendOnlyReceiptLog()

    first = new_append_only_round(
        log, parent_id=None, round_=0, kind=RoundKind.DISPATCH, result=_result()
    )

    corr1 = new_append_only_round(
        log, parent_id=first.record_id, round_=1, kind=RoundKind.CORRECTION,
        result=_result(),
    )
    corr2 = new_append_only_round(
        log, parent_id=corr1.record_id, round_=2, kind=RoundKind.CORRECTION,
        result=_result(),
    )
    integ = new_append_only_round(
        log, parent_id=corr2.record_id, round_=3, kind=RoundKind.INTEGRATION,
        result=_result(),
    )

    assert len(log) == 4  # 1 dispatch + 2 corrections + 1 integration
    correction_records = [r for r in log.records() if r.kind is RoundKind.CORRECTION]
    integration_records = [r for r in log.records() if r.kind is RoundKind.INTEGRATION]
    assert len(correction_records) == 2
    assert len(integration_records) == 1

    # Resolvable ids + parent relationships.
    assert log.resolve_id(corr1.record_id) is corr1
    assert corr1.parent_id == first.record_id
    assert corr2.parent_id == corr1.record_id
    assert integ.parent_id == corr2.record_id

    # Prior digests are unchanged after later appends.
    assert log.resolve_id(first.record_id).digest == first.digest
    assert log.resolve_id(corr1.record_id).digest == corr1.digest
    assert log.resolve_id(corr2.record_id).digest == corr2.digest

    # Each record carries a distinct, resolvable digest.
    digests = {r.digest for r in log.records()}
    assert len(digests) == 4


def test_prior_digests_do_not_change_when_later_records_appended():
    log = AppendOnlyReceiptLog()
    first = new_append_only_round(
        log, parent_id=None, round_=0, kind=RoundKind.DISPATCH, result=_result()
    )
    before = first.digest
    new_append_only_round(
        log, parent_id=first.record_id, round_=1, kind=RoundKind.CORRECTION,
        result=_result(),
    )
    assert first.digest == before
    assert log.resolve_digest(before) is first


def test_record_digest_reflects_body_and_parent():
    # Two records with different parents must hash differently, so a broken
    # heritage cannot silently collapse onto the same digest.
    log = AppendOnlyReceiptLog()
    a = new_append_only_round(log, parent_id=None, round_=0, kind=RoundKind.DISPATCH,
                              result=_result())
    b = new_append_only_round(log, parent_id=a.record_id, round_=1,
                              kind=RoundKind.CORRECTION, result=_result())
    c = new_append_only_round(log, parent_id=b.record_id, round_=2,
                              kind=RoundKind.CORRECTION, result=_result())
    assert len({a.digest, b.digest, c.digest}) == 3


def test_record_ids_are_resolvable():
    log = AppendOnlyReceiptLog()
    r = new_append_only_round(log, parent_id=None, round_=0, kind=RoundKind.DISPATCH,
                              result=_result())
    resolved = log.resolve_id(r.record_id)
    assert resolved is r
    assert log.resolve_id("does-not-exist") is None


# ── Criterion 8: idempotent duplicate vs fail-closed difference ─────────────


def test_duplicate_id_same_bytes_is_idempotent():
    log = AppendOnlyReceiptLog()
    r = new_append_only_round(
        log, parent_id=None, round_=0, kind=RoundKind.DISPATCH, result=_result(),
        record_id="stable-id",
    )
    # Re-append the *same* record id with identical bytes: idempotent.
    again = new_append_only_round(
        log, parent_id=None, round_=0, kind=RoundKind.DISPATCH, result=_result(),
        record_id="stable-id",
    )
    assert again is r
    assert len(log) == 1  # no duplicate entry


def test_duplicate_id_different_bytes_fails_closed():
    log = AppendOnlyReceiptLog()
    new_append_only_round(
        log, parent_id=None, round_=0, kind=RoundKind.DISPATCH, result=_result(),
        record_id="stable-id",
    )
    different = _result(task_verdict=TaskVerdict.FAILED)
    with pytest.raises(DuplicateDigestError):
        new_append_only_round(
            log, parent_id=None, round_=0, kind=RoundKind.DISPATCH,
            result=different, record_id="stable-id",
        )
    assert len(log) == 1


def test_trailing_rounds_preserve_prior_records_after_failed_append():
    # A failed-closed append must not corrupt or drop the prior records.
    log = AppendOnlyReceiptLog()
    new_append_only_round(
        log, parent_id=None, round_=0, kind=RoundKind.DISPATCH, result=_result(),
        record_id="stable-id",
    )
    with pytest.raises(DuplicateDigestError):
        new_append_only_round(
            log, parent_id=None, round_=0, kind=RoundKind.DISPATCH,
            result=_result(task_verdict=TaskVerdict.INCONCLUSIVE),
            record_id="stable-id",
        )
    assert len(log) == 1
    assert log.latest().record_id == "stable-id"


def _run_all() -> int:
    tests = [
        test_two_corrections_and_one_integration_produce_three_immutable_records,
        test_prior_digests_do_not_change_when_later_records_appended,
        test_record_digest_reflects_body_and_parent,
        test_record_ids_are_resolvable,
        test_duplicate_id_same_bytes_is_idempotent,
        test_duplicate_id_different_bytes_fails_closed,
        test_trailing_rounds_preserve_prior_records_after_failed_append,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
