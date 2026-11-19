import sqlite3
from contextlib import closing
from pathlib import Path

from intake.batch import TrialBatch
from intake.rows import RawSample, SampleKey, restore_sample, stored_reading


class IntakeRegister:
    def __init__(self, database: Path):
        self.database = Path(database)

    def initialize(self) -> None:
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS trials (
                    trial TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS raw_samples (
                    trial TEXT NOT NULL REFERENCES trials(trial),
                    side TEXT NOT NULL CHECK (side IN ('left', 'right')),
                    original_id TEXT NOT NULL,
                    unit TEXT,
                    source_value TEXT,
                    micrometres TEXT,
                    PRIMARY KEY (trial, side, original_id)
                );
            ''')

    def record_batch(self, batch: TrialBatch) -> None:
        rows = [
            (sample.key.trial_id, sample.key.side, sample.key.original_id, *stored_reading(sample))
            for sample in batch.samples
        ]
        if not rows or any(row[:2] != (batch.trial_id, batch.side) for row in rows):
            raise ValueError('samples must belong to the imported trial and side')
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys = ON')
            try:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT OR IGNORE INTO trials VALUES (?)', (batch.trial_id,))
                db.executemany('INSERT INTO raw_samples VALUES (?, ?, ?, ?, ?, ?)', rows)
                db.commit()
            except sqlite3.IntegrityError as exc:
                db.rollback()
                raise ValueError('sample already registered or invalid') from exc
            except BaseException:
                db.rollback()
                raise

    def contains_trial(self, trial_id: str) -> bool:
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute('SELECT 1 FROM trials WHERE trial = ?', (trial_id,)).fetchone()
        return row is not None

    def get_sample(self, key: SampleKey) -> RawSample:
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute('''
                SELECT unit, source_value, micrometres FROM raw_samples
                WHERE trial = ? AND side = ? AND original_id = ?
            ''', (key.trial_id, key.side, key.original_id)).fetchone()
        if row is None:
            raise KeyError(key)
        return restore_sample(key, *row)
