from dataclasses import dataclass
from fractions import Fraction

from intake.rows import RawSample, SampleKey
from revision.pairs import PairSpec


@dataclass(frozen=True)
class PairResult:
    pair_id: str
    left: SampleKey
    right: SampleKey
    left_um: Fraction | None
    right_um: Fraction | None
    missing: tuple[str, ...]
    difference: Fraction | None


def evaluate_pair(pair: PairSpec, left: RawSample, right: RawSample) -> PairResult:
    if left.key != pair.left or right.key != pair.right:
        raise ValueError(f'sample evidence does not match {pair.pair_id}')
    left_um = left.micrometres
    right_um = right.micrometres
    missing = tuple(side for side, value in (('left', left_um), ('right', right_um)) if value is None)
    difference = None if left_um is None or right_um is None else left_um - right_um
    return PairResult(pair.pair_id, left.key, right.key, left_um, right_um, missing, difference)
