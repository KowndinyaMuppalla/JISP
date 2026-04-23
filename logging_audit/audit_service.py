"""
JISP Audit Logging Service

Provides centralized audit trail recording:
  - log_request()     : Record HTTP request entry/exit
  - log_explanation() : Record explanation generation
  - log_event()       : Record safety guard & system events
  - query_history()   : Retrieve historical data for analytics

Non-blocking: Uses threading for async log persistence to avoid
impacting API response times.
"""

import logging
import threading
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from api.models import APIRequest, Explanation, AuditEvent
from config.database import get_session

logger = logging.getLogger(__name__)


@dataclass
class RequestMetadata:
    """Metadata for a single HTTP request."""

    request_id: str
    endpoint: str
    method: str
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ExplanationMetadata:
    """Metadata for a generated explanation."""

    subject: str
    template: str
    model: str
    context_keys: Optional[List[str]] = None
    severity_raw: Optional[float] = None
    finding_type: Optional[str] = None
    source: Optional[str] = None


class AuditLogger:
    """
    Centralized audit logging service.

    Records all API activity, explanations, and security events.
    Uses background threads to avoid blocking API responses.
    """

    def __init__(self, async_mode: bool = True):
        self.async_mode = async_mode
        self._lock = threading.Lock()
        logger.info(
            f"AuditLogger initialized (async_mode={async_mode})"
        )

    def log_request(
        self,
        request_meta: RequestMetadata,
        status_code: int,
        response_time_ms: float,
        error_message: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """
        Log an HTTP request/response.

        Args:
            request_meta: Request metadata (id, endpoint, method, client_ip)
            status_code: HTTP response status code (200, 400, 503, etc.)
            response_time_ms: Total request processing time in milliseconds
            error_message: Error description if status != 200
            extra_metadata: Additional context (headers, query params, etc.)

        Returns:
            Database record ID (or None if logging failed)
        """

        def _persist():
            try:
                session = get_session()
                extra_data = extra_metadata or {}
                if request_meta.user_agent:
                    extra_data["user_agent"] = request_meta.user_agent

                record = APIRequest(
                    endpoint=request_meta.endpoint,
                    method=request_meta.method,
                    request_id=request_meta.request_id,
                    status_code=status_code,
                    response_time_ms=response_time_ms,
                    client_ip=request_meta.client_ip,
                    error_message=error_message,
                    extra_data=extra_data,
                )
                session.add(record)
                session.commit()
                record_id = record.id
                session.close()

                logger.debug(
                    f"Logged API request: {request_meta.endpoint} "
                    f"{status_code} ({response_time_ms:.1f}ms)"
                )
                return record_id
            except SQLAlchemyError as e:
                logger.error(f"Failed to log API request: {e}")
                return None

        if self.async_mode:
            thread = threading.Thread(target=_persist, daemon=True)
            thread.start()
            return None  # Async: caller doesn't wait for ID
        else:
            return _persist()

    def log_explanation(
        self,
        api_request_id: Optional[int],
        explanation_meta: ExplanationMetadata,
        explanation_text: str,
        execution_time_ms: float,
    ) -> Optional[int]:
        """
        Log a generated explanation.

        Args:
            api_request_id: Reference to parent APIRequest record
            explanation_meta: Explanation metadata
            explanation_text: The full explanation text from LLaMA
            execution_time_ms: Time to generate explanation

        Returns:
            Database record ID (or None if logging failed)
        """

        def _persist():
            try:
                session = get_session()

                record = Explanation(
                    api_request_id=api_request_id,
                    subject=explanation_meta.subject,
                    template=explanation_meta.template,
                    model=explanation_meta.model,
                    context_keys=explanation_meta.context_keys,
                    explanation_text=explanation_text,
                    explanation_length=len(explanation_text),
                    execution_time_ms=execution_time_ms,
                    severity_raw=explanation_meta.severity_raw,
                    finding_type=explanation_meta.finding_type,
                    source=explanation_meta.source,
                )
                session.add(record)
                session.commit()
                record_id = record.id
                session.close()

                logger.debug(
                    f"Logged explanation: {explanation_meta.subject} "
                    f"({len(explanation_text)} chars, {execution_time_ms:.1f}ms)"
                )
                return record_id
            except SQLAlchemyError as e:
                logger.error(f"Failed to log explanation: {e}")
                return None

        if self.async_mode:
            thread = threading.Thread(target=_persist, daemon=True)
            thread.start()
            return None
        else:
            return _persist()

    def log_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        api_request_id: Optional[int] = None,
        explanation_id: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        success: bool = True,
    ) -> Optional[int]:
        """
        Log a fine-grained audit event.

        Event types (examples):
          - "llama_call"            : LLaMA model invoked
          - "template_loaded"       : Template file loaded
          - "safety_guard_passed"   : Request passed validation
          - "safety_guard_rejected" : Request blocked by safety check
          - "validation_failed"     : Pydantic validation failed
          - "ollama_error"          : Ollama service unavailable
          - "db_error"              : Database operation failed

        Severity levels: "info", "warning", "error", "critical"

        Args:
            event_type: Category of event
            severity: Severity level
            description: Human-readable event description
            api_request_id: Parent API request (if applicable)
            explanation_id: Parent explanation (if applicable)
            context: Additional event-specific data
            success: Whether the operation succeeded

        Returns:
            Database record ID (or None if logging failed)
        """

        def _persist():
            try:
                session = get_session()

                record = AuditEvent(
                    api_request_id=api_request_id,
                    explanation_id=explanation_id,
                    event_type=event_type,
                    severity=severity,
                    description=description,
                    context=context,
                    success=success,
                )
                session.add(record)
                session.commit()
                record_id = record.id
                session.close()

                logger.debug(
                    f"Logged audit event: {event_type} ({severity}) - {description[:50]}"
                )
                return record_id
            except SQLAlchemyError as e:
                logger.error(f"Failed to log audit event: {e}")
                return None

        if self.async_mode:
            thread = threading.Thread(target=_persist, daemon=True)
            thread.start()
            return None
        else:
            return _persist()

    def query_explanations(
        self,
        subject: Optional[str] = None,
        template: Optional[str] = None,
        limit: int = 100,
    ) -> List[Explanation]:
        """
        Query explanation history.

        Args:
            subject: Filter by subject (e.g., "ASSET-12345")
            template: Filter by template name
            limit: Maximum records to return

        Returns:
            List of Explanation records
        """
        try:
            session = get_session()
            query = session.query(Explanation)

            if subject:
                query = query.filter(Explanation.subject == subject)
            if template:
                query = query.filter(Explanation.template == template)

            results = query.order_by(
                Explanation.created_at.desc()
            ).limit(limit).all()
            session.close()
            return results
        except SQLAlchemyError as e:
            logger.error(f"Failed to query explanations: {e}")
            return []

    def query_audit_events(
        self,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """
        Query audit event history.

        Args:
            event_type: Filter by event type (e.g., "llama_call")
            severity: Filter by severity ("info", "warning", "error", "critical")
            limit: Maximum records to return

        Returns:
            List of AuditEvent records
        """
        try:
            session = get_session()
            query = session.query(AuditEvent)

            if event_type:
                query = query.filter(AuditEvent.event_type == event_type)
            if severity:
                query = query.filter(AuditEvent.severity == severity)

            results = query.order_by(
                AuditEvent.created_at.desc()
            ).limit(limit).all()
            session.close()
            return results
        except SQLAlchemyError as e:
            logger.error(f"Failed to query audit events: {e}")
            return []


# Singleton instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get or create the global audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(async_mode=True)
    return _audit_logger
