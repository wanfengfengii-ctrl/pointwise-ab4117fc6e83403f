import sqlite3

from analysis.jobs import JobStore
from intake.rows import require_identifier
from revision.visibility import RevisionVisibility
from specimens.pages import PageReadError


class AdmissionError(ValueError):
    pass


class AnalysisAdmission:
    def __init__(self, visibility: RevisionVisibility, jobs: JobStore):
        self._visibility = visibility
        self._jobs = jobs

    def admit(self, trial_id: str) -> str:
        try:
            require_identifier(trial_id, 'trial')
            captured = self._visibility.capture(trial_id)
        except (ValueError, LookupError, OSError, sqlite3.Error) as exc:
            reason = 'incomplete sample evidence' if isinstance(exc, PageReadError) else str(exc)
            raise AdmissionError(f'analysis rejected: {reason}') from exc
        try:
            return self._jobs.open(captured)
        except BaseException:
            captured.evidence.close()
            raise
