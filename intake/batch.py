from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from intake.rows import RawSample, SampleKey, parse_sample_row, require_identifier, require_side


@dataclass(frozen=True)
class TrialBatch:
    trial_id: str
    side: str
    samples: tuple[RawSample, ...]

    @property
    def references(self) -> tuple[SampleKey, ...]:
        return tuple(sample.key for sample in self.samples)


def build_trial_batch(trial_id: str, side: str, rows: Iterable[Mapping]) -> TrialBatch:
    require_identifier(trial_id, 'trial')
    require_side(side)
    samples = tuple(parse_sample_row(trial_id, side, row) for row in rows)
    if not samples:
        raise ValueError('an import needs at least one sample')
    if len({sample.key for sample in samples}) != len(samples):
        raise ValueError('duplicate sample in import')
    return TrialBatch(trial_id, side, samples)
