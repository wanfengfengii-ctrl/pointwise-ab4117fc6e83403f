from collections.abc import Iterable, Mapping

from intake.batch import TrialBatch, build_trial_batch
from intake.register import IntakeRegister


class BatchImporter:
    def __init__(self, register: IntakeRegister):
        self._register = register

    def import_batch(self, trial_id: str, side: str, rows: Iterable[Mapping]) -> TrialBatch:
        batch = build_trial_batch(trial_id, side, rows)
        self._register.record_batch(batch)
        return batch
