import json
import time
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from openai import OpenAI
from config import config
from security.validators import QueryValidator, SafetyClassifier
from security.audit import AuditLogger
from security.guardrails import Guardrails, rate_limiter
from security.language import LanguageDetector
from tools.registry import ToolRegistry
from observability.recorder import AgentRunRecorder
from db.models import AgentRun


class AgentOrchestrator:
    """Main agent loop orchestrator"""

    def __init__(self, registry: ToolRegistry, recorder: AgentRunRecorder, db: Session):
        self.registry = registry
        self.recorder = recorder
        self.db = db
        self.max_iterations = config.MAX_ITERATIONS

        self.client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )
        self.model = config.LLM_MODEL

    def _build_tools(self) -> List[Dict[str, Any]]:
        """Build OpenAI-compatible tool definitions from registry schemas"""
        tools = []
        for schema in self.registry.get_schemas():
            tools.append({
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                },
            })
        return tools

    async def run(
        self, query: str, session_id: Optional[str] = None, client_ip: str = "0.0.0.0"
    ) -> Dict[str, Any]:
        """
        Main agent loop.
        Returns response dict with answer, run_id, tool_trace, and metadata.
        """

        is_allowed, rate_stats = rate_limiter.is_allowed(client_ip)
        if not is_allowed:
            return {
                "error": "Rate limit exceeded (15 requests per minute)",
                "status": "rate_limited",
                "rate_stats": rate_stats,
            }

        run_id = self.recorder.start_run(query, session_id)
        self.recorder.update_run_status(run_id, "running")

        AuditLogger.log_query_received(self.db, run_id, query, session_id)

        lang_code, lang_name, lang_confidence = LanguageDetector.detect_language(query)

        try:
            is_valid, validation_error = QueryValidator.validate_query(query)
            if not is_valid:
                AuditLogger.log_validation_failed(self.db, run_id, validation_error, {"query": query})
                self.recorder.end_run(run_id, final_answer=validation_error, status="failed")
                return {
                    "error": f"Query validation failed: {validation_error}",
                    "status": "invalid_query",
                    "run_id": run_id,
                }

            safety_score = SafetyClassifier.classify(query)
            if not safety_score.is_safe:
                AuditLogger.log_security_flag(
                    self.db, run_id, "safety_threshold_exceeded", safety_score.model_dump()
                )
                self.recorder.end_run(run_id, final_answer=safety_score.reason, status="rejected")
                return {
                    "error": safety_score.reason,
                    "status": "security_check_failed",
                    "run_id": run_id,
                    "language": {
                        "code": lang_code,
                        "name": lang_name,
                        "confidence": lang_confidence,
                    },
                    "safety_score": safety_score.score,
                }

            tools = self._build_tools()
            system_prompt = LanguageDetector.get_system_prompt(lang_code)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ]

            iteration = 0
            start_time = time.time()

            while iteration < self.max_iterations:
                iteration += 1

                can_continue, budget_error = Guardrails.check_iteration_budget(
                    iteration, self.max_iterations
                )
                if not can_continue:
                    break

                try:
                    print(f"[AGENT] Iteration {iteration}: Calling {self.model}...")

                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                    )

                    print(f"[AGENT] API responded successfully")

                    choice = response.choices[0]
                    input_tokens = getattr(response.usage, 'prompt_tokens', 0) or 0
                    output_tokens = getattr(response.usage, 'completion_tokens', 0) or 0

                    if choice.finish_reason == "tool_calls" or (choice.message.tool_calls and len(choice.message.tool_calls) > 0):
                        # Append assistant message with tool calls
                        messages.append(choice.message)

                        for tool_call in choice.message.tool_calls:
                            tool_name = tool_call.function.name
                            try:
                                tool_args = json.loads(tool_call.function.arguments)
                            except json.JSONDecodeError:
                                tool_args = {}

                            result, error, duration_ms = self.registry.execute(tool_name, tool_args)

                            AuditLogger.log_tool_call(
                                self.db, run_id, tool_name, tool_args, result, duration_ms, error,
                            )

                            self.recorder.record_step(
                                run_id,
                                step_num=iteration,
                                tool_name=tool_name,
                                tool_input=tool_args,
                                tool_output=result,
                                error_message=error,
                                duration_ms=duration_ms,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                            )

                            tool_response = json.dumps(result if result else {"error": error})
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": tool_response,
                            })

                    else:
                        # Final text answer
                        final_answer = choice.message.content or "I couldn't generate an answer."
                        total_duration = int((time.time() - start_time) * 1000)

                        self.recorder.end_run(
                            run_id,
                            final_answer=final_answer,
                            iterations=iteration,
                            status="success",
                            total_duration_ms=total_duration,
                            checkpoint_step=iteration,
                        )

                        return {
                            "answer": final_answer,
                            "run_id": run_id,
                            "session_id": session_id,
                            "status": "success",
                            "language": {
                                "code": lang_code,
                                "name": lang_name,
                                "confidence": lang_confidence,
                            },
                            "iterations": iteration,
                            "duration_ms": total_duration,
                            "tokens": {
                                "total": self._get_run_tokens(run_id),
                            },
                            "tool_trace": self.recorder.get_steps(run_id),
                        }

                except Exception as e:
                    error_msg = str(e)
                    print(f"[AGENT ERROR] LLM call failed: {error_msg}")
                    AuditLogger.log_error(self.db, run_id, "llm_error", error_msg)
                    self.recorder.end_run(
                        run_id,
                        final_answer=f"Error communicating with LLM: {error_msg[:100]}",
                        iterations=iteration,
                        status="failed",
                        total_duration_ms=int((time.time() - start_time) * 1000),
                    )
                    return {
                        "error": f"LLM error: {error_msg[:200]}",
                        "status": "error",
                        "run_id": run_id,
                        "language": {
                            "code": lang_code,
                            "name": lang_name,
                            "confidence": lang_confidence,
                        },
                    }

            total_duration = int((time.time() - start_time) * 1000)
            self.recorder.end_run(
                run_id,
                final_answer="Max iterations reached without final answer",
                iterations=iteration,
                status="max_iterations",
                total_duration_ms=total_duration,
            )
            return {
                "error": "I exceeded my thinking limit. Please try a simpler question.",
                "status": "max_iterations_reached",
                "run_id": run_id,
                "iterations": iteration,
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[AGENT ERROR] Unexpected: {error_msg}")
            AuditLogger.log_error(self.db, run_id, "agent_error", error_msg)
            self.recorder.end_run(run_id, status="error")
            return {
                "error": f"Unexpected error: {error_msg[:200]}",
                "status": "error",
                "run_id": run_id,
            }

    def _get_run_tokens(self, run_id: str) -> int:
        """Get total tokens used in a run"""
        try:
            run = self.db.query(AgentRun).filter_by(id=run_id).first()
            return run.total_tokens_used if run else 0
        except Exception:
            return 0

    def pause_run(self, run_id: str, checkpoint_step: int):
        self.recorder.pause_run(run_id, checkpoint_step)

    def resume_run(self, run_id: str) -> Dict[str, Any]:
        success = self.recorder.resume_run(run_id)
        if success:
            return {"status": "resumed", "run_id": run_id, "message": "Run resumed"}
        return {"error": "Could not resume run", "run_id": run_id}

    def cancel_run(self, run_id: str):
        self.recorder.update_run_status(run_id, "cancelled")
