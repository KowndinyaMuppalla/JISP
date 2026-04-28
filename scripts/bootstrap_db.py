"""Apply JISP database migrations in order.

Reads ``spatial/db/migrations/*.sql`` lexicographically and executes
each file as a single statement batch against the configured database.

Usage
-----
    # explicit DSN
    python -m scripts.bootstrap_db --dsn postgresql://jisp:jisp@localhost:5432/jisp

    # or via environment
    JISP_DATABASE_URL=postgresql://... python -m scripts.bootstrap_db

    # dry run — print files that would be applied, without connecting
    python -m scripts.bootstrap_db --dry-run

The runner records applied migrations in a ``schema_migrations`` table
and skips any file whose checksum already matches a recorded entry.
A file whose checksum has changed since it was applied is treated as
an error: migration files are immutable once shipped.

Strict scope: this module is the only Python entry that touches the
DB schema. Nothing here imports the API, GeoAI, or reasoning layers.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("jisp.bootstrap_db")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "spatial" / "db" / "migrations"

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename     TEXT PRIMARY KEY,
    checksum     TEXT NOT NULL,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


@dataclass(frozen=True)
class Migration:
    """A single migration file on disk."""

    path: Path
    checksum: str

    @property
    def filename(self) -> str:
        return self.path.name

    def read_sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Return migrations sorted by filename.

    Raises:
        FileNotFoundError: if the migrations directory is missing.
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"Migrations directory not found: {directory}")

    sql_files = sorted(p for p in directory.iterdir() if p.suffix.lower() == ".sql")
    return [
        Migration(path=p, checksum=_checksum(p.read_bytes()))
        for p in sql_files
    ]


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _resolve_dsn(cli_dsn: str | None) -> str:
    if cli_dsn:
        return cli_dsn
    env = os.environ.get("JISP_DATABASE_URL")
    if env:
        return env
    raise SystemExit(
        "No database DSN provided. Pass --dsn or set JISP_DATABASE_URL."
    )


def _print_plan(migrations: Iterable[Migration]) -> None:
    print("JISP migrations (lexicographic order):")
    for m in migrations:
        print(f"  {m.filename}  sha256={m.checksum[:12]}…")


def apply(dsn: str, migrations: list[Migration]) -> list[str]:
    """Apply all pending migrations. Returns the list of filenames applied."""

    # Imported lazily so `--dry-run` works on machines without psycopg installed.
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on env
        raise SystemExit(
            "psycopg (v3) is required to apply migrations. "
            "Install with: pip install 'psycopg[binary]>=3.1'"
        ) from exc

    applied: list[str] = []
    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_MIGRATIONS_DDL)
            conn.commit()

            cur.execute("SELECT filename, checksum FROM schema_migrations")
            recorded = {row[0]: row[1] for row in cur.fetchall()}

        for migration in migrations:
            previous = recorded.get(migration.filename)
            if previous == migration.checksum:
                logger.info("skip %s (already applied)", migration.filename)
                continue
            if previous is not None and previous != migration.checksum:
                raise RuntimeError(
                    f"Checksum mismatch for {migration.filename}: "
                    f"recorded={previous[:12]}… current={migration.checksum[:12]}… "
                    "Migration files are immutable once shipped."
                )

            logger.info("apply %s", migration.filename)
            sql = migration.read_sql()
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)",
                    (migration.filename, migration.checksum),
                )
            conn.commit()
            applied.append(migration.filename)

    return applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply JISP database migrations.")
    parser.add_argument(
        "--dsn",
        help="PostgreSQL DSN. Defaults to $JISP_DATABASE_URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the migrations that would be applied, then exit.",
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=MIGRATIONS_DIR,
        help="Override migrations directory (default: spatial/db/migrations).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    migrations = discover_migrations(args.migrations_dir)
    if not migrations:
        print(f"No migrations found in {args.migrations_dir}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_plan(migrations)
        return 0

    dsn = _resolve_dsn(args.dsn)
    applied = apply(dsn, migrations)
    if applied:
        print(f"Applied {len(applied)} migration(s):")
        for name in applied:
            print(f"  + {name}")
    else:
        print("No new migrations to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
