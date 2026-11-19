from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock

from revision.catalog import RevisionCatalog
from revision.pairs import PairSpec, required_samples
from specimens.evidence import EvidenceLease, EvidenceStore


@dataclass(frozen=True)
class PublishedInput:
    trial_id: str
    revision_id: str
    pairs: tuple[PairSpec, ...]
    evidence: EvidenceLease


class RevisionVisibility:
    def __init__(self, catalog: RevisionCatalog, evidence: EvidenceStore):
        self._catalog = catalog
        self._evidence = evidence
        self._gate = Lock()

    @contextmanager
    def publishing(self):
        with self._gate:
            yield

    def capture(self, trial_id: str) -> PublishedInput:
        with self._gate:
            current = self._catalog.current(trial_id)
            if current is None:
                raise LookupError(f'no published revision for {trial_id}')
            locations = {key: current.locations[key] for key in sorted(required_samples(current.pairs))}
            evidence = self._evidence.acquire(locations)
            return PublishedInput(trial_id, current.revision_id, current.pairs, evidence)
