import sqlite3

from analysis.jobs import JobStore
from reports.audit import audit_report
from reports.detail import ReportDetail
from reports.receipts import IssueReceipt
from reports.store import ReportStore


class IssueError(ValueError):
    pass


class ReportPublisher:
    def __init__(self, jobs: JobStore, store: ReportStore):
        self._jobs = jobs
        self._store = store

    def issue(self, job_id: str) -> IssueReceipt:
        try:
            job = self._jobs.completed(job_id)
            detail = ReportDetail.from_completed_job(job)
            audit_report(detail, job)
            return self._store.commit(detail)
        except (KeyError, ValueError, sqlite3.Error) as exc:
            raise IssueError(f'report issue failed: {exc}') from exc

    def read(self, report_id: str) -> ReportDetail:
        detail = self._store.get(report_id)
        if detail is None:
            raise KeyError(report_id)
        return detail
