import uuid
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from db.models import AgentRun, AgentStep, AgentSession


class AgentRunRecorder:
    """Records agent runs and steps to database for observability"""

    def __init__(self, db: Session):
        self.db = db

    def create_session(self, user_id: Optional[str] = None) -> str:
        """Create a new agent session. Returns session_id"""
        session_id = str(uuid.uuid4())
        session = AgentSession(id=session_id, user_id=user_id, status="active")
        self.db.add(session)
        self.db.commit()
        return session_id

    def start_run(self, query: str, session_id: Optional[str] = None) -> str:
        """Start a new agent run. Returns run_id"""
        run_id = str(uuid.uuid4())

        # Update session if provided
        if session_id:
            session = self.db.query(AgentSession).filter_by(id=session_id).first()
            if session:
                session.last_active_at = datetime.utcnow()

        run = AgentRun(
            id=run_id,
            session_id=session_id,
            query=query,
            status="pending",
        )
        self.db.add(run)
        self.db.commit()
        return run_id

    def update_run_status(self, run_id: str, status: str):
        """Update run status"""
        run = self.db.query(AgentRun).filter_by(id=run_id).first()
        if run:
            run.status = status
            self.db.commit()

    def record_step(
        self,
        run_id: str,
        step_num: int,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_output: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        duration_ms: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ):
        """Record a tool execution step"""
        total_tokens = input_tokens + output_tokens

        step = AgentStep(
            run_id=run_id,
            step_number=step_num,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            error_message=error_message,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens_used=total_tokens,
        )
        self.db.add(step)
        self.db.commit()

    def end_run(
        self,
        run_id: str,
        final_answer: Optional[str] = None,
        iterations: int = 0,
        status: str = "success",
        total_duration_ms: int = 0,
        checkpoint_step: int = 0,
    ):
        """Mark a run as complete and calculate totals"""
        run = self.db.query(AgentRun).filter_by(id=run_id).first()

        if run:
            run.final_answer = final_answer
            run.status = status
            run.total_iterations = iterations
            run.total_duration_ms = total_duration_ms
            run.checkpoint_step = checkpoint_step
            run.completed_at = datetime.utcnow()

            # Calculate total tokens from steps
            steps = self.db.query(AgentStep).filter_by(run_id=run_id).all()
            run.total_input_tokens = sum(s.input_tokens or 0 for s in steps)
            run.total_output_tokens = sum(s.output_tokens or 0 for s in steps)
            run.total_tokens_used = sum(s.total_tokens_used or 0 for s in steps)

            self.db.commit()

    def get_steps(self, run_id: str) -> List[Dict[str, Any]]:
        """Get all steps for a run, formatted for API response"""
        steps = self.db.query(AgentStep).filter_by(run_id=run_id).order_by(AgentStep.step_number).all()

        return [
            {
                "step": s.step_number,
                "tool": s.tool_name,
                "input": s.tool_input,
                "output": s.tool_output,
                "error": s.error_message,
                "duration_ms": s.duration_ms,
                "tokens": {
                    "input": s.input_tokens,
                    "output": s.output_tokens,
                    "total": s.total_tokens_used,
                },
            }
            for s in steps
        ]

    def get_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get full run details"""
        run = self.db.query(AgentRun).filter_by(id=run_id).first()

        if not run:
            return None

        return {
            "run_id": run.id,
            "session_id": run.session_id,
            "query": run.query,
            "answer": run.final_answer,
            "status": run.status,
            "iterations": run.total_iterations,
            "duration_ms": run.total_duration_ms,
            "checkpoint_step": run.checkpoint_step,
            "tokens": {
                "input": run.total_input_tokens,
                "output": run.total_output_tokens,
                "total": run.total_tokens_used,
            },
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "tool_trace": self.get_steps(run_id),
        }

    def get_recent_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent runs"""
        runs = self.db.query(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit).all()

        return [
            {
                "run_id": r.id,
                "query": r.query[:100],
                "status": r.status,
                "iterations": r.total_iterations,
                "duration_ms": r.total_duration_ms,
                "tokens": r.total_tokens_used,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ]

    def pause_run(self, run_id: str, checkpoint_step: int):
        """Pause a run at a checkpoint"""
        run = self.db.query(AgentRun).filter_by(id=run_id).first()
        if run:
            run.status = "interrupted"
            run.checkpoint_step = checkpoint_step
            self.db.commit()

    def resume_run(self, run_id: str) -> bool:
        """Resume a paused run. Returns success"""
        run = self.db.query(AgentRun).filter_by(id=run_id).first()
        if run and run.status == "interrupted":
            run.status = "running"
            self.db.commit()
            return True
        return False
