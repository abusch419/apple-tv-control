import sqlite3
from datetime import date

SCHEMA = """CREATE TABLE IF NOT EXISTS watched (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    year INTEGER,
    source TEXT,
    watched_on TEXT NOT NULL,
    rating TEXT CHECK (rating IN ('liked', 'disliked')),
    notes TEXT
)"""


def connect(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute(SCHEMA)
    return db


def add(db: sqlite3.Connection, title: str, year=None, source=None, watched_on: str | None = None, notes: str | None = None) -> int:
    with db:
        cur = db.execute(
            "INSERT INTO watched (title, year, source, watched_on, notes) VALUES (?, ?, ?, ?, ?)",
            (title, year, source, watched_on or date.today().isoformat(), notes),
        )
    return cur.lastrowid


def rate(db: sqlite3.Connection, row_id: int, rating: str | None, notes: str | None = None) -> None:
    if rating not in ("liked", "disliked", None):
        raise ValueError("rating must be 'liked', 'disliked' or empty")
    with db:
        db.execute("UPDATE watched SET rating = ?, notes = COALESCE(?, notes) WHERE id = ?", (rating, notes, row_id))


def recent(db: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = db.execute("SELECT * FROM watched ORDER BY watched_on DESC, id DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]
