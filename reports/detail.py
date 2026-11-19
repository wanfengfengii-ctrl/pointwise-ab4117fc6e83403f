from dataclasses import dataclass
from fractions import Fraction

from analysis.jobs import CompletedJob
from analysis.paired import PairResult


@dataclass(frozen=True)
class ReportDetail:
    job_id: str
    trial_id: str
    revision_id: str
    results: tuple[PairResult, ...]
    valid_count: int
    mean: Fraction | None

    @classmethod
    def from_completed_job(cls, job: CompletedJob) -> 'ReportDetail':
        return cls(job.job_id, job.trial_id, job.revision_id, job.results, job.valid_count, job.mean)
