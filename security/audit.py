from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from db.models import AuditLog


class AuditLogger:
    """Logs all agent activities to database"""

    EVENT_TYPES = {
        "query_received": "info",
        "query_validated": "info",
        "safety_check": "info",
        "tool_call": "info",
        "write_operation": "warning",
        "validation_failed": "warning",
        "error_occurred": "error",
        "security_flag": "error",
        "rate_limit_hit": "warning",
        "session_created": "info",
        "session_resumed": "info",
        "run_interrupted": "warning",
    }

    @staticmethod
    def log(
        db: Session,
        run_id: Optional[str],
        event_type: str,
        details: Dict[str, Any],
        severity: Optional[str] = None,
    ) -> AuditLog:
        """
        Log an event to the audit trail.

        Args:
            db: Database session
            run_id: Associated run ID (optional)
            event_type: Type of event (see EVENT_TYPES)
            details: Event details as dict
            severity: Override severity (info, warning, error)

        Returns:
            Created AuditLog entry
        """

        if severity is None:
            severity = AuditLogger.EVENT_TYPES.get(event_type, "info")

        if event_type not in AuditLogger.EVENT_TYPES:
            severity = "info"

        audit_entry = AuditLog(
            run_id=run_id,
            event_type=event_type,
            details=details,
            severity=severity,
        )

        db.add(audit_entry)
        db.commit()

        return audit_entry

    @staticmethod
    def log_query_received(db: Session, run_id: str, query: str, session_id: Optional[str] = None):
        """Log when a query is received"""
        AuditLogger.log(
            db,
            run_id,
            "query_received",
            {
                "query_length": len(query),
                "query_preview": query[:100],
                "session_id": session_id,
            },
        )

    @staticmethod
    def log_tool_call(
        db: Session,
        run_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_output: Optional[Dict[str, Any]],
        duration_ms: int,
        error: Optional[str] = None,
    ):
        """Log a tool call"""
        is_write_op = tool_name in ["create_support_ticket"]

        details = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_output": tool_output,
            "duration_ms": duration_ms,
            "error": error,
            "is_write_operation": is_write_op,
        }

        event_type = "write_operation" if is_write_op else "tool_call"
        AuditLogger.log(db, run_id, event_type, details, severity="warning" if is_write_op else "info")

    @staticmethod
    def log_validation_failed(db: Session, run_id: str, reason: str, input_data: Optional[Dict[str, Any]] = None):
        """Log when validation fails"""
        AuditLogger.log(
            db,
            run_id,
            "validation_failed",
            {"reason": reason, "input_preview": str(input_data)[:200]},
            severity="warning",
        )

    @staticmethod
    def log_security_flag(db: Session, run_id: str, flag_type: str, details: Dict[str, Any]):
        """Log security flags"""
        AuditLogger.log(
            db,
            run_id,
            "security_flag",
            {"flag_type": flag_type, **details},
            severity="error",
        )

    @staticmethod
    def log_error(db: Session, run_id: Optional[str], error_type: str, error_msg: str):
        """Log an error"""
        AuditLogger.log(
            db,
            run_id,
            "error_occurred",
            {"error_type": error_type, "error_message": error_msg[:500]},
            severity="error",
        )

    @staticmethod
    def get_audit_trail(db: Session, run_id: str) -> list[Dict[str, Any]]:
        """Get all audit events for a run"""
        events = db.query(AuditLog).filter_by(run_id=run_id).order_by(AuditLog.created_at).all()

        return [
            {
                "timestamp": e.created_at.isoformat(),
                "event_type": e.event_type,
                "severity": e.severity,
                "details": e.details,
            }
            for e in events
        ]
