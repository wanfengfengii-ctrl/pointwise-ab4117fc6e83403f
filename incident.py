"""Reconcile the signed reports from the two jobs in the correction incident."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from demo import load_sample, open_lab, sample_pairs, seed_example, summary
from revision.amendments import NamedAmendment


def run_incident(directory: Path) -> int:
    lab = open_lab(directory)
    source, first_revision = seed_example(lab)
    trial = source['trial_id']
    old_job = lab.admission.admit(trial)
    first = lab.jobs.advance(old_job, 1)
    if (first_revision, first.revision_id, first.processed, first.done) != ('R1', 'R1', 1, False):
        raise AssertionError('expected a pending R1 job after its first pair')
    if [(row.pair_id, row.difference) for row in first.batch] != [('P01', 3)]:
        raise AssertionError('expected P01 to yield 3 micrometres before the correction')

    edit = load_sample('correction.json')
    second_revision = lab.revisions.publish(trial, amendment=NamedAmendment(
        edit['name'], edit['parent_revision'], sample_pairs(trial, edit['pairs']),
    ))
    if second_revision != 'R2':
        raise AssertionError('expected the correction to publish R2')
    new_job = lab.admission.admit(trial)
    new_first = lab.jobs.advance(new_job, 1)
    if (new_first.revision_id, new_first.processed, new_first.done) != ('R2', 1, False):
        raise AssertionError('expected R2 to start while R1 is pending')
    lab.jobs.advance(old_job, 1)
    lab.jobs.advance(new_job, 1)
    receipts = [lab.reports.issue(job) for job in (old_job, new_job)]
    reopened = open_lab(directory)
    actual = [summary(reopened.reports.read(receipt.report_id)) for receipt in receipts]
    expected = [
        {'revision': 'R1', 'pairs': [
            ['P01', 'L1', 'R1a', '10', '7', [], '3'],
            ['P02', 'L2', 'R2a', '8', '7', [], '1'],
        ], 'valid_count': 2, 'mean': '2'},
        {'revision': 'R2', 'pairs': [
            ['P01', 'L1', 'R1a', '10', '7', [], '3'],
            ['P02', 'L2', 'R2b', '8', '12', [], '-4'],
        ], 'valid_count': 2, 'mean': '-1/2'},
    ]
    print(json.dumps({'expected': expected, 'actual': actual}, ensure_ascii=False))
    if actual == [dict(expected[1], revision='R1'), expected[1]]:
        print('PAIR_REVISION_MIX: R1 signed R2b with difference -4 and mean -1/2')
    return int(actual != expected)


if __name__ == '__main__':
    with TemporaryDirectory(prefix='coating-lab-incident-') as temporary:
        raise SystemExit(run_incident(Path(temporary)))
