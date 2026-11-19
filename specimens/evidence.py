from collections.abc import Mapping
from threading import Lock
from types import MappingProxyType

from intake.rows import RawSample, SampleKey
from specimens.pages import PageReadError, SampleLocation, SamplePageStore
from specimens.retirement import PageRetirement


class EvidenceLease:
    def __init__(self, pages: SamplePageStore, locations: Mapping[SampleKey, SampleLocation],
                 retirement: PageRetirement):
        self._pages = pages
        self._locations = MappingProxyType(dict(locations))
        self._retirement = retirement
        self._open = True
        self._lock = Lock()

    def read(self, key: SampleKey) -> RawSample:
        with self._lock:
            if not self._open:
                raise PageReadError('sample evidence has been released')
            if key not in self._locations:
                raise PageReadError('sample is absent from the accepted evidence')
            return self._pages.read(self._locations[key], key)

    def close(self) -> None:
        with self._lock:
            if not self._open:
                return
            self._open = False
            addresses = {location.address for location in self._locations.values()}
        self._retirement.release(addresses)


class EvidenceStore:
    def __init__(self, pages: SamplePageStore, retirement: PageRetirement):
        self._pages = pages
        self._retirement = retirement

    def acquire(self, locations: Mapping[SampleKey, SampleLocation]) -> EvidenceLease:
        addresses = frozenset(location.address for location in locations.values())
        if not self._retirement.is_current(addresses):
            raise PageReadError("sample page is not in the current publication")
        self._retirement.hold(addresses)
        lease = EvidenceLease(self._pages, locations, self._retirement)
        try:
            for key in lease._locations:
                lease.read(key)
        except BaseException:
            lease.close()
            raise
        return lease
