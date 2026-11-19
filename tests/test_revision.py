import sqlite3
from contextlib import closing

from intake.rows import SampleKey
from revision.amendments import NamedAmendment, ReadingChange
from revision.pairs import PairSpec
from revision.publish import PublicationError
from tests.support import LabCase, TRIAL, correction, execute_sql, pair


class TestRevision(LabCase):
    def assert_r1_still_current(self):
        self.assertEqual(self.lab.catalog.current(TRIAL).revision_id, 'R1')
        self.assert_original_report(self.issue(self.complete())[1])

    def test_bad_reference(self):
        self.seed()
        with self.assertRaises(PublicationError):
            self.lab.revisions.publish(TRIAL, amendment=correction('unknown'))
        self.assert_r1_still_current()

    def test_wrong_side(self):
        self.seed()
        wrong_side = PairSpec('P02', SampleKey(TRIAL, 'left', 'L2'), SampleKey(TRIAL, 'left', 'L1'))
        self.assertEqual(self.lab.register.get_sample(wrong_side.right).micrometres, 10)
        with self.assertRaisesRegex(PublicationError, 'wrong side'):
            self.lab.revisions.publish(TRIAL, amendment=NamedAmendment('错侧候选', 'R1', (wrong_side,)))
        self.assert_r1_still_current()

    def test_partial_candidate(self):
        self.seed()
        before = self.lab.catalog.current(TRIAL)
        edit = NamedAmendment('两对更正', 'R1', (pair('P01', 'L1', 'R2b'), pair('P02', 'L2', 'unknown')),
                              (ReadingChange(SampleKey(TRIAL, 'left', 'L2'), 9, 'um'),))
        with self.assertRaises(PublicationError):
            self.lab.revisions.publish(TRIAL, amendment=edit)
        self.assertEqual(self.lab.catalog.current(TRIAL), before)
        self.assert_r1_still_current()

    def test_invalid_candidate(self):
        self.seed()
        pair_one = pair('P01', 'L1', 'R1a')
        pair_duplicate = pair('P01', 'L2', 'R2a')
        foreign = PairSpec('P02', SampleKey(TRIAL, 'left', 'L2'), SampleKey('other', 'right', 'R2a'))
        for amendment in (correction(parent='R0'),
                          NamedAmendment('重复配对号', 'R1', (pair_one, pair_duplicate)),
                          NamedAmendment('异批引用', 'R1', (foreign,)),
                          NamedAmendment('未登记读数', 'R1', readings=(
                              ReadingChange(SampleKey(TRIAL, 'right', 'unknown'), 4, 'um'),
                          ))):
            with self.subTest(amendment=amendment.name):
                with self.assertRaises(PublicationError):
                    self.lab.revisions.publish(TRIAL, amendment=amendment)
        self.assert_r1_still_current()

    def test_initial_candidate_failure_has_no_head(self):
        with self.assertRaises(PublicationError):
            self.lab.revisions.publish(TRIAL, [pair('P01', 'L1', 'R1a')])
        self.assertIsNone(self.lab.catalog.current(TRIAL))
        self.seed()
        with self.assertRaises(PublicationError):
            self.lab.revisions.publish(TRIAL, [pair('P01', 'L1', 'R1a')])
        self.assert_r1_still_current()

    def test_failed_publication_commit(self):
        self.seed()
        old_pages = self.lab.pages.addresses()
        database = self.lab.catalog.database
        execute_sql(database, '''
            CREATE TRIGGER reject_head_update BEFORE UPDATE ON revision_heads
            BEGIN SELECT RAISE(ABORT, 'head update rejected'); END;
        ''')
        with self.assertRaisesRegex(PublicationError, 'head update rejected'):
            self.lab.revisions.publish(TRIAL, amendment=correction())
        self.assertEqual(self.lab.pages.addresses(), old_pages)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute('SELECT number, amendment_name FROM revisions').fetchall(), [(1, None)])
        self.assert_r1_still_current()
        execute_sql(database, 'DROP TRIGGER reject_head_update;')
        edit = correction()
        self.assertEqual(self.lab.revisions.publish(TRIAL, amendment=edit), 'R2')
        self.assertEqual(self.lab.catalog.current(TRIAL).amendment_name, edit.name)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute('SELECT parent, amendment_name FROM revisions WHERE number = 2').fetchone(),
                             (1, edit.name))
