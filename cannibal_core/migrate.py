from __future__ import annotations

import argparse
from pathlib import Path

from .database import run_migrations


def _sqlite_sync_url(db_path: Path) -> str:
    if db_path.is_absolute():
        return f"sqlite:////{db_path.as_posix().lstrip('/')}"
    return f"sqlite:///{db_path.as_posix()}"


def migrate(db_path: Path) -> None:
    run_migrations(sqlalchemy_url=_sqlite_sync_url(db_path))


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
    print(f"Alembic migration complete: {db_path}")


if __name__ == "__main__":
    main()
