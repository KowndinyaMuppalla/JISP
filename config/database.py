"""
JISP Database Configuration & Connection Management

Provides PostgreSQL connection pooling, health checks, and schema initialization.
Integrates with TimescaleDB for time-series audit logging.

Environment Variables:
  JISP_DB_HOST       : PostgreSQL hostname (default: localhost)
  JISP_DB_PORT       : PostgreSQL port (default: 5432)
  JISP_DB_NAME       : Database name (default: jisp)
  JISP_DB_USER       : PostgreSQL user (default: postgres)
  JISP_DB_PASSWORD   : PostgreSQL password (default: postgres)
  JISP_DB_POOL_SIZE  : Connection pool size (default: 10)
  JISP_DB_ECHO_SQL   : Log all SQL statements (default: False)
"""

import os
import logging
from typing import Optional
from sqlalchemy import create_engine, text, event, pool
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """PostgreSQL + TimescaleDB connection configuration."""

    def __init__(self):
        self.host = os.getenv("JISP_DB_HOST", "localhost")
        self.port = int(os.getenv("JISP_DB_PORT", "5432"))
        self.database = os.getenv("JISP_DB_NAME", "jisp")
        self.user = os.getenv("JISP_DB_USER", "postgres")
        self.password = os.getenv("JISP_DB_PASSWORD", "postgres")
        self.pool_size = int(os.getenv("JISP_DB_POOL_SIZE", "10"))
        self.echo_sql = os.getenv("JISP_DB_ECHO_SQL", "False").lower() == "true"

    @property
    def url(self) -> str:
        """PostgreSQL connection string."""
        return (
            f"postgresql://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.database}"
        )

    def __repr__(self) -> str:
        return (
            f"DatabaseConfig(host={self.host}, port={self.port}, "
            f"database={self.database}, user={self.user})"
        )


class DatabaseManager:
    """Manages PostgreSQL connection pool and session lifecycle."""

    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or DatabaseConfig()
        self.engine = None
        self.SessionLocal = None
        self._initialize()

    def _initialize(self):
        """Create connection pool and session factory."""
        try:
            self.engine = create_engine(
                self.config.url,
                poolclass=pool.QueuePool,
                pool_size=self.config.pool_size,
                max_overflow=20,
                pool_pre_ping=True,  # Verify connections before use
                echo=self.config.echo_sql,
                connect_args={"connect_timeout": 10},
            )
            self.SessionLocal = sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
            )
            logger.info(
                f"Database pool initialized: {self.config.database} "
                f"(pool_size={self.config.pool_size})"
            )
        except SQLAlchemyError as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise

    def get_session(self) -> Session:
        """Get a new database session."""
        if self.SessionLocal is None:
            raise RuntimeError("Database not initialized. Call connect() first.")
        return self.SessionLocal()

    def health_check(self) -> bool:
        """Check database connectivity and readiness."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.debug("Database health check passed")
                return True
        except SQLAlchemyError as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def close(self):
        """Close connection pool."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection pool closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Singleton instance (lazy-loaded on first use)
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get or create the global database manager."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def get_session() -> Session:
    """Get a new database session from the global manager."""
    return get_db_manager().get_session()
