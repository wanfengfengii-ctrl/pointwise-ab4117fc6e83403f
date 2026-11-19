from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from intake.rows import RawSample, SampleKey, parse_sample_row, require_identifier
from revision.pairs import PairSpec, validate_pairs


@dataclass(frozen=True)
class ReadingChange:
    key: SampleKey
    value: str | int | None
    unit: str | None = None


@dataclass(frozen=True)
class NamedAmendment:
    name: str
    parent_revision: str
    pairs: tuple[PairSpec, ...] = ()
    readings: tuple[ReadingChange, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.name, 'amendment')
        require_identifier(self.parent_revision, 'parent revision')
        object.__setattr__(self, 'pairs', tuple(self.pairs))
        object.__setattr__(self, 'readings', tuple(self.readings))
        if not self.pairs and not self.readings:
            raise ValueError('an amendment needs an edit')


@dataclass(frozen=True)
class AmendmentCandidate:
    pairs: tuple[PairSpec, ...]
    overrides: Mapping[SampleKey, RawSample]
    changed_samples: tuple[SampleKey, ...]


def build_amendment_candidate(
    trial_id: str,
    current_pairs: tuple[PairSpec, ...],
    current_overrides: Mapping[SampleKey, RawSample],
    amendment: NamedAmendment,
) -> AmendmentCandidate:
    by_id = {pair.pair_id: pair for pair in current_pairs}
    for pair in validate_pairs(trial_id, amendment.pairs):
        by_id[pair.pair_id] = pair

    overrides = dict(current_overrides)
    changed = set()
    for edit in amendment.readings:
        if not isinstance(edit, ReadingChange) or not isinstance(edit.key, SampleKey):
            raise ValueError('expected a reading change with a sample key')
        if edit.key.trial_id != trial_id or edit.key in changed:
            raise ValueError('duplicate reading change or different trial')
        overrides[edit.key] = parse_sample_row(trial_id, edit.key.side, {
            'original_id': edit.key.original_id,
            'value': edit.value,
            'unit': edit.unit,
        })
        changed.add(edit.key)
    return AmendmentCandidate(
        validate_pairs(trial_id, by_id.values()), MappingProxyType(overrides), tuple(sorted(changed)),
    )
