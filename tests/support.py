import sqlite3
import sys
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from demo import open_lab, seed_example
from intake.rows import SampleKey
from revision.amendments import NamedAmendment
from revision.pairs import PairSpec


TRIAL = 'CP-042'


def sample(original_id, value, unit='um'):
    return {'original_id': original_id, 'value': value, 'unit': unit}


def pair(pair_id, left, right, trial=TRIAL):
    return PairSpec(pair_id, SampleKey(trial, 'left', left), SampleKey(trial, 'right', right))


def correction(right='R2b', parent='R1'):
    return NamedAmendment(f'替换 P02 右样本为 {right}', parent, (pair('P02', 'L2', right),))


def execute_sql(database, script):
    with closing(sqlite3.connect(database)) as db:
        db.executescript(script)


def receipt_numbers(database):
    with closing(sqlite3.connect(database)) as db:
        return [row[0] for row in db.execute('SELECT number FROM report_receipts ORDER BY number')]


def on_call(code, callback, action):
    def trace(frame, event, argument):
        if event == 'call' and frame.f_code is code:
            callback()
        return None

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        return action()
    finally:
        sys.settrace(previous)


class LabCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='coating-lab-test-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.lab = open_lab(self.directory)

    def seed(self):
        source, revision = seed_example(self.lab)
        self.assertEqual(source['trial_id'], TRIAL)
        self.assertEqual(revision, 'R1')

    def publish_rows(self, left, right, pairs, trial=TRIAL):
        self.lab.importer.import_batch(trial, 'left', left)
        self.lab.importer.import_batch(trial, 'right', right)
        return self.lab.revisions.publish(trial, pairs)

    def complete(self, trial=TRIAL):
        job = self.lab.admission.admit(trial)
        self.assertTrue(self.lab.jobs.advance(job, 100).done)
        return job

    def issue(self, job):
        receipt = self.lab.reports.issue(job)
        detail = self.lab.reports.read(receipt.report_id)
        self.assertEqual((receipt.job_id, receipt.trial_id, receipt.revision_id),
                         (detail.job_id, detail.trial_id, detail.revision_id))
        return receipt, detail

    def assert_original_report(self, report):
        self.assertEqual((report.trial_id, report.revision_id), (TRIAL, 'R1'))
        self.assertEqual([row.pair_id for row in report.results], ['P01', 'P02'])
        self.assertEqual([(row.left.original_id, row.right.original_id) for row in report.results],
                         [('L1', 'R1a'), ('L2', 'R2a')])
        self.assertEqual([(row.left_um, row.right_um) for row in report.results], [(10, 7), (8, 7)])
        self.assertEqual([row.difference for row in report.results], [3, 1])
        self.assertEqual((report.valid_count, report.mean), (2, 2))
