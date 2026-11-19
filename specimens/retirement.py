from collections.abc import Iterable, Set
from threading import Lock

from specimens.pages import PageAddress, SampleLocation, SamplePageStore


class PageRetirement:
    def __init__(self, pages: SamplePageStore):
        self._pages = pages
        self._lock = Lock()
        self._current: set[PageAddress] = set()
        self._retired: set[PageAddress] = set()
        # Pages leased by accepted jobs must outlive their revision and keep their slots reserved.
        self._holders: dict[PageAddress, int] = {}

    def initialize(self, locations: Iterable[SampleLocation]) -> None:
        with self._lock:
            self._pages.initialize()
            current = {location.address for location in locations}
            self._retired.update(self._pages.addresses() - current)
            self._retired.difference_update(current)
            self._current = current

    def reuse_candidate(self, detaching: Set[PageAddress], reserved_slots: Set[int]) -> int:
        with self._lock:
            used = {address.slot for address in self._current - detaching}
            used.update(reserved_slots)
            # A page leased by an accepted job keeps its slot until that job finishes,
            # even after a newer revision has stopped referencing it.
            used.update(address.slot for address in self._holders)
            slot = 1
            while slot in used:
                slot += 1
            return slot

    def set_current(self, previous: Iterable[SampleLocation], new: Iterable[SampleLocation]) -> None:
        old_addresses = {location.address for location in previous}
        new_addresses = {location.address for location in new}
        with self._lock:
            self._current.difference_update(old_addresses)
            self._current.update(new_addresses)
            self._retired.update(old_addresses - new_addresses)
            self._retired.difference_update(new_addresses)

    def is_current(self, addresses: Set[PageAddress]) -> bool:
        with self._lock:
            return addresses <= self._current

    def hold(self, addresses: Iterable[PageAddress]) -> None:
        with self._lock:
            for address in addresses:
                self._holders[address] = self._holders.get(address, 0) + 1

    def release(self, addresses: Iterable[PageAddress]) -> None:
        with self._lock:
            for address in addresses:
                count = self._holders.get(address, 0) - 1
                if count > 0:
                    self._holders[address] = count
                else:
                    self._holders.pop(address, None)
            self._reap_locked()

    def abandon(self, addresses: Iterable[PageAddress]) -> None:
        with self._lock:
            self._retired.update(addresses)
            self._reap_locked()

    def reap(self) -> None:
        with self._lock:
            self._reap_locked()

    def _reap_locked(self) -> None:
        obsolete = self._retired.difference(self._current).difference(self._holders)
        for address in sorted(obsolete):
            try:
                self._pages.discard(address)
            except OSError:
                continue
            self._retired.remove(address)
