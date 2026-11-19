from collections.abc import Iterable
from dataclasses import dataclass

from intake.rows import SampleKey, require_identifier


@dataclass(frozen=True)
class PairSpec:
    pair_id: str
    left: SampleKey
    right: SampleKey

    def __post_init__(self) -> None:
        require_identifier(self.pair_id, 'pair')
        if not isinstance(self.left, SampleKey) or not isinstance(self.right, SampleKey):
            raise ValueError('a pair needs two sample references')


def order_pairs(pairs: Iterable[PairSpec]) -> tuple[PairSpec, ...]:
    return tuple(sorted(pairs, key=lambda pair: pair.pair_id))


def validate_pairs(trial_id: str, pairs: Iterable[PairSpec]) -> tuple[PairSpec, ...]:
    require_identifier(trial_id, 'trial')
    seen = set()
    validated = []
    for pair in pairs:
        if not isinstance(pair, PairSpec):
            raise ValueError('expected a PairSpec')
        if pair.pair_id in seen:
            raise ValueError(f'duplicate pair {pair.pair_id}')
        if pair.left.trial_id != trial_id or pair.right.trial_id != trial_id:
            raise ValueError(f'pair {pair.pair_id} refers to a different trial')
        if pair.left.side != 'left' or pair.right.side != 'right':
            raise ValueError(f'pair {pair.pair_id} has a reference on the wrong side')
        seen.add(pair.pair_id)
        validated.append(pair)
    return order_pairs(validated)


def required_samples(pairs: Iterable[PairSpec]) -> set[SampleKey]:
    return {key for pair in pairs for key in (pair.left, pair.right)}
