import json
import sqlite3
from fractions import Fraction

from demo import open_lab, summary
from intake.rows import SampleKey
from reports.publish import IssueError
from revision.amendments import NamedAmendment, ReadingChange
from tests.support import LabCase, TRIAL, correction, execute_sql, pair, receipt_numbers, sample


class TestReports(LabCase):
    def test_read_after_correction(self):
        self.seed()
        receipt, original = self.issue(self.complete())
        self.assert_original_report(original)
        self.lab.revisions.publish(TRIAL, amendment=correction())
        corrected_receipt, corrected = self.issue(self.complete())
        self.lab = open_lab(self.directory)
        self.assertEqual(self.lab.reports.read(receipt.report_id), original)
        self.assertEqual(self.lab.reports.read(corrected_receipt.report_id), corrected)
        self.assertEqual((corrected.revision_id, corrected.mean), ('R2', Fraction(-1, 2)))
        self.assert_original_report(self.lab.reports.read(receipt.report_id))

    def test_exact_roundtrip(self):
        left = [sample('A', '0.0002', 'mm'), sample('B', '0.1')]
        right = [sample('A', 0), sample('B', 0)]
        self.publish_rows(left, right, [pair('A', 'A', 'A'), pair('B', 'B', 'B')])
        job = self.complete()
        completed = self.lab.jobs.completed(job)
        receipt, issued = self.issue(job)
        edit = NamedAmendment('右台架零点读数更正', 'R1', readings=(
            ReadingChange(SampleKey(TRIAL, 'right', 'A'), '0.7', 'um'),
        ))
        self.lab.revisions.publish(TRIAL, amendment=edit)
        self.lab = open_lab(self.directory)
        restored = self.lab.reports.read(receipt.report_id)
        expected = {'revision': 'R1', 'pairs': [
            ['A', 'A', 'A', '1/5', '0', [], '1/5'], ['B', 'B', 'B', '1/10', '0', [], '1/10'],
        ], 'valid_count': 2, 'mean': '3/20'}
        self.assertEqual(summary(completed), expected)
        self.assertEqual(restored, issued)
        self.assertEqual(summary(restored), expected)
        self.assertIsInstance(restored.mean, Fraction)
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'V7.exact_roundtrip',
            'input': {'left': left, 'right': right, 'pairs': [['A', 'A', 'A'], ['B', 'B', 'B']],
                      'after_issue': {'right_A_um': '0.7', 'report': receipt.report_id}},
            'expected': expected,
            'actual': summary(completed),
            'downstream_expected': expected,
            'downstream_actual': summary(restored),
            'code_paths': ['intake/units.py', 'analysis/paired.py', 'analysis/totals.py',
                           'reports/codec.py', 'reports/store.py'],
            'oracle': '0.0002 毫米等于 1/5 微米，两次减零，均值为 (1/5+1/10)/2。',
        }, ensure_ascii=False, separators=(',', ':')))

    def test_reinitialize(self):
        self.seed()
        receipt, first = self.issue(self.complete())
        self.lab.revisions.publish(TRIAL, amendment=correction())
        self.lab.report_store.initialize()
        self.lab.revisions.initialize()
        self.lab.register.initialize()
        self.assertEqual(self.lab.reports.read(receipt.report_id), first)
        self.assertEqual(self.lab.catalog.current(TRIAL).revision_id, 'R2')
        self.assertEqual(self.issue(self.complete())[0].report_id, 'REP-2')

    def test_unknown_report(self):
        self.seed()
        self.issue(self.complete())
        for unknown in ('REP-2', 'REP-01', 'missing', 'REP-9999999999999999999'):
            with self.subTest(report=unknown):
                with self.assertRaises(KeyError):
                    self.lab.reports.read(unknown)

    def _install_commit_failure(self):
        execute_sql(self.lab.report_store.database, '''
            CREATE TABLE commit_fixture_parent (id INTEGER PRIMARY KEY);
            CREATE TABLE commit_fixture_child (
                report_number INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL REFERENCES commit_fixture_parent(id)
                    DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER reject_report_commit AFTER INSERT ON report_receipts
            BEGIN
                INSERT INTO commit_fixture_child VALUES (NEW.number, 1);
            END;
        ''')

    def test_failed_commit(self):
        self.seed()
        original_receipt, original = self.issue(self.complete())
        second_job = self.complete()
        self._install_commit_failure()
        with self.assertRaises(IssueError) as error:
            self.lab.reports.issue(second_job)
        self.assertIsInstance(error.exception.__cause__, sqlite3.IntegrityError)
        self.assertIn('FOREIGN KEY', str(error.exception.__cause__))
        with self.assertRaises(KeyError):
            self.lab.reports.read('REP-2')
        self.assertEqual(receipt_numbers(self.lab.report_store.database), [1])
        self.lab = open_lab(self.directory)
        self.assertEqual(self.lab.reports.read(original_receipt.report_id), original)
        with self.assertRaises(KeyError):
            self.lab.reports.read('REP-2')
        self.assertEqual(receipt_numbers(self.lab.report_store.database), [1])

    def test_retry_after_failure(self):
        self.seed()
        self.issue(self.complete())
        job = self.complete()
        self._install_commit_failure()
        with self.assertRaises(IssueError):
            self.lab.reports.issue(job)
        self.assertEqual(receipt_numbers(self.lab.report_store.database), [1])
        execute_sql(self.lab.report_store.database, 'DROP TRIGGER reject_report_commit;')
        receipt, detail = self.issue(job)
        self.assertEqual((receipt.report_id, receipt.job_id), ('REP-2', job))
        self.assertEqual(receipt_numbers(self.lab.report_store.database), [1, 2])
        self.assert_original_report(detail)
