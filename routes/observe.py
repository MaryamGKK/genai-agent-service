from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.session import get_db
from db.models import AgentRun, AuditLog
from observability.recorder import AgentRunRecorder
from security.audit import AuditLogger
from typing import Optional

router = APIRouter(prefix="/observe", tags=["observability"])


@router.get("/recent")
async def get_recent_runs(limit: int = 10, db: Session = Depends(get_db)):
    """Get recent agent runs"""
    if limit > 100:
        limit = 100

    recorder = AgentRunRecorder(db)
    runs = recorder.get_recent_runs(limit=limit)

    return {
        "runs": runs,
        "count": len(runs),
    }


@router.get("/audit")
async def get_audit_log(
    run_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Get audit log entries"""
    query = db.query(AuditLog)

    if run_id:
        query = query.filter_by(run_id=run_id)

    if event_type:
        query = query.filter_by(event_type=event_type)

    if limit > 500:
        limit = 500

    events = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    return {
        "events": [
            {
                "id": e.id,
                "run_id": e.run_id,
                "event_type": e.event_type,
                "severity": e.severity,
                "details": e.details,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "count": len(events),
    }


@router.get("/stats")
async def get_statistics(db: Session = Depends(get_db)):
    """Get system statistics"""
    total_runs = db.query(AgentRun).count()
    successful_runs = db.query(AgentRun).filter_by(status="success").count()
    failed_runs = db.query(AgentRun).filter_by(status="failed").count()
    total_events = db.query(AuditLog).count()

    from sqlalchemy import func

    total_tokens = db.query(func.sum(AgentRun.total_tokens_used)).scalar() or 0

    return {
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "success_rate": (successful_runs / total_runs * 100) if total_runs > 0 else 0,
        "total_audit_events": total_events,
        "total_tokens_used": total_tokens,
    }


@router.get("/{run_id}")
async def get_run_details(run_id: str, db: Session = Depends(get_db)):
    """Get full details of an agent run"""
    recorder = AgentRunRecorder(db)
    run_details = recorder.get_run_details(run_id)

    if not run_details:
        raise HTTPException(status_code=404, detail="Run not found")

    audit_trail = AuditLogger.get_audit_trail(db, run_id)

    return {
        "run": run_details,
        "audit_trail": audit_trail,
    }
