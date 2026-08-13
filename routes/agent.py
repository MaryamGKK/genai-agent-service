from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.session import get_db
from tools.registry import ToolRegistry
from tools.operations import bind_tools_to_registry
from observability.recorder import AgentRunRecorder
from agent.loop import AgentOrchestrator
from typing import Optional

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class AgentResponse(BaseModel):
    answer: Optional[str] = None
    run_id: str
    status: str
    error: Optional[str] = None
    language: Optional[dict] = None
    iterations: Optional[int] = None
    duration_ms: Optional[int] = None
    tokens: Optional[dict] = None
    tool_trace: Optional[list] = None


@router.post("/", response_model=AgentResponse)
async def ask_agent(request: AgentRequest, req: Request, db: Session = Depends(get_db)):
    """Ask the agent a question"""

    client_ip = req.client.host if req.client else "0.0.0.0"

    registry = ToolRegistry(db)
    registry.load_schemas_from_db()
    bind_tools_to_registry(registry, db)

    recorder = AgentRunRecorder(db)
    orchestrator = AgentOrchestrator(registry, recorder, db)

    result = await orchestrator.run(request.query, request.session_id, client_ip)

    if result.get("error"):
        return AgentResponse(
            error=result.get("error"),
            run_id=result.get("run_id", ""),
            status=result.get("status", "error"),
            language=result.get("language"),
        )

    return AgentResponse(
        answer=result.get("answer"),
        run_id=result.get("run_id"),
        status=result.get("status", "success"),
        language=result.get("language"),
        iterations=result.get("iterations"),
        duration_ms=result.get("duration_ms"),
        tokens=result.get("tokens"),
        tool_trace=result.get("tool_trace"),
    )


@router.delete("/{run_id}")
async def cancel_run(run_id: str, db: Session = Depends(get_db)):
    """Cancel an ongoing run"""
    recorder = AgentRunRecorder(db)
    recorder.pause_run(run_id, 0)

    return {
        "status": "interrupted",
        "run_id": run_id,
        "message": "Run cancelled. You can resume with the same run_id.",
    }


@router.get("/{run_id}/resume")
async def resume_run(run_id: str, db: Session = Depends(get_db)):
    """Resume a paused run"""
    recorder = AgentRunRecorder(db)
    result = recorder.resume_run(run_id)

    if result:
        return {
            "status": "resumed",
            "run_id": run_id,
            "message": "Run resumed from checkpoint",
        }

    return {"error": "Could not resume run", "run_id": run_id}
