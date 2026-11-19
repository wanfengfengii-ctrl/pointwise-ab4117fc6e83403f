import sqlite3
from contextlib import closing
from pathlib import Path

from reports.codec import decode_report_detail, encode_report_detail
from reports.detail import ReportDetail
from reports.receipts import IssueReceipt, make_issue_receipt


class ReportStore:
    def __init__(self, database: Path):
        self.database = Path(database)

    def initialize(self) -> None:
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS report_bodies (
                    number INTEGER PRIMARY KEY,
                    body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS report_receipts (
                    number INTEGER PRIMARY KEY REFERENCES report_bodies(number),
                    job_id TEXT NOT NULL,
                    trial_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL
                );
            ''')

    def commit(self, detail: ReportDetail) -> IssueReceipt:
        body = encode_report_detail(detail)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys = ON')
            try:
                db.execute('BEGIN IMMEDIATE')
                cursor = db.execute('INSERT INTO report_bodies (body) VALUES (?)', (body,))
                number = cursor.lastrowid
                receipt = make_issue_receipt(number, detail.job_id, detail.trial_id, detail.revision_id)
                db.execute('INSERT INTO report_receipts VALUES (?, ?, ?, ?)', (
                    number, receipt.job_id, receipt.trial_id, receipt.revision_id,
                ))
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return receipt

    def get(self, report_id: str) -> ReportDetail | None:
        if not isinstance(report_id, str) or not report_id.startswith('REP-'):
            return None
        digits = report_id[4:]
        if not digits.isascii() or not digits.isdecimal() or digits.startswith('0') or len(digits) > 19:
            return None
        number = int(digits)
        if number > 2**63 - 1:
            return None
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute('SELECT body FROM report_bodies WHERE number = ?', (number,)).fetchone()
        return None if row is None else decode_report_detail(row[0])
