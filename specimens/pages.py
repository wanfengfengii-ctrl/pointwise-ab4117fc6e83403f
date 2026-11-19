import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from intake.rows import RawSample, SampleKey, restore_sample, stored_reading


_PAGE_NAME = re.compile(r'slot-([1-9][0-9]*)-([1-9][0-9]*)\.json')


@dataclass(frozen=True, order=True)
class PageAddress:
    slot: int
    generation: int

    def __post_init__(self) -> None:
        if any(type(number) is not int or number < 1 for number in (self.slot, self.generation)):
            raise ValueError('slot and generation must be positive integers')


@dataclass(frozen=True)
class SampleLocation:
    address: PageAddress
    position: int

    def __post_init__(self) -> None:
        if type(self.position) is not int or self.position < 0:
            raise ValueError('page position must be a nonnegative integer')


class PageReadError(ValueError):
    pass


class SamplePageStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def initialize(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, address: PageAddress) -> Path:
        return self.directory / f'slot-{address.slot}-{address.generation}.json'

    def addresses(self) -> set[PageAddress]:
        addresses = set()
        for path in self.directory.iterdir():
            match = _PAGE_NAME.fullmatch(path.name)
            if match:
                addresses.add(PageAddress(int(match[1]), int(match[2])))
        return addresses

    def stage(self, address: PageAddress, samples: tuple[RawSample, ...]) -> tuple[SampleLocation, ...]:
        path = self.path_for(address)
        if path.exists():
            raise FileExistsError(path)
        if not samples or len({sample.key for sample in samples}) != len(samples):
            raise ValueError('a page needs distinct sample keys')
        payload = {'address': asdict(address), 'rows': [
            {'key': asdict(sample.key), 'reading': stored_reading(sample)} for sample in samples
        ]}
        temporary = None
        try:
            with NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.directory,
                                    prefix='.staging-', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return tuple(SampleLocation(address, position) for position in range(len(samples)))

    def read(self, location: SampleLocation, key: SampleKey) -> RawSample:
        try:
            with self.path_for(location.address).open(encoding='utf-8') as stream:
                payload = json.load(stream)
            if PageAddress(**payload['address']) != location.address:
                raise ValueError('page address mismatch')
            rows = payload['rows']
            if not isinstance(rows, list):
                raise ValueError('page rows must be a list')
            row = rows[location.position]
            actual_key = SampleKey(**row['key'])
            if actual_key != key:
                raise ValueError('sample identity mismatch')
            reading = row['reading']
            if not isinstance(reading, list) or len(reading) != 3:
                raise ValueError('invalid page reading')
            return restore_sample(actual_key, *reading)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            raise PageReadError(f'unreadable sample {key.original_id} at {location}') from exc

    def discard(self, address: PageAddress) -> None:
        self.path_for(address).unlink(missing_ok=True)
