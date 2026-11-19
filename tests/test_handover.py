from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from threading import Event

from demo import open_lab
from intake.rows import SampleKey
from revision.amendments import NamedAmendment, ReadingChange
from revision.visibility import RevisionVisibility
from specimens.evidence import EvidenceStore
from specimens.pages import PageReadError
from tests.support import LabCase, TRIAL, correction, on_call


class TestHandover(LabCase):
    def assert_corrected_report(self, report):
        self.assertEqual((report.trial_id, report.revision_id), (TRIAL, 'R2'))
        self.assertEqual([row.pair_id for row in report.results], ['P01', 'P02'])
        self.assertEqual([row.difference for row in report.results], [3, -4])
        self.assertEqual((report.valid_count, report.mean), (2, Fraction(-1, 2)))
        row = report.results[1]
        self.assertEqual((row.left.original_id, row.right.original_id, row.left_um, row.right_um, row.missing),
                         ('L2', 'R2b', 8, 12, ()))

    def test_revision_between_batches(self):
        self.seed()
        old = self.lab.admission.admit(TRIAL)
        first = self.lab.jobs.advance(old, 1)
        self.assertEqual((first.revision_id, first.processed, first.done, first.batch[0].difference),
                         ('R1', 1, False, 3))
        self.assertEqual(self.lab.revisions.publish(TRIAL, amendment=correction()), 'R2')
        new = self.lab.admission.admit(TRIAL)
        self.assertEqual(self.lab.jobs.advance(new, 1).revision_id, 'R2')
        self.assertTrue(self.lab.jobs.advance(old, 1).done)
        self.assertTrue(self.lab.jobs.advance(new, 1).done)
        self.assert_original_report(self.issue(old)[1])
        self.assert_corrected_report(self.issue(new)[1])

    def test_missing_replacement(self):
        self.seed()
        old = self.lab.admission.admit(TRIAL)
        self.lab.jobs.advance(old, 1)
        self.lab.revisions.publish(TRIAL, amendment=correction('R2m'))
        new = self.complete()
        self.lab.jobs.advance(old, 1)
        original = self.issue(old)[1]
        corrected = self.issue(new)[1]
        self.assert_original_report(original)
        self.assertEqual((corrected.revision_id, corrected.valid_count, corrected.mean), ('R2', 1, 3))
        self.assertEqual([row.difference for row in corrected.results], [3, None])
        row = corrected.results[1]
        self.assertEqual((row.left.original_id, row.right.original_id, row.right_um, row.missing),
                         ('L2', 'R2m', None, ('right',)))

    def test_same_sample_reading(self):
        self.seed()
        old = self.lab.admission.admit(TRIAL)
        self.lab.jobs.advance(old, 1)
        key = SampleKey(TRIAL, 'right', 'R2a')
        edit = NamedAmendment('修正原号读数', 'R1', readings=(ReadingChange(key, '0.012', 'mm'),))
        self.assertEqual(self.lab.revisions.publish(TRIAL, amendment=edit), 'R2')
        new = self.complete()
        self.lab.jobs.advance(old, 1)
        self.assert_original_report(self.issue(old)[1])
        revised = self.issue(new)[1]
        self.assertEqual((revised.results[1].right, revised.results[1].right_um, revised.results[1].difference),
                         (key, 12, -4))
        self.assertEqual(self.lab.register.get_sample(key).micrometres, 7)
        self.lab.revisions.publish(TRIAL, amendment=correction('R2b', parent='R2'))
        self.lab = open_lab(self.directory)
        self.lab.revisions.publish(TRIAL, amendment=correction('R2a', parent='R3'))
        restored_override = self.issue(self.complete())[1]
        self.assertEqual((restored_override.revision_id, restored_override.results[1].right_um), ('R4', 12))

    def test_slot_reuse(self):
        self.seed()
        old_key = SampleKey(TRIAL, 'right', 'R2a')
        original_location = self.lab.catalog.current(TRIAL).locations[old_key]
        old_jobs = [self.lab.admission.admit(TRIAL) for _ in range(2)]
        for job in old_jobs:
            self.lab.jobs.advance(job, 1)
        self.lab.revisions.publish(TRIAL, amendment=correction())
        new = self.lab.admission.admit(TRIAL)
        new_key = SampleKey(TRIAL, 'right', 'R2b')
        new_location = self.lab.catalog.current(TRIAL).locations[new_key]
        self.assertNotEqual(new_location.address.slot, original_location.address.slot)

        self.lab.revisions.initialize()
        self.assertEqual(self.lab.pages.read(original_location, old_key).micrometres, 7)
        self.lab.jobs.advance(old_jobs[0], 1)
        self.assertEqual(self.lab.pages.read(original_location, old_key).micrometres, 7)
        self.lab.jobs.advance(old_jobs[1], 1)
        for job in old_jobs:
            self.assert_original_report(self.issue(job)[1])
        with self.assertRaises(PageReadError):
            self.lab.pages.read(original_location, old_key)

        self.assertEqual(self.lab.revisions.publish(TRIAL, amendment=correction('R2m', parent='R2')), 'R3')
        missing_key = SampleKey(TRIAL, 'right', 'R2m')
        reused = self.lab.catalog.current(TRIAL).locations[missing_key]
        self.assertEqual(reused.address.slot, original_location.address.slot)
        self.assertGreater(reused.address.generation, original_location.address.generation)
        with self.assertRaises(PageReadError):
            self.lab.pages.read(original_location, old_key)
        self.assertIsNone(self.lab.pages.read(reused, missing_key).micrometres)
        self.lab.jobs.advance(new, 2)
        self.assert_corrected_report(self.issue(new)[1])

    def test_admission_interleave(self):
        self.seed()
        at_evidence = Event()
        resume_capture = Event()
        publication_entered = Event()

        def pause_at_acquire():
            at_evidence.set()
            if not resume_capture.wait(10):
                raise AssertionError('admission fixture did not release the reader')

        with ThreadPoolExecutor(max_workers=2) as threads:
            reading = threads.submit(on_call, EvidenceStore.acquire.__code__, pause_at_acquire,
                                     lambda: self.lab.admission.admit(TRIAL))
            try:
                self.assertTrue(at_evidence.wait(10), 'admission did not reach evidence acquisition')
                self.assertTrue(self.lab.visibility._gate.locked())
                publishing = threads.submit(
                    on_call, RevisionVisibility.publishing.__wrapped__.__code__, publication_entered.set,
                    lambda: self.lab.revisions.publish(TRIAL, amendment=correction()),
                )
                self.assertTrue(publication_entered.wait(10), 'publisher did not reach the visibility boundary')
                self.assertFalse(publishing.done())
            finally:
                resume_capture.set()
            old = reading.result(timeout=10)
            self.assertEqual(publishing.result(timeout=10), 'R2')
        new = self.lab.admission.admit(TRIAL)
        self.lab.jobs.advance(old, 2)
        self.lab.jobs.advance(new, 2)
        self.assert_original_report(self.issue(old)[1])
        self.assert_corrected_report(self.issue(new)[1])

    def test_reopen_current(self):
        self.seed()
        self.lab.revisions.publish(TRIAL, amendment=correction())
        before = self.lab.catalog.current(TRIAL)
        self.lab = open_lab(self.directory)
        self.assertEqual(self.lab.catalog.current(TRIAL), before)
        self.assert_corrected_report(self.issue(self.complete())[1])
