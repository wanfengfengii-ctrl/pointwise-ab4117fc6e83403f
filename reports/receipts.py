from dataclasses import dataclass


@dataclass(frozen=True)
class IssueReceipt:
    report_id: str
    job_id: str
    trial_id: str
    revision_id: str


def make_issue_receipt(number: int, job_id: str, trial_id: str, revision_id: str) -> IssueReceipt:
    return IssueReceipt(f'REP-{number}', job_id, trial_id, revision_id)
