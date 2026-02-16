from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


NEW_COLUMNS: dict[str, str] = {
    "rewritten_text": "TEXT",
    "is_duplicate": "INTEGER NOT NULL DEFAULT 0",
    "similarity": "REAL",
    "duplicate_of": "TEXT",
    "processed_at": "TEXT",
}


def _existing_columns(cursor: sqlite3.Cursor, table: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def migrate(db_path: Path) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path.as_posix()) as conn:
        cursor = conn.cursor()
        tables = {
            row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "posts" not in tables:
            raise RuntimeError("Table 'posts' not found. Create DB first.")

        existing = _existing_columns(cursor, "posts")
        for name, ddl in NEW_COLUMNS.items():
            if name in existing:
                continue
            cursor.execute(f"ALTER TABLE posts ADD COLUMN {name} {ddl}")

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_posts_processed_at ON posts (processed_at)"
        )
        conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate cannibal.db schema.")
    parser.add_argument(
        "--db",
        default="./cannibal.db",
        help="Path to sqlite database.",
    )
    args = parser.parse_args()
    db_path = Path(args.db).expanduser().resolve()
    migrate(db_path)
    print(f"Migration complete: {db_path}")


if __name__ == "__main__":
    main()
