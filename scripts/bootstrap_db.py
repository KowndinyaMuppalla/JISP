"""Bootstrap JISP database by discovering and applying SQL migrations.

Usage:
    python scripts/bootstrap_db.py [--dry-run]

Environment:
    JISP_DATABASE_URL   PostgreSQL DSN (default: postgresql://jisp:jisp_secret@localhost:5432/jisp)
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("jisp.bootstrap_db")

MIGRATIONS_DIR = Path(__file__).parent.parent / "spatial" / "db" / "migrations"
DATABASE_URL = os.getenv("JISP_DATABASE_URL", "postgresql://jisp:jisp_secret@localhost:5432/jisp")
MIGRATION_NAME_RE = re.compile(r"^\d{3}_[a-z0-9_]+\.sql$")


@dataclass(frozen=True)
class Migration:
    path: Path
    name: str
    checksum: str


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def discover_migrations() -> list[Migration]:
    """Return all .sql files in MIGRATIONS_DIR, sorted lexicographically."""
    if not MIGRATIONS_DIR.is_dir():
        raise FileNotFoundError(f"Migrations directory not found: {MIGRATIONS_DIR}")

    files = sorted(
        f for f in MIGRATIONS_DIR.iterdir()
        if f.suffix == ".sql" and MIGRATION_NAME_RE.match(f.name)
    )

    return [
        Migration(path=f, name=f.name, checksum=_sha256(f.read_text(encoding="utf-8")))
        for f in files
    ]


def _ensure_schema_migrations_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name        TEXT PRIMARY KEY,
            checksum    TEXT NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.commit()


def _get_applied(conn) -> dict[str, str]:
    rows = conn.execute("SELECT name, checksum FROM schema_migrations ORDER BY name").fetchall()
    return {row[0]: row[1] for row in rows}


def apply(dry_run: bool = False) -> None:
    """Discover and apply all pending migrations in order."""
    migrations = discover_migrations()
    if not migrations:
        logger.info("No migration files found in %s", MIGRATIONS_DIR)
        return

    if dry_run:
        logger.info("DRY-RUN — migrations that would be applied:")
        for m in migrations:
            logger.info("  %s  (sha256: %s)", m.name, m.checksum[:12])
        return

    import psycopg  # lazy import — not needed for dry-run

    with psycopg.connect(DATABASE_URL, autocommit=False) as conn:
        _ensure_schema_migrations_table(conn)
        applied = _get_applied(conn)

        for migration in migrations:
            if migration.name in applied:
                stored = applied[migration.name]
                if stored != migration.checksum:
                    raise RuntimeError(
                        f"Immutability violation: {migration.name} checksum changed "
                        f"({stored[:12]}… → {migration.checksum[:12]}…). "
                        "Never modify applied migrations."
                    )
                logger.debug("Skip (already applied): %s", migration.name)
                continue

            logger.info("Applying %s …", migration.name)
            sql = migration.path.read_text(encoding="utf-8")
            conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_migrations (name, checksum) VALUES (%s, %s)",
                (migration.name, migration.checksum),
            )
            conn.commit()
            logger.info("Applied %s", migration.name)

    logger.info("Bootstrap complete — %d migrations processed.", len(migrations))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(description="Bootstrap JISP database schema")
    parser.add_argument("--dry-run", action="store_true", help="List migrations without applying")
    args = parser.parse_args()

    try:
        apply(dry_run=args.dry_run)
    except Exception as exc:
        logger.error("Bootstrap failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
