from dataclasses import dataclass
from fractions import Fraction

from analysis.paired import PairResult


@dataclass(frozen=True)
class PairTotals:
    difference_sum: Fraction = Fraction(0)
    valid_count: int = 0

    def add(self, pair: PairResult) -> 'PairTotals':
        if pair.difference is None:
            return self
        return PairTotals(self.difference_sum + pair.difference, self.valid_count + 1)

    def mean(self) -> Fraction | None:
        return self.difference_sum / self.valid_count if self.valid_count else None
