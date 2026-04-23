"""
JISP Audit Logging Models & Schema

Defines SQLAlchemy ORM models for storing audit trails:
  - api_requests      : All HTTP requests (GET /health, POST /explain)
  - explanations      : Generated explanations with metadata
  - audit_events      : Fine-grained safety guard & system events

Uses TimescaleDB hypertables for efficient time-series storage.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    DateTime,
    Boolean,
    JSON,
    ForeignKey,
    Index,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class APIRequest(Base):
    """
    HTTP request audit log entry.

    One record per /health or /explain call, capturing:
      - method, endpoint, status code
      - client metadata (if available)
      - request arrival and response time
      - error details (if applicable)
    """

    __tablename__ = "api_requests"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    endpoint = Column(String(255), nullable=False, index=True)  # e.g., "/explain", "/health"
    method = Column(String(10), nullable=False)  # GET, POST, etc.
    request_id = Column(String(36), unique=True, index=True)  # UUID for tracing
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Float, nullable=False)
    client_ip = Column(String(45), nullable=True)  # IPv4 or IPv6
    error_message = Column(Text, nullable=True)
    extra_data = Column(JSON, nullable=True)  # Extra context (user_agent, headers, etc.)

    explanations = relationship("Explanation", back_populates="api_request")
    audit_events = relationship("AuditEvent", back_populates="api_request")

    def __repr__(self):
        return (
            f"<APIRequest id={self.id} endpoint={self.endpoint} "
            f"status={self.status_code} response_time={self.response_time_ms}ms>"
        )


class Explanation(Base):
    """
    Generated explanation record.

    One record per POST /explain call that returns 200 OK.
    Captures the full input/output for audit and analytics.
    """

    __tablename__ = "explanations"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    api_request_id = Column(Integer, ForeignKey("api_requests.id"), nullable=True)
    subject = Column(String(255), nullable=False, index=True)  # e.g., "ASSET-12345"
    template = Column(String(100), nullable=False, index=True)  # asset_risk, flood_explanation, etc.
    model = Column(String(100), nullable=False, default="llama3.3")  # LLaMA model version
    context_keys = Column(JSON, nullable=True)  # Keys present in the GeoAI context dict
    explanation_text = Column(Text, nullable=False)
    explanation_length = Column(Integer, nullable=False)  # Character count
    execution_time_ms = Column(Float, nullable=False)
    severity_raw = Column(Float, nullable=True)  # Raw severity from finding (0–1)
    finding_type = Column(String(100), nullable=True)  # flood_proximity, flood_change, etc.
    source = Column(String(255), nullable=True)  # Which GeoAI module called this

    api_request = relationship("APIRequest", back_populates="explanations")
    audit_events = relationship("AuditEvent", back_populates="explanation")

    def __repr__(self):
        return (
            f"<Explanation id={self.id} subject={self.subject} "
            f"template={self.template} length={self.explanation_length}>"
        )


class AuditEvent(Base):
    """
    Fine-grained audit event log.

    Captures safety guards, validation checks, and system events:
      - LLaMA model usage (when/where called)
      - Safety guard activations (when constraints enforced)
      - Request validation failures (before they reach endpoints)
      - Connection events (database, Ollama, etc.)
    """

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    api_request_id = Column(Integer, ForeignKey("api_requests.id"), nullable=True)
    explanation_id = Column(Integer, ForeignKey("explanations.id"), nullable=True)
    event_type = Column(String(100), nullable=False, index=True)
    # event_type examples:
    #   "llama_call"            : LLaMA model invoked via ollama_client
    #   "template_loaded"       : Prompt template loaded from disk
    #   "safety_guard_passed"   : Request passed all safety checks
    #   "safety_guard_rejected" : Request rejected by safety guard
    #   "validation_failed"     : Pydantic schema validation failed
    #   "ollama_error"          : Ollama service error
    #   "db_error"              : Database operation failed
    #   "config_loaded"         : Environment configuration verified

    severity = Column(String(20), nullable=False)  # "info", "warning", "error", "critical"
    description = Column(Text, nullable=False)
    context = Column(JSON, nullable=True)  # Event-specific context data
    success = Column(Boolean, default=True)  # Did the operation succeed?

    api_request = relationship("APIRequest", back_populates="audit_events")
    explanation = relationship("Explanation", back_populates="audit_events")

    def __repr__(self):
        return (
            f"<AuditEvent id={self.id} type={self.event_type} "
            f"severity={self.severity} success={self.success}>"
        )


# Indexes for common query patterns
Index("ix_explanations_created_subject", Explanation.created_at, Explanation.subject)
Index("ix_explanations_created_template", Explanation.created_at, Explanation.template)
Index("ix_audit_events_created_type", AuditEvent.created_at, AuditEvent.event_type)


def init_database(db_url: str):
    """
    Initialize database schema.

    Creates all tables and enables TimescaleDB extension if available.
    Safe to call multiple times (idempotent).

    Args:
        db_url: PostgreSQL connection string

    Example:
        init_database("postgresql://user:pass@localhost:5432/jisp")
    """
    engine = create_engine(db_url)

    # Create all tables
    Base.metadata.create_all(engine)

    # Try to enable TimescaleDB extension (non-fatal if unavailable)
    try:
        with engine.connect() as conn:
            conn.execute('CREATE EXTENSION IF NOT EXISTS timescaledb')
            conn.commit()
            
            # Convert explanations to hypertable for time-series optimization
            conn.execute(
                """
                SELECT create_hypertable('explanations', 'created_at',
                if_not_exists => TRUE)
                """
            )
            conn.commit()
    except Exception:
        # TimescaleDB not installed or extension creation failed—continue anyway
        # Regular PostgreSQL tables work fine, just less optimized for time-series
        pass

    engine.dispose()
