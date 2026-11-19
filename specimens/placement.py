from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from intake.rows import RawSample, SampleKey
from specimens.pages import PageAddress, PageReadError, SampleLocation, SamplePageStore
from specimens.retirement import PageRetirement


@dataclass(frozen=True)
class PlacementPlan:
    locations: Mapping[SampleKey, SampleLocation]
    staged: frozenset[PageAddress]


class PagePlacement:
    def __init__(self, pages: SamplePageStore, retirement: PageRetirement):
        self._pages = pages
        self._retirement = retirement

    def available_generation(self, minimum: int) -> int:
        on_disk = max((address.generation for address in self._pages.addresses()), default=0)
        return max(minimum, on_disk + 1)

    def stage_revision(self, samples: Mapping[SampleKey, RawSample],
                       previous: Mapping[SampleKey, SampleLocation], generation: int) -> PlacementPlan:
        locations = {}
        changed = []
        for key, sample in sorted(samples.items()):
            location = previous.get(key)
            if location is not None and self._matches(location, key, sample):
                locations[key] = location
            else:
                changed.append(sample)

        retained = {location.address for location in locations.values()}
        detaching = {location.address for location in previous.values()} - retained
        reserved_slots = {address.slot for address in retained}
        staged = set()
        try:
            for sample in changed:
                slot = self._retirement.reuse_candidate(detaching, reserved_slots)
                address = PageAddress(slot, generation)
                # Keeping independently corrected samples on separate pages makes their reuse independent.
                location, = self._pages.stage(address, (sample,))
                staged.add(address)
                reserved_slots.add(slot)
                if self._pages.read(location, sample.key) != sample:
                    raise PageReadError('candidate page does not match the effective reading')
                locations[sample.key] = location
        except BaseException:
            self._retirement.abandon(staged)
            raise
        return PlacementPlan(MappingProxyType(locations), frozenset(staged))

    def _matches(self, location: SampleLocation, key: SampleKey, sample: RawSample) -> bool:
        try:
            return self._pages.read(location, key) == sample
        except PageReadError:
            return False

    def abort(self, plan: PlacementPlan) -> None:
        self._retirement.abandon(plan.staged)
