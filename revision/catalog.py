import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType

from intake.rows import RawSample, SampleKey, restore_sample, stored_reading
from revision.amendments import NamedAmendment
from revision.pairs import PairSpec, order_pairs
from specimens.pages import PageAddress, SampleLocation


@dataclass(frozen=True)
class PublishedRevision:
    trial_id: str
    revision_id: str
    parent_revision: str | None
    amendment_name: str | None
    generation: int
    pairs: tuple[PairSpec, ...]
    locations: Mapping[SampleKey, SampleLocation]
    overrides: Mapping[SampleKey, RawSample]


def _revision_id(number: int | None) -> str | None:
    return None if number is None else f'R{number}'


def _head(db: sqlite3.Connection, trial_id: str) -> int | None:
    row = db.execute('SELECT number FROM revision_heads WHERE trial = ?', (trial_id,)).fetchone()
    return None if row is None else row[0]


class RevisionCatalog:
    def __init__(self, database: Path):
        self.database = Path(database)

    def initialize(self) -> None:
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS revisions (
                    trial TEXT NOT NULL,
                    number INTEGER NOT NULL,
                    parent INTEGER,
                    amendment_name TEXT,
                    amendment_json TEXT,
                    generation INTEGER NOT NULL UNIQUE,
                    PRIMARY KEY (trial, number)
                );
                CREATE TABLE IF NOT EXISTS revision_heads (
                    trial TEXT PRIMARY KEY,
                    number INTEGER NOT NULL,
                    FOREIGN KEY (trial, number) REFERENCES revisions(trial, number)
                );
                CREATE TABLE IF NOT EXISTS revision_pairs (
                    trial TEXT NOT NULL, number INTEGER NOT NULL, pair_id TEXT NOT NULL,
                    left_side TEXT NOT NULL, left_id TEXT NOT NULL,
                    right_side TEXT NOT NULL, right_id TEXT NOT NULL,
                    PRIMARY KEY (trial, number, pair_id),
                    FOREIGN KEY (trial, number) REFERENCES revisions(trial, number)
                );
                CREATE TABLE IF NOT EXISTS revision_locations (
                    trial TEXT NOT NULL, number INTEGER NOT NULL,
                    side TEXT NOT NULL, original_id TEXT NOT NULL,
                    slot INTEGER NOT NULL, generation INTEGER NOT NULL, position INTEGER NOT NULL,
                    PRIMARY KEY (trial, number, side, original_id),
                    FOREIGN KEY (trial, number) REFERENCES revisions(trial, number)
                );
                CREATE TABLE IF NOT EXISTS reading_overrides (
                    trial TEXT NOT NULL, number INTEGER NOT NULL,
                    side TEXT NOT NULL, original_id TEXT NOT NULL,
                    unit TEXT, source_value TEXT, micrometres TEXT,
                    PRIMARY KEY (trial, number, side, original_id),
                    FOREIGN KEY (trial, number) REFERENCES revisions(trial, number)
                );
            ''')

    def current(self, trial_id: str) -> PublishedRevision | None:
        with closing(sqlite3.connect(self.database)) as db:
            number = _head(db, trial_id)
            if number is None:
                return None
            # The head identifies immutable rows, even if a later publication moves it.
            identity = (trial_id, number)
            parent, name, generation = db.execute('''
                SELECT parent, amendment_name, generation FROM revisions
                WHERE trial = ? AND number = ?
            ''', identity).fetchone()
            pairs = order_pairs(
                PairSpec(pair_id, SampleKey(trial_id, left_side, left_id),
                         SampleKey(trial_id, right_side, right_id))
                for pair_id, left_side, left_id, right_side, right_id in db.execute('''
                    SELECT pair_id, left_side, left_id, right_side, right_id FROM revision_pairs
                    WHERE trial = ? AND number = ?
                ''', identity)
            )
            locations = {
                SampleKey(trial_id, side, original_id): SampleLocation(PageAddress(slot, page_gen), position)
                for side, original_id, slot, page_gen, position in db.execute('''
                    SELECT side, original_id, slot, generation, position FROM revision_locations
                    WHERE trial = ? AND number = ?
                ''', identity)
            }
            overrides = {}
            for side, original_id, unit, source, value in db.execute('''
                SELECT side, original_id, unit, source_value, micrometres FROM reading_overrides
                WHERE trial = ? AND number = ?
            ''', identity):
                key = SampleKey(trial_id, side, original_id)
                overrides[key] = restore_sample(key, unit, source, value)
        return PublishedRevision(
            trial_id, f'R{number}', _revision_id(parent), name, generation, pairs,
            MappingProxyType(locations), MappingProxyType(overrides),
        )

    def current_locations(self) -> dict[SampleKey, SampleLocation]:
        with closing(sqlite3.connect(self.database)) as db:
            rows = db.execute('''
                SELECT l.trial, l.side, l.original_id, l.slot, l.generation, l.position
                FROM revision_locations AS l
                JOIN revision_heads AS h ON h.trial = l.trial AND h.number = l.number
            ''')
            return {
                SampleKey(trial, side, original_id): SampleLocation(PageAddress(slot, generation), position)
                for trial, side, original_id, slot, generation, position in rows
            }

    def next_generation(self) -> int:
        with closing(sqlite3.connect(self.database)) as db:
            return db.execute('SELECT COALESCE(MAX(generation), 0) + 1 FROM revisions').fetchone()[0]

    def commit_publication(self, revision: PublishedRevision, amendment: NamedAmendment | None) -> None:
        trial = revision.trial_id
        record = None if amendment is None else json.dumps(asdict(amendment), ensure_ascii=False)
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys = ON')
            try:
                db.execute('BEGIN IMMEDIATE')
                parent = _head(db, trial)
                number = (parent or 0) + 1
                if revision.parent_revision != _revision_id(parent) or revision.revision_id != f'R{number}':
                    raise ValueError('publication parent is no longer current')
                db.execute('INSERT INTO revisions VALUES (?, ?, ?, ?, ?, ?)', (
                    trial, number, parent, revision.amendment_name, record, revision.generation,
                ))
                db.executemany('INSERT INTO revision_pairs VALUES (?, ?, ?, ?, ?, ?, ?)', (
                    (trial, number, pair.pair_id, pair.left.side, pair.left.original_id,
                     pair.right.side, pair.right.original_id)
                    for pair in revision.pairs
                ))
                db.executemany('INSERT INTO revision_locations VALUES (?, ?, ?, ?, ?, ?, ?)', (
                    (trial, number, key.side, key.original_id, location.address.slot,
                     location.address.generation, location.position)
                    for key, location in revision.locations.items()
                ))
                db.executemany('INSERT INTO reading_overrides VALUES (?, ?, ?, ?, ?, ?, ?)', (
                    (trial, number, key.side, key.original_id, *stored_reading(sample))
                    for key, sample in revision.overrides.items()
                ))
                db.execute('''
                    INSERT INTO revision_heads VALUES (?, ?)
                    ON CONFLICT(trial) DO UPDATE SET number = excluded.number
                ''', (trial, number))
                db.commit()
            except BaseException:
                db.rollback()
                raise
