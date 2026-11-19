import json
from dataclasses import asdict
from fractions import Fraction

from analysis.paired import PairResult
from intake.rows import SampleKey
from reports.detail import ReportDetail


def _encode_fraction(value: Fraction | None) -> list[int] | None:
    return None if value is None else [value.numerator, value.denominator]


def _decode_fraction(value: list[int] | None) -> Fraction | None:
    return None if value is None else Fraction(*value)


def encode_report_detail(detail: ReportDetail) -> str:
    return json.dumps({
        'job_id': detail.job_id,
        'trial_id': detail.trial_id,
        'revision_id': detail.revision_id,
        'valid_count': detail.valid_count,
        'mean': _encode_fraction(detail.mean),
        'results': [
            {
                'pair_id': row.pair_id,
                'left': asdict(row.left),
                'right': asdict(row.right),
                'left_um': _encode_fraction(row.left_um),
                'right_um': _encode_fraction(row.right_um),
                'missing': list(row.missing),
                'difference': _encode_fraction(row.difference),
            }
            for row in detail.results
        ],
    }, ensure_ascii=False, separators=(',', ':'))


def decode_report_detail(body: str) -> ReportDetail:
    data = json.loads(body)
    rows = tuple(
        PairResult(
            row['pair_id'], SampleKey(**row['left']), SampleKey(**row['right']),
            _decode_fraction(row['left_um']), _decode_fraction(row['right_um']),
            tuple(row['missing']), _decode_fraction(row['difference']),
        )
        for row in data['results']
    )
    return ReportDetail(
        data['job_id'], data['trial_id'], data['revision_id'], rows,
        data['valid_count'], _decode_fraction(data['mean']),
    )
