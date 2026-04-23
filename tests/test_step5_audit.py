"""
STEP 5 Audit Logging & Safety Guards Test Suite

Comprehensive tests covering:
  - Database schema and ORM models
  - Audit logging (request, explanation, events)
  - Safety guard validation
  - Error recovery and edge cases
"""

import pytest
import json
from datetime import datetime
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models import APIRequest, Explanation, AuditEvent, Base, init_database
from config.database import DatabaseConfig, DatabaseManager, get_session
from logging_audit.audit_service import AuditLogger, RequestMetadata, ExplanationMetadata
from logging_audit.safety_guards import SafetyGuards, SafetyGuardViolation, validate_explain_request


# Test database (in-memory SQLite for isolation)
@pytest.fixture
def test_db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal


@pytest.fixture
def audit_logger():
    """Create AuditLogger with async_mode=False for deterministic testing."""
    return AuditLogger(async_mode=False)


# ============================================================================
# Database & ORM Tests
# ============================================================================


class TestAPIRequestModel:
    """Tests for APIRequest ORM model."""

    def test_create_request(self, test_db):
        """Test creating an API request record."""
        engine, SessionLocal = test_db
        session = SessionLocal()

        record = APIRequest(
            endpoint="/explain",
            method="POST",
            request_id="test-123",
            status_code=200,
            response_time_ms=45.2,
            client_ip="192.168.1.1",
        )
        session.add(record)
        session.commit()

        # Verify persistence
        assert record.id is not None
        assert record.created_at is not None

        # Query back
        fetched = session.query(APIRequest).filter_by(request_id="test-123").first()
        assert fetched is not None
        assert fetched.status_code == 200
        assert fetched.response_time_ms == 45.2

        session.close()

    def test_request_with_error_message(self, test_db):
        """Test creating a failed request with error message."""
        engine, SessionLocal = test_db
        session = SessionLocal()

        record = APIRequest(
            endpoint="/explain",
            method="POST",
            request_id="test-error",
            status_code=503,
            response_time_ms=5000.0,
            error_message="Ollama service unavailable",
        )
        session.add(record)
        session.commit()

        fetched = session.query(APIRequest).filter_by(request_id="test-error").first()
        assert fetched.status_code == 503
        assert "Ollama" in fetched.error_message

        session.close()

    def test_request_with_metadata(self, test_db):
        """Test request with extra_data JSON."""
        engine, SessionLocal = test_db
        session = SessionLocal()

        extra_data = {"user_agent": "curl/7.64", "custom_field": "value"}

        record = APIRequest(
            endpoint="/health",
            method="GET",
            request_id="test-meta",
            status_code=200,
            response_time_ms=2.1,
            extra_data=extra_data,
        )
        session.add(record)
        session.commit()

        fetched = session.query(APIRequest).filter_by(request_id="test-meta").first()
        assert fetched.extra_data["user_agent"] == "curl/7.64"

        session.close()


class TestExplanationModel:
    """Tests for Explanation ORM model."""

    def test_create_explanation(self, test_db):
        """Test creating an explanation record."""
        engine, SessionLocal = test_db
        session = SessionLocal()

        record = Explanation(
            subject="ASSET-12345",
            template="asset_risk",
            model="llama3.3",
            explanation_text="Asset is 2.5 km from active flood zone.",
            explanation_length=38,
            execution_time_ms=125.5,
        )
        session.add(record)
        session.commit()

        fetched = session.query(Explanation).filter_by(subject="ASSET-12345").first()
        assert fetched is not None
        assert fetched.template == "asset_risk"
        assert fetched.explanation_length == 38

        session.close()

    def test_explanation_with_context_keys(self, test_db):
        """Test explanation with context metadata."""
        engine, SessionLocal = test_db
        session = SessionLocal()

        record = Explanation(
            subject="ASSET-99",
            template="flood_explanation",
            model="llama3.3",
            context_keys=["finding_type", "severity_raw", "metrics"],
            explanation_text="Flood extent increased by 15%.",
            explanation_length=31,
            execution_time_ms=98.0,
            severity_raw=0.75,
            finding_type="flood_change",
            source="geoai.flood_module",
        )
        session.add(record)
        session.commit()

        fetched = session.query(Explanation).filter_by(subject="ASSET-99").first()
        assert fetched.finding_type == "flood_change"
        assert fetched.severity_raw == 0.75
        assert "metrics" in fetched.context_keys

        session.close()


class TestAuditEventModel:
    """Tests for AuditEvent ORM model."""

    def test_create_audit_event(self, test_db):
        """Test creating an audit event."""
        engine, SessionLocal = test_db
        session = SessionLocal()

        record = AuditEvent(
            event_type="llama_call",
            severity="info",
            description="LLaMA model invoked for asset_risk template",
            success=True,
        )
        session.add(record)
        session.commit()

        fetched = session.query(AuditEvent).filter_by(event_type="llama_call").first()
        assert fetched is not None
        assert fetched.success is True

        session.close()

    def test_audit_event_with_context(self, test_db):
        """Test audit event with detailed context."""
        engine, SessionLocal = test_db
        session = SessionLocal()

        context = {
            "guard": "invalid_template",
            "subject": "ASSET-123",
            "template": "unknown_template",
        }

        record = AuditEvent(
            event_type="safety_guard_rejected",
            severity="warning",
            description="Unknown template 'unknown_template'",
            context=context,
            success=False,
        )
        session.add(record)
        session.commit()

        fetched = session.query(AuditEvent).filter_by(
            event_type="safety_guard_rejected"
        ).first()
        assert fetched.context["guard"] == "invalid_template"
        assert fetched.success is False

        session.close()


# ============================================================================
# Audit Logging Service Tests
# ============================================================================


class TestAuditLogger:
    """Tests for AuditLogger service."""

    def test_log_request_sync(self, test_db, audit_logger):
        """Test synchronous request logging."""
        # Patch get_session to use test database
        engine, SessionLocal = test_db

        with patch("logging_audit.audit_service.get_session") as mock_get_session:
            mock_get_session.return_value = SessionLocal()

            meta = RequestMetadata(
                request_id="req-123",
                endpoint="/explain",
                method="POST",
                client_ip="127.0.0.1",
            )

            record_id = audit_logger.log_request(
                request_meta=meta,
                status_code=200,
                response_time_ms=50.0,
            )

            assert record_id is not None

    def test_log_explanation_sync(self, test_db, audit_logger):
        """Test synchronous explanation logging."""
        engine, SessionLocal = test_db

        with patch("logging_audit.audit_service.get_session") as mock_get_session:
            mock_get_session.return_value = SessionLocal()

            meta = ExplanationMetadata(
                subject="ASSET-456",
                template="asset_risk",
                model="llama3.3",
                context_keys=["metrics", "signals"],
                finding_type="flood_proximity",
            )

            record_id = audit_logger.log_explanation(
                api_request_id=None,
                explanation_meta=meta,
                explanation_text="Long explanation text here...",
                execution_time_ms=120.0,
            )

            assert record_id is not None

    def test_log_event_sync(self, test_db, audit_logger):
        """Test synchronous audit event logging."""
        engine, SessionLocal = test_db

        with patch("logging_audit.audit_service.get_session") as mock_get_session:
            mock_get_session.return_value = SessionLocal()

            record_id = audit_logger.log_event(
                event_type="safety_guard_passed",
                severity="info",
                description="Request passed all safety checks",
                context={"template": "asset_risk"},
                success=True,
            )

            assert record_id is not None

    def test_query_explanations(self, test_db):
        """Test querying explanation history."""
        engine, SessionLocal = test_db
        session = SessionLocal()

        # Insert test data
        for i in range(5):
            record = Explanation(
                subject=f"ASSET-{i}",
                template="asset_risk" if i % 2 == 0 else "flood_explanation",
                model="llama3.3",
                explanation_text=f"Explanation {i}",
                explanation_length=20,
                execution_time_ms=100.0,
            )
            session.add(record)
        session.commit()
        session.close()

        # Create logger and query
        logger = AuditLogger(async_mode=False)

        with patch("logging_audit.audit_service.get_session") as mock_get_session:
            mock_get_session.return_value = SessionLocal()

            results = logger.query_explanations(template="asset_risk", limit=10)
            assert len(results) == 3  # 0, 2, 4

    def test_query_audit_events(self, test_db):
        """Test querying audit event history."""
        engine, SessionLocal = test_db
        session = SessionLocal()

        # Insert test data
        for event_type in ["llama_call", "safety_guard_passed", "validation_failed"]:
            record = AuditEvent(
                event_type=event_type,
                severity="info" if event_type == "llama_call" else "warning",
                description=f"Test {event_type}",
                success=event_type != "validation_failed",
            )
            session.add(record)
        session.commit()
        session.close()

        logger = AuditLogger(async_mode=False)

        with patch("logging_audit.audit_service.get_session") as mock_get_session:
            mock_get_session.return_value = SessionLocal()

            results = logger.query_audit_events(event_type="llama_call")
            assert len(results) == 1
            assert results[0].event_type == "llama_call"


# ============================================================================
# Safety Guards Tests
# ============================================================================


class TestSafetyGuards:
    """Tests for SafetyGuards validation layer."""

    def test_validate_valid_template(self):
        """Test that valid templates pass."""
        assert SafetyGuards.validate_template("asset_risk") is True
        assert SafetyGuards.validate_template("flood_explanation") is True
        assert SafetyGuards.validate_template("anomaly_summary") is True

    def test_validate_invalid_template(self):
        """Test that invalid templates raise."""
        with pytest.raises(SafetyGuardViolation) as excinfo:
            SafetyGuards.validate_template("unknown_template")
        assert excinfo.value.guard_name == "invalid_template"
        assert "Unknown template" in excinfo.value.reason

    def test_validate_valid_subject(self):
        """Test that valid subjects pass."""
        assert SafetyGuards.validate_subject("ASSET-12345") is True
        assert SafetyGuards.validate_subject("A") is True
        assert SafetyGuards.validate_subject("x" * 255) is True

    def test_validate_empty_subject(self):
        """Test that empty subjects are rejected."""
        with pytest.raises(SafetyGuardViolation) as excinfo:
            SafetyGuards.validate_subject("")
        assert excinfo.value.guard_name == "empty_subject"

    def test_validate_whitespace_subject(self):
        """Test that whitespace-only subjects are rejected."""
        with pytest.raises(SafetyGuardViolation):
            SafetyGuards.validate_subject("   ")

    def test_validate_subject_too_long(self):
        """Test that oversized subjects are rejected."""
        with pytest.raises(SafetyGuardViolation) as excinfo:
            SafetyGuards.validate_subject("x" * 256)
        assert "exceeds" in excinfo.value.reason

    def test_validate_subject_wrong_type(self):
        """Test that non-string subjects are rejected."""
        with pytest.raises(SafetyGuardViolation):
            SafetyGuards.validate_subject(12345)

    def test_validate_none_context(self):
        """Test that None context is valid."""
        assert SafetyGuards.validate_context(None) is True

    def test_validate_empty_context(self):
        """Test that empty dict context is valid."""
        assert SafetyGuards.validate_context({}) is True

    def test_validate_valid_context(self):
        """Test that valid context dict passes."""
        context = {
            "finding_type": "flood_proximity",
            "severity_raw": 0.75,
            "metrics": {"proximity_km": 2.5},
        }
        assert SafetyGuards.validate_context(context) is True

    def test_validate_context_invalid_type(self):
        """Test that non-dict context is rejected."""
        with pytest.raises(SafetyGuardViolation):
            SafetyGuards.validate_context("not a dict")

    def test_validate_context_oversized_value(self):
        """Test that oversized context values are rejected."""
        # Create a value > 1MB
        large_value = "x" * (1024 * 1024 + 1)
        context = {"huge": large_value}

        with pytest.raises(SafetyGuardViolation) as excinfo:
            SafetyGuards.validate_context(context)
        assert "exceeds 1MB" in excinfo.value.reason

    def test_validate_finding_type_valid(self):
        """Test that known finding types pass."""
        assert SafetyGuards.validate_finding_type("flood_proximity") is True
        assert SafetyGuards.validate_finding_type("flood_change") is True
        assert SafetyGuards.validate_finding_type("temperature_spike") is True

    def test_validate_finding_type_unknown(self):
        """Test that unknown finding types are logged but not rejected."""
        # Should return True but log a warning
        assert SafetyGuards.validate_finding_type("future_finding_type") is True

    def test_validate_finding_type_none(self):
        """Test that None finding type is valid."""
        assert SafetyGuards.validate_finding_type(None) is True

    def test_validate_explain_request_valid(self):
        """Test that valid explain requests pass all checks."""
        context = {
            "finding_type": "flood_proximity",
            "severity_raw": 0.5,
            "metrics": {"proximity_km": 3.0},
        }

        # The audit logger is imported lazily inside the function, so patch the import
        with patch("logging_audit.audit_service.get_audit_logger"):
            assert SafetyGuards.validate_explain_request(
                subject="ASSET-123",
                template="asset_risk",
                context=context,
            ) is True

    def test_validate_explain_request_bad_template(self):
        """Test rejection of bad template."""
        with pytest.raises(SafetyGuardViolation):
            SafetyGuards.validate_explain_request(
                subject="ASSET-123",
                template="bad_template",
            )

    def test_validate_explain_request_bad_subject(self):
        """Test rejection of bad subject."""
        with pytest.raises(SafetyGuardViolation):
            SafetyGuards.validate_explain_request(
                subject="",
                template="asset_risk",
            )

    def test_validate_explain_request_bad_context(self):
        """Test rejection of bad context."""
        with pytest.raises(SafetyGuardViolation):
            SafetyGuards.validate_explain_request(
                subject="ASSET-123",
                template="asset_risk",
                context="not a dict",
            )


class TestConvenienceFunctions:
    """Tests for convenience validation functions."""

    def test_validate_explain_request_function(self):
        """Test the validate_explain_request convenience function."""
        with patch("logging_audit.audit_service.get_audit_logger"):
            assert validate_explain_request(
                subject="ASSET-999",
                template="flood_explanation",
                context={"finding_type": "flood_change"},
            ) is True

    def test_validate_explain_request_logs_rejection(self):
        """Test that function logs rejections."""
        with patch("logging_audit.safety_guards.SafetyGuards.log_guard_rejection") as mock_log:
            with pytest.raises(SafetyGuardViolation):
                validate_explain_request(
                    subject="",
                    template="asset_risk",
                )
            assert mock_log.called


# ============================================================================
# Integration & Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error recovery."""

    def test_context_with_nested_structures(self):
        """Test deeply nested context structures."""
        context = {
            "metrics": {
                "level1": {
                    "level2": {
                        "level3": {"data": [1, 2, 3, 4, 5]},
                    },
                },
            },
        }
        assert SafetyGuards.validate_context(context) is True

    def test_context_with_unicode_keys(self):
        """Test context with Unicode characters in keys."""
        context = {"metric_🌊": 123.45}
        assert SafetyGuards.validate_context(context) is True

    def test_subject_with_special_characters(self):
        """Test subject with special characters."""
        assert SafetyGuards.validate_subject("ASSET-12345_v2.0") is True
        assert SafetyGuards.validate_subject("物件-123") is True

    def test_concurrent_logging(self, test_db, audit_logger):
        """Test concurrent async logging requests."""
        import threading

        engine, SessionLocal = test_db
        results = []

        def log_request():
            with patch("logging_audit.audit_service.get_session"):
                meta = RequestMetadata(
                    request_id=f"req-{threading.current_thread().ident}",
                    endpoint="/explain",
                    method="POST",
                )
                audit_logger.log_request(meta, 200, 50.0)
                results.append(1)

        threads = [threading.Thread(target=log_request) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # All threads should have completed
        assert len(results) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
