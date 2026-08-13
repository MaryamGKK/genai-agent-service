from typing import Dict, Any, Callable, Optional, Tuple, List
from sqlalchemy.orm import Session
from db.models import ToolDefinition, ToolAudit
from security.validators import ToolArgumentValidator
from datetime import datetime
import time


class ToolRegistry:
    """Registry for LLM tools with DB-backed schemas"""

    def __init__(self, db: Session):
        self.db = db
        self.tools: Dict[str, Callable] = {}
        self.schemas: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str):
        """Decorator to register a tool implementation"""

        def decorator(func: Callable):
            self.tools[name] = func
            return func

        return decorator

    def load_schemas_from_db(self) -> bool:
        """Load tool parameter schemas from database. Returns success status"""
        try:
            tool_defs = self.db.query(ToolDefinition).filter_by(enabled=True).all()

            for tool_def in tool_defs:
                self.schemas[tool_def.name] = {
                    "name": tool_def.name,
                    "description": tool_def.description,
                    "parameters": tool_def.parameters_schema,
                }

            return len(self.schemas) > 0
        except Exception as e:
            print(f"Error loading tool schemas from DB: {e}")
            return False

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Get all tool schemas as Gemini function_declarations"""
        schemas = []
        for name, schema in self.schemas.items():
            schemas.append(
                {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                }
            )
        return schemas

    def validate_args(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate arguments for a tool. Returns (is_valid, error_msg)"""
        return ToolArgumentValidator.validate_args(tool_name, args)

    def execute(
        self, tool_name: str, args: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
        """
        Execute a tool with error handling.
        Returns (result, error_msg, duration_ms)
        """

        start_time = time.time()

        # Validate arguments first
        is_valid, validation_error = self.validate_args(tool_name, args)
        if not is_valid:
            duration_ms = int((time.time() - start_time) * 1000)
            return None, validation_error, duration_ms

        # Check if tool exists
        if tool_name not in self.tools:
            duration_ms = int((time.time() - start_time) * 1000)
            return None, f"Tool '{tool_name}' not found", duration_ms

        try:
            # Execute the tool
            result = self.tools[tool_name](**args)
            duration_ms = int((time.time() - start_time) * 1000)

            # Update tool audit
            self._update_tool_audit(tool_name, duration_ms)

            return result, None, duration_ms

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            return None, error_msg, duration_ms

    def _update_tool_audit(self, tool_name: str, duration_ms: int):
        """Update tool audit statistics"""
        try:
            audit = self.db.query(ToolAudit).filter_by(tool_name=tool_name).first()

            if audit:
                audit.total_calls += 1
                audit.total_duration_ms += duration_ms
                audit.avg_duration_ms = audit.total_duration_ms / audit.total_calls
                audit.last_called_at = datetime.utcnow()
            else:
                audit = ToolAudit(
                    tool_name=tool_name,
                    total_calls=1,
                    total_duration_ms=duration_ms,
                    avg_duration_ms=duration_ms,
                    last_called_at=datetime.utcnow(),
                )
                self.db.add(audit)

            self.db.commit()
        except Exception as e:
            print(f"Error updating tool audit: {e}")

    def __len__(self) -> int:
        return len(self.tools)

    def __repr__(self) -> str:
        return f"ToolRegistry({len(self.tools)} tools)"
