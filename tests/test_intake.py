from fractions import Fraction

from demo import open_lab
from intake.rows import SampleKey
from tests.support import LabCase, TRIAL, sample


class TestIntake(LabCase):
    def test_units_and_identity(self):
        left = self.lab.importer.import_batch(TRIAL, 'left', [sample('L2', '0.008', 'mm')])
        right = self.lab.importer.import_batch(TRIAL, 'right', [sample('R2a', '7')])
        self.assertEqual(left.references, (SampleKey(TRIAL, 'left', 'L2'),))
        self.assertEqual(right.references, (SampleKey(TRIAL, 'right', 'R2a'),))
        self.assertEqual((left.samples[0].source_value, left.samples[0].unit), ('0.008', 'mm'))
        self.assertEqual(self.lab.register.get_sample(left.references[0]).micrometres, Fraction(8))
        self.assertEqual(self.lab.register.get_sample(right.references[0]).micrometres, Fraction(7))

    def test_identity_scope(self):
        for trial, side, value in [(TRIAL, 'left', 1), (TRIAL, 'right', 2), ('CP-043', 'left', 3)]:
            with self.subTest(trial=trial, side=side):
                self.lab.importer.import_batch(trial, side, [sample('A', value)])
                self.assertEqual(self.lab.register.get_sample(SampleKey(trial, side, 'A')).micrometres, value)

    def test_invalid_batch(self):
        importer = self.lab.importer
        importer.import_batch(TRIAL, 'left', [sample('existing', 6)])
        for rows in (
            [sample('new', 1), sample('existing', 9)],
            [sample('new', 1), sample('new', 2)],
            [sample('new', 1), sample('invalid', '7/8')],
            [sample('new', 1), sample('invalid', '4', 'cm')],
        ):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    importer.import_batch(TRIAL, 'left', rows)
                with self.assertRaises(KeyError):
                    self.lab.register.get_sample(SampleKey(TRIAL, 'left', 'new'))
                self.assertEqual(self.lab.register.get_sample(SampleKey(TRIAL, 'left', 'existing')).micrometres, 6)
        with self.assertRaises(ValueError):
            importer.import_batch('bad-trial', 'left', [sample('invalid', 'NaN')])
        self.assertFalse(self.lab.register.contains_trial('bad-trial'))

    def test_reopen_imports(self):
        self.seed()
        self.lab.register.initialize()
        self.lab = open_lab(self.directory)
        key = SampleKey(TRIAL, 'left', 'L2')
        restored = self.lab.register.get_sample(key)
        self.assertEqual((restored.source_value, restored.unit, restored.micrometres), ('0.008', 'mm', 8))
        with self.assertRaises(ValueError):
            self.lab.importer.import_batch(TRIAL, 'left', [sample('L2', 50)])
        self.assert_original_report(self.issue(self.complete())[1])

    def test_fractional_micrometres(self):
        batch = self.lab.importer.import_batch(TRIAL, 'left', [
            sample('millimetres', '0.0002', 'mm'), sample('micrometres', '0.2'),
        ])
        restored = [self.lab.register.get_sample(key) for key in batch.references]
        self.assertEqual([row.micrometres for row in restored], [Fraction(1, 5), Fraction(1, 5)])
        self.assertEqual([row.unit for row in restored], ['mm', 'um'])

    def test_publish_first(self):
        self.seed()
        current = self.lab.catalog.current(TRIAL)
        self.assertEqual((current.revision_id, current.parent_revision), ('R1', None))
        self.assertEqual([pair.pair_id for pair in current.pairs], ['P01', 'P02'])
        self.assertEqual(set(current.locations), {key for pair in current.pairs for key in (pair.left, pair.right)})
        for key, location in current.locations.items():
            self.assertEqual(self.lab.pages.read(location, key), self.lab.register.get_sample(key))
        self.assert_original_report(self.issue(self.complete())[1])
