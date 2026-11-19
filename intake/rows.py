from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from intake.units import MICROMETRE_FACTORS, to_micrometres


def require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError(f'{label} must be a nonblank identifier')
    value.encode('utf-8')


def require_side(side: str) -> None:
    if side not in ('left', 'right'):
        raise ValueError('side must be left or right')


@dataclass(frozen=True, order=True)
class SampleKey:
    trial_id: str
    side: str
    original_id: str

    def __post_init__(self) -> None:
        require_identifier(self.trial_id, 'trial')
        require_side(self.side)
        require_identifier(self.original_id, 'sample')


@dataclass(frozen=True)
class RawSample:
    key: SampleKey
    unit: str | None
    source_value: str | None
    micrometres: Fraction | None


def parse_sample_row(trial_id: str, side: str, row: Mapping) -> RawSample:
    if not isinstance(row, Mapping) or 'original_id' not in row or 'value' not in row:
        raise ValueError('each sample needs original_id and value')
    key = SampleKey(trial_id, side, row['original_id'])
    unit = row.get('unit')
    value = row['value']
    if value is None:
        if unit is not None and (not isinstance(unit, str) or unit not in MICROMETRE_FACTORS):
            raise ValueError('unsupported thickness unit')
        return RawSample(key, unit, None, None)
    normalised = to_micrometres(value, unit)
    return RawSample(key, unit, str(value), normalised)


def restore_sample(key: SampleKey, unit: str | None, source: str | None,
                   micrometres: str | None) -> RawSample:
    if source is not None and not isinstance(source, str):
        raise ValueError('invalid stored source value')
    sample = parse_sample_row(key.trial_id, key.side, {
        'original_id': key.original_id,
        'unit': unit,
        'value': source,
    })
    expected = None if sample.micrometres is None else str(sample.micrometres)
    if micrometres != expected:
        raise ValueError('stored thickness disagrees with its source value')
    return sample


def stored_reading(sample: RawSample) -> tuple[str | None, str | None, str | None]:
    value = None if sample.micrometres is None else str(sample.micrometres)
    return sample.unit, sample.source_value, value
