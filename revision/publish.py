import sqlite3
from collections.abc import Iterable
from types import MappingProxyType

from intake.register import IntakeRegister
from revision.amendments import NamedAmendment, build_amendment_candidate
from revision.catalog import PublishedRevision, RevisionCatalog
from revision.pairs import PairSpec, required_samples, validate_pairs
from revision.visibility import RevisionVisibility
from specimens.placement import PagePlacement
from specimens.retirement import PageRetirement


class PublicationError(ValueError):
    pass


class RevisionPublisher:
    def __init__(self, register: IntakeRegister, catalog: RevisionCatalog,
                 visibility: RevisionVisibility, placement: PagePlacement,
                 retirement: PageRetirement):
        self._register = register
        self._catalog = catalog
        self._visibility = visibility
        self._placement = placement
        self._retirement = retirement

    def initialize(self) -> None:
        with self._visibility.publishing():
            self._catalog.initialize()
            self._retirement.initialize(self._catalog.current_locations().values())
            self._retirement.reap()

    def publish(self, trial_id: str, pairs: Iterable[PairSpec] | None = None, *,
                amendment: NamedAmendment | None = None) -> str:
        if (pairs is None) == (amendment is None):
            raise PublicationError('supply an initial pair list or a named amendment')
        with self._visibility.publishing():
            try:
                return self._publish(trial_id, pairs, amendment)
            except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
                raise PublicationError(f'publication rejected: {exc}') from exc

    def _publish(self, trial_id: str, pairs: Iterable[PairSpec] | None,
                 amendment: NamedAmendment | None) -> str:
        if not self._register.contains_trial(trial_id):
            raise ValueError('unknown trial')
        current = self._catalog.current(trial_id)
        if amendment is None:
            if current is not None:
                raise ValueError('trial already has a published revision')
            pair_list = validate_pairs(trial_id, pairs)
            overrides = MappingProxyType({})
            parent_id = None
            revision_id = 'R1'
            previous_locations = {}
        else:
            if current is None or current.revision_id != amendment.parent_revision:
                raise ValueError('amendment parent must be the current revision')
            candidate = build_amendment_candidate(trial_id, current.pairs, current.overrides, amendment)
            for key in candidate.changed_samples:
                self._register.get_sample(key)
            pair_list = candidate.pairs
            overrides = candidate.overrides
            parent_id = current.revision_id
            revision_id = f'R{int(parent_id[1:]) + 1}'
            previous_locations = current.locations

        samples = {
            key: overrides[key] if key in overrides else self._register.get_sample(key)
            for key in sorted(required_samples(pair_list))
        }
        generation = self._placement.available_generation(self._catalog.next_generation())
        plan = self._placement.stage_revision(samples, previous_locations, generation)
        revision = PublishedRevision(
            trial_id, revision_id, parent_id, None if amendment is None else amendment.name,
            generation, pair_list, plan.locations, overrides,
        )
        try:
            self._catalog.commit_publication(revision, amendment)
        except BaseException:
            self._placement.abort(plan)
            raise
        self._retirement.set_current(previous_locations.values(), plan.locations.values())
        self._retirement.reap()
        return revision_id
