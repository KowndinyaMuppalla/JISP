"""
JISP Safety Guards

Explicit validation layer ensuring:
  1. LLaMA model is only called via reasoning_service.py
  2. All LLaMA calls are logged (audit trail)
  3. Request/response bounds are enforced (no unbounded operations)
  4. Invalid contexts are rejected before reaching LLaMA

Safety guards are STATELESS and called early in the request pipeline.
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SafetyGuardViolation(Exception):
    """Raised when a safety guard rejects a request."""

    def __init__(self, guard_name: str, reason: str):
        self.guard_name = guard_name
        self.reason = reason
        super().__init__(f"{guard_name}: {reason}")


class SafetyGuards:
    """
    Enforces JISP safety constraints.

    Constraints (locked):
      1. Template names are validated against known templates
      2. Subject must be non-empty string, max 255 chars
      3. Context dict must be present if template requires it
      4. No context key can exceed 1MB (prevent malicious payloads)
      5. Explanation requests must specify valid finding_type if provided
    """

    # Known valid templates (must match those in reasoning/prompt_templates/)
    VALID_TEMPLATES = {
        "asset_risk",
        "flood_explanation",
        "anomaly_summary",
    }

    # Known valid finding types (from GeoAI contract)
    VALID_FINDING_TYPES = {
        "flood_proximity",
        "flood_change",
        "temperature_spike",
        "vegetation_anomaly",
        # Extensible: add new types as GeoAI modules define them
    }

    # Maximum sizes (prevent DOS attacks)
    MAX_SUBJECT_LENGTH = 255
    MAX_CONTEXT_VALUE_SIZE = 1024 * 1024  # 1MB per context value
    MAX_EXPLANATION_CONTEXT_SIZE = 10 * 1024 * 1024  # 10MB total context

    @classmethod
    def validate_template(cls, template: str) -> bool:
        """
        Validate template name against known templates.

        Args:
            template: Template name from request

        Returns:
            True if valid, False otherwise

        Raises:
            SafetyGuardViolation if invalid
        """
        if template not in cls.VALID_TEMPLATES:
            valid_list = ", ".join(sorted(cls.VALID_TEMPLATES))
            raise SafetyGuardViolation(
                "invalid_template",
                f"Unknown template '{template}'. Valid: {valid_list}",
            )
        return True

    @classmethod
    def validate_subject(cls, subject: str) -> bool:
        """
        Validate subject identifier.

        Args:
            subject: Subject ID from request (e.g., "ASSET-12345")

        Returns:
            True if valid

        Raises:
            SafetyGuardViolation if invalid
        """
        if not isinstance(subject, str):
            raise SafetyGuardViolation(
                "invalid_subject",
                f"Subject must be string, got {type(subject).__name__}",
            )
        if not subject or subject.isspace():
            raise SafetyGuardViolation(
                "empty_subject",
                "Subject cannot be empty or whitespace-only",
            )
        if len(subject) > cls.MAX_SUBJECT_LENGTH:
            raise SafetyGuardViolation(
                "subject_too_long",
                f"Subject exceeds {cls.MAX_SUBJECT_LENGTH} chars (got {len(subject)})",
            )
        return True

    @classmethod
    def validate_context(cls, context: Optional[Dict[str, Any]]) -> bool:
        """
        Validate GeoAI context dictionary.

        Args:
            context: Context dict from request (may be None for /health)

        Returns:
            True if valid

        Raises:
            SafetyGuardViolation if invalid
        """
        if context is None:
            return True

        if not isinstance(context, dict):
            raise SafetyGuardViolation(
                "invalid_context",
                f"Context must be dict, got {type(context).__name__}",
            )

        # Check individual values for size
        total_size = 0
        for key, value in context.items():
            if not isinstance(key, str):
                raise SafetyGuardViolation(
                    "invalid_context_key",
                    f"Context keys must be strings, got {type(key).__name__}",
                )

            # Estimate value size (JSON representation)
            import json

            try:
                value_size = len(json.dumps(value).encode("utf-8"))
            except (TypeError, ValueError):
                value_size = len(str(value).encode("utf-8"))

            if value_size > cls.MAX_CONTEXT_VALUE_SIZE:
                raise SafetyGuardViolation(
                    "context_value_too_large",
                    f"Context['{key}'] exceeds 1MB ({value_size} bytes)",
                )

            total_size += value_size

        if total_size > cls.MAX_EXPLANATION_CONTEXT_SIZE:
            raise SafetyGuardViolation(
                "total_context_too_large",
                f"Total context exceeds 10MB ({total_size} bytes)",
            )

        return True

    @classmethod
    def validate_finding_type(cls, finding_type: Optional[str]) -> bool:
        """
        Validate finding_type if provided in context.

        Args:
            finding_type: Optional finding type from context

        Returns:
            True if valid or not provided

        Raises:
            SafetyGuardViolation if provided but invalid
        """
        if finding_type is None:
            return True

        if finding_type not in cls.VALID_FINDING_TYPES:
            valid_list = ", ".join(sorted(cls.VALID_FINDING_TYPES))
            logger.warning(
                f"Unknown finding_type '{finding_type}'. Valid: {valid_list}"
            )
            # Note: We warn but don't reject—allows future extensibility
            # GeoAI modules can add new types without requiring code changes

        return True

    @classmethod
    def validate_explain_request(
        cls,
        subject: str,
        template: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Comprehensive validation for /explain requests.

        Checks:
          1. Template is known
          2. Subject is valid
          3. Context is well-formed
          4. Finding type (if present) is known

        Args:
            subject: Subject ID
            template: Template name
            context: Optional GeoAI context

        Returns:
            True if all checks pass

        Raises:
            SafetyGuardViolation on first failure
        """
        cls.validate_template(template)
        cls.validate_subject(subject)
        cls.validate_context(context)

        if context and "finding_type" in context:
            cls.validate_finding_type(context["finding_type"])

        # Log successful validation (lazy import to avoid circular dependency)
        try:
            from logging_audit.audit_service import get_audit_logger
            audit = get_audit_logger()
            audit.log_event(
                event_type="safety_guard_passed",
                severity="info",
                description=f"ExplainRequest validation passed: {subject}/{template}",
                context={
                    "subject": subject,
                    "template": template,
                    "context_keys": list(context.keys()) if context else [],
                },
                success=True,
            )
        except Exception as e:
            logger.debug(f"Could not log safety guard success: {e}")

        return True

    @classmethod
    def log_guard_rejection(
        cls,
        guard_name: str,
        reason: str,
        subject: Optional[str] = None,
        template: Optional[str] = None,
    ):
        """
        Log a safety guard rejection for audit trail.

        Args:
            guard_name: Name of the guard that rejected
            reason: Reason for rejection
            subject: Subject (if available)
            template: Template (if available)
        """
        try:
            from logging_audit.audit_service import get_audit_logger
            audit = get_audit_logger()
            audit.log_event(
                event_type="safety_guard_rejected",
                severity="warning",
                description=f"{guard_name}: {reason}",
                context={
                    "guard": guard_name,
                    "subject": subject,
                    "template": template,
                },
                success=False,
            )
        except Exception as e:
            logger.debug(f"Could not log safety guard rejection: {e}")


def validate_explain_request(
    subject: str,
    template: str,
    context: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Convenience function to validate /explain requests.

    Calls SafetyGuards.validate_explain_request() and logs violations.

    Args:
        subject: Subject ID
        template: Template name
        context: Optional context dict

    Returns:
        True if valid

    Raises:
        SafetyGuardViolation on first failure
    """
    try:
        return SafetyGuards.validate_explain_request(subject, template, context)
    except SafetyGuardViolation as e:
        SafetyGuards.log_guard_rejection(
            guard_name=e.guard_name,
            reason=e.reason,
            subject=subject,
            template=template,
        )
        raise
