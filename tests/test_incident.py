import unittest

from incident import run_incident
from tests.support import LabCase


class TestIncident(LabCase):
    def test_signed_reports_keep_their_own_revision(self):
        # The full incident reconciliation: R1 must stay [3, 1] with mean 2 and
        # R2 must carry [3, -4] with mean -1/2, both read back by report number.
        self.assertEqual(run_incident(self.directory), 0)


if __name__ == '__main__':
    unittest.main()
