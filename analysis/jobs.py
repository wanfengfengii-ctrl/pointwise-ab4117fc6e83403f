from dataclasses import dataclass, field
from fractions import Fraction
from threading import Lock
from uuid import uuid4

from analysis.paired import PairResult, evaluate_pair
from analysis.totals import PairTotals
from revision.pairs import PairSpec
from revision.visibility import PublishedInput


@dataclass(frozen=True)
class CompletedJob:
    job_id: str
    trial_id: str
    revision_id: str
    pairs: tuple[PairSpec, ...]
    results: tuple[PairResult, ...]
    valid_count: int
    mean: Fraction | None


@dataclass
class AnalysisJob:
    job_id: str
    accepted: PublishedInput | None
    results: list[PairResult] = field(default_factory=list)
    totals: PairTotals = field(default_factory=PairTotals)
    finished: CompletedJob | None = None


@dataclass(frozen=True)
class AdvanceResult:
    job_id: str
    revision_id: str
    batch: tuple[PairResult, ...]
    processed: int
    total_pairs: int
    done: bool


class JobStore:
    def __init__(self):
        self._jobs: dict[str, AnalysisJob] = {}
        self._lock = Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)

    def open(self, accepted: PublishedInput) -> str:
        with self._lock:
            job_id = f'JOB-{uuid4().hex}'
            self._jobs[job_id] = AnalysisJob(job_id, accepted)
            return job_id

    def advance(self, job_id: str, batch_size: int) -> AdvanceResult:
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError('batch size must be a positive integer')
        with self._lock:
            job = self._jobs[job_id]
            if job.finished is not None:
                count = len(job.finished.pairs)
                return AdvanceResult(job_id, job.finished.revision_id, (), count, count, True)

            accepted = job.accepted
            assert accepted is not None
            # The accepted revision and its leased pages define the job for its whole
            # lifetime; a later publication must not change an already accepted job.
            start = len(job.results)
            end = min(start + batch_size, len(accepted.pairs))
            batch = []
            totals = job.totals
            for pair in accepted.pairs[start:end]:
                row = evaluate_pair(pair, accepted.evidence.read(pair.left),
                                    accepted.evidence.read(pair.right))
                batch.append(row)
                totals = totals.add(row)

            done = end == len(accepted.pairs)
            if done:
                finished = CompletedJob(
                    job_id, accepted.trial_id, accepted.revision_id, accepted.pairs,
                    tuple(job.results) + tuple(batch), totals.valid_count, totals.mean(),
                )
            job.results.extend(batch)
            job.totals = totals
            if done:
                job.finished = finished
                job.accepted = None
                accepted.evidence.close()
            return AdvanceResult(job_id, accepted.revision_id, tuple(batch), end,
                                 len(accepted.pairs), done)

    def completed(self, job_id: str) -> CompletedJob:
        with self._lock:
            finished = self._jobs[job_id].finished
            if finished is None:
                raise ValueError('analysis is still in progress')
            return finished
