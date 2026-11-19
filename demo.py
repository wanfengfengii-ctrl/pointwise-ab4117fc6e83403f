import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.admission import AnalysisAdmission
from analysis.jobs import CompletedJob, JobStore
from intake.admission import BatchImporter
from intake.register import IntakeRegister
from intake.rows import SampleKey
from reports.detail import ReportDetail
from reports.publish import ReportPublisher
from reports.store import ReportStore
from revision.amendments import NamedAmendment
from revision.catalog import RevisionCatalog
from revision.pairs import PairSpec
from revision.publish import RevisionPublisher
from revision.visibility import RevisionVisibility
from specimens.evidence import EvidenceStore
from specimens.pages import SamplePageStore
from specimens.placement import PagePlacement
from specimens.retirement import PageRetirement


@dataclass(frozen=True)
class Lab:
    importer: BatchImporter
    register: IntakeRegister
    revisions: RevisionPublisher
    catalog: RevisionCatalog
    visibility: RevisionVisibility
    pages: SamplePageStore
    admission: AnalysisAdmission
    jobs: JobStore
    reports: ReportPublisher
    report_store: ReportStore


def open_lab(directory: Path) -> Lab:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    register = IntakeRegister(directory / 'intake.sqlite3')
    catalog = RevisionCatalog(directory / 'revisions.sqlite3')
    pages = SamplePageStore(directory / 'sample-pages')
    retirement = PageRetirement(pages)
    visibility = RevisionVisibility(catalog, EvidenceStore(pages, retirement))
    revisions = RevisionPublisher(register, catalog, visibility, PagePlacement(pages, retirement), retirement)
    jobs = JobStore()
    report_store = ReportStore(directory / 'reports.sqlite3')
    register.initialize()
    revisions.initialize()
    report_store.initialize()
    return Lab(BatchImporter(register), register, revisions, catalog, visibility, pages,
               AnalysisAdmission(visibility, jobs), jobs, ReportPublisher(jobs, report_store), report_store)


def load_sample(filename: str) -> dict:
    directory = Path(__file__).resolve().parent / 'samples'
    with (directory / filename).open(encoding='utf-8') as stream:
        return json.load(stream)


def sample_pairs(trial_id: str, rows: list[dict]) -> tuple[PairSpec, ...]:
    return tuple(
        PairSpec(row['pair_id'], SampleKey(trial_id, 'left', row['left']),
                 SampleKey(trial_id, 'right', row['right']))
        for row in rows
    )


def seed_example(lab: Lab) -> tuple[dict, str]:
    source = load_sample('trial.json')
    trial = source['trial_id']
    for side in ('left', 'right'):
        lab.importer.import_batch(trial, side, source[side])
    revision = lab.revisions.publish(trial, sample_pairs(trial, source['pairs']))
    return source, revision


def _quantity(value: Fraction | None) -> str | None:
    return None if value is None else str(value)


def summary(result: CompletedJob | ReportDetail) -> dict:
    return {
        'revision': result.revision_id,
        'pairs': [
            [row.pair_id, row.left.original_id, row.right.original_id, _quantity(row.left_um),
             _quantity(row.right_um), list(row.missing), _quantity(row.difference)]
            for row in result.results
        ],
        'valid_count': result.valid_count,
        'mean': _quantity(result.mean),
    }


def run_demo(directory: Path) -> None:
    lab = open_lab(directory)
    source, first_revision = seed_example(lab)
    trial = source['trial_id']
    old_job = lab.admission.admit(trial)
    first_batch = lab.jobs.advance(old_job, 1)
    edit = load_sample('correction.json')
    second_revision = lab.revisions.publish(trial, amendment=NamedAmendment(
        edit['name'], edit['parent_revision'], sample_pairs(trial, edit['pairs']),
    ))
    new_job = lab.admission.admit(trial)
    lab.jobs.advance(old_job, 1)
    lab.jobs.advance(new_job, 2)
    receipts = [lab.reports.issue(job) for job in (old_job, new_job)]
    reopened = open_lab(directory)
    actual = [summary(lab.jobs.completed(job)) for job in (old_job, new_job)]
    read_back = [summary(reopened.reports.read(receipt.report_id)) for receipt in receipts]
    expected = [
        {'revision': 'R1', 'pairs': [
            ['P01', 'L1', 'R1a', '10', '7', [], '3'], ['P02', 'L2', 'R2a', '8', '7', [], '1'],
        ], 'valid_count': 2, 'mean': '2'},
        {'revision': 'R2', 'pairs': [
            ['P01', 'L1', 'R1a', '10', '7', [], '3'], ['P02', 'L2', 'R2b', '8', '12', [], '-4'],
        ], 'valid_count': 2, 'mean': '-1/2'},
    ]
    if (first_revision, second_revision, first_batch.done) != ('R1', 'R2', False):
        raise AssertionError('the correction must occur between the old job batches')
    if tuple(row.difference for row in first_batch.batch) != (Fraction(3),):
        raise AssertionError('the first batch must contain the original first pair')
    if actual != expected or read_back != expected:
        raise AssertionError(f'analysis and report reconciliation differ: {actual!r}, {read_back!r}')
    for receipt, result in zip(receipts, read_back, strict=True):
        differences = [pair[-1] for pair in result['pairs']]
        print(f'{receipt.report_id} {result["revision"]} {differences} mean={result["mean"]} µm')
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'V6',
        'input': {'trial': source, 'correction': edit, 'old_batches': [1, 1], 'new_batches': [2]},
        'expected': expected,
        'actual': actual,
        'downstream_expected': expected,
        'downstream_actual': read_back,
        'code_paths': ['revision/publish.py', 'revision/visibility.py', 'specimens/evidence.py',
                       'analysis/jobs.py', 'reports/store.py'],
        'oracle': '手算 10−7、8−7、8−12，按每版两条有效差求均值，再按签发号领取核对原号。',
    }, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    with TemporaryDirectory(prefix='coating-lab-demo-') as temporary:
        run_demo(Path(temporary))
