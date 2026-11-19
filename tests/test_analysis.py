from fractions import Fraction

from analysis.admission import AdmissionError
from intake.rows import SampleKey
from reports.publish import IssueError
from specimens.pages import PageReadError
from tests.support import LabCase, TRIAL, pair, sample


class TestAnalysis(LabCase):
    def test_batch_size(self):
        self.seed()
        split = self.lab.admission.admit(TRIAL)
        once = self.lab.admission.admit(TRIAL)
        self.assertFalse(self.lab.jobs.advance(split, 1).done)
        self.assertTrue(self.lab.jobs.advance(split, 1).done)
        self.assertTrue(self.lab.jobs.advance(once, 2).done)
        reports = [self.issue(job)[1] for job in (split, once)]
        for report in reports:
            self.assert_original_report(report)
        self.assertEqual(reports[0].results, reports[1].results)

    def test_cursor_boundary(self):
        self.seed()
        job = self.lab.admission.admit(TRIAL)
        first = self.lab.jobs.advance(job, 1)
        second = self.lab.jobs.advance(job, 100)
        again = self.lab.jobs.advance(job, 1)
        self.assertEqual([(r.processed, r.total_pairs, r.done) for r in (first, second, again)],
                         [(1, 2, False), (2, 2, True), (2, 2, True)])
        self.assertEqual([row.pair_id for row in first.batch], ['P01'])
        self.assertEqual([row.pair_id for row in second.batch], ['P02'])
        self.assertEqual(again.batch, ())
        self.assert_original_report(self.issue(job)[1])

    def test_invalid_advance(self):
        self.seed()
        job = self.lab.admission.admit(TRIAL)
        self.lab.jobs.advance(job, 1)
        for invalid in (0, -1, True, 1.0, '1'):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.lab.jobs.advance(job, invalid)
        with self.assertRaises(KeyError):
            self.lab.jobs.advance('unknown', 1)
        next_batch = self.lab.jobs.advance(job, 1)
        self.assertTrue(next_batch.done)
        self.assertEqual([row.pair_id for row in next_batch.batch], ['P02'])

    def test_unfinished_issue(self):
        self.seed()
        job = self.lab.admission.admit(TRIAL)
        self.lab.jobs.advance(job, 1)
        with self.assertRaises(IssueError):
            self.lab.reports.issue(job)
        with self.assertRaises(KeyError):
            self.lab.reports.read('REP-1')
        self.lab.jobs.advance(job, 1)
        self.assertEqual(self.issue(job)[0].report_id, 'REP-1')

    def test_fractional_statistics(self):
        self.publish_rows([sample('A', '0.0002', 'mm'), sample('B', '0.1')],
                          [sample('A', 0), sample('B', 0)],
                          [pair('A', 'A', 'A'), pair('B', 'B', 'B')])
        report = self.issue(self.complete())[1]
        self.assertEqual([row.difference for row in report.results], [Fraction(1, 5), Fraction(1, 10)])
        self.assertEqual((report.valid_count, report.mean), (2, Fraction(3, 20)))

    def test_missing_pairs(self):
        self.publish_rows([sample('A', 10), sample('B', None)],
                          [sample('A', 7), sample('B', 2)],
                          [pair('P01', 'A', 'A'), pair('P02', 'B', 'B')])
        report = self.issue(self.complete())[1]
        self.assertEqual([row.difference for row in report.results], [3, None])
        self.assertEqual((report.valid_count, report.mean), (1, 3))
        self.assertEqual((report.results[1].left.original_id, report.results[1].missing), ('B', ('left',)))

        trial = 'ALL-MISSING'
        self.publish_rows([sample('A', None), sample('B', 9)],
                          [sample('A', None), sample('B', None)],
                          [pair('P01', 'A', 'A', trial), pair('P02', 'B', 'B', trial)], trial=trial)
        empty = self.issue(self.complete(trial))[1]
        self.assertEqual((empty.valid_count, empty.mean), (0, None))
        self.assertEqual([row.difference for row in empty.results], [None, None])
        self.assertEqual([row.missing for row in empty.results], [('left', 'right'), ('right',)])

    def test_missing_and_zero(self):
        self.publish_rows([sample('A', 10), sample('B', 0), sample('C', 5)],
                          [sample('A', 7), sample('B', 0), sample('C', None)],
                          [pair('P01', 'A', 'A'), pair('P02', 'B', 'B'), pair('P03', 'C', 'C')])
        report = self.issue(self.complete())[1]
        self.assertEqual([row.difference for row in report.results], [3, 0, None])
        self.assertEqual([row.missing for row in report.results], [(), (), ('right',)])
        self.assertEqual((report.valid_count, report.mean), (2, Fraction(3, 2)))

    def _page_path(self, side, original_id):
        current = self.lab.catalog.current(TRIAL)
        location = current.locations[SampleKey(TRIAL, side, original_id)]
        return self.lab.pages.path_for(location.address)

    def test_incomplete_evidence(self):
        self.seed()
        page = self._page_path('left', 'L1')
        data = page.read_bytes()
        page.unlink()
        try:
            with self.assertRaises(AdmissionError):
                self.lab.admission.admit(TRIAL)
            self.assertEqual(len(self.lab.jobs), 0)
        finally:
            page.write_bytes(data)
        self.assert_original_report(self.issue(self.complete())[1])

    def test_last_page_unreadable(self):
        self.seed()
        existing = self.complete()
        page = self._page_path('right', 'R2a')
        data = page.read_bytes()
        first_page = self._page_path('right', 'R1a')
        page.write_bytes(first_page.read_bytes())
        try:
            with self.assertRaisesRegex(AdmissionError, 'incomplete sample evidence'):
                self.lab.admission.admit(TRIAL)
            self.assertEqual(len(self.lab.jobs), 1)
            self.assert_original_report(self.issue(existing)[1])
        finally:
            page.write_bytes(data)
        self.assert_original_report(self.issue(self.complete())[1])

    def test_no_current(self):
        self.lab.importer.import_batch(TRIAL, 'left', [sample('L1', 10)])
        with self.assertRaisesRegex(AdmissionError, 'no published revision'):
            self.lab.admission.admit(TRIAL)
        self.assertEqual(len(self.lab.jobs), 0)

    def test_failed_batch_preserves_progress(self):
        self.seed()
        job = self.lab.admission.admit(TRIAL)
        page = self._page_path('right', 'R2a')
        data = page.read_bytes()
        page.unlink()
        try:
            with self.assertRaises(PageReadError):
                self.lab.jobs.advance(job, 2)
        finally:
            page.write_bytes(data)
        first = self.lab.jobs.advance(job, 1)
        self.assertEqual((first.processed, first.done, first.batch[0].pair_id), (1, False, 'P01'))
        self.assertTrue(self.lab.jobs.advance(job, 1).done)
        self.assert_original_report(self.issue(job)[1])
