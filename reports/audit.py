from fractions import Fraction

from analysis.jobs import CompletedJob
from reports.detail import ReportDetail


def audit_report(detail: ReportDetail, job: CompletedJob) -> None:
    if (detail.job_id, detail.trial_id, detail.revision_id) != (job.job_id, job.trial_id, job.revision_id):
        raise ValueError('report identity disagrees with the completed job')
    if detail.results != job.results or len(detail.results) != len(job.pairs):
        raise ValueError('report does not contain the completed pair detail')
    pair_ids = [row.pair_id for row in detail.results]
    if pair_ids != sorted(set(pair_ids)):
        raise ValueError('report pairs must be unique and ordered')

    total = Fraction(0)
    valid_count = 0
    for row, pair in zip(detail.results, job.pairs, strict=True):
        if (row.pair_id, row.left, row.right) != (pair.pair_id, pair.left, pair.right):
            raise ValueError(f'wrong source references for {pair.pair_id}')
        expected_missing = []
        if row.left_um is None:
            expected_missing.append('left')
        if row.right_um is None:
            expected_missing.append('right')
        if row.missing != tuple(expected_missing):
            raise ValueError(f'wrong missing positions for {row.pair_id}')
        if expected_missing:
            if row.difference is not None:
                raise ValueError(f'missing pair {row.pair_id} has a difference')
        else:
            difference = row.left_um - row.right_um
            if row.difference != difference:
                raise ValueError(f'wrong difference for {row.pair_id}')
            total += difference
            valid_count += 1

    mean = total / valid_count if valid_count else None
    if (detail.valid_count, detail.mean) != (valid_count, mean):
        raise ValueError('report totals cannot be reconciled with the pair detail')
    if (job.valid_count, job.mean) != (valid_count, mean):
        raise ValueError('completed analysis totals cannot be reconciled with the pair detail')
