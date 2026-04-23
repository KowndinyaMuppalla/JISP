"""
JISP Configuration Package

Provides:
  - database : PostgreSQL connection pooling and session management
"""

from config.database import (
    DatabaseConfig,
    DatabaseManager,
    get_db_manager,
    get_session,
)

__all__ = [
    "DatabaseConfig",
    "DatabaseManager",
    "get_db_manager",
    "get_session",
]
