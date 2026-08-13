from datetime import datetime, timedelta
from typing import Dict, Tuple
from collections import defaultdict
from config import config


class RateLimiter:
    """Rate limiting for API requests (per IP, in-memory)"""

    def __init__(self, rpm_limit: int = 15):
        self.rpm_limit = rpm_limit
        self.requests: Dict[str, list[datetime]] = defaultdict(list)

    def is_allowed(self, client_ip: str) -> Tuple[bool, Dict[str, int]]:
        """
        Check if request is allowed for client IP.
        Returns (is_allowed, stats)
        """
        now = datetime.utcnow()
        one_minute_ago = now - timedelta(minutes=1)

        # Clean old requests
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip] if req_time > one_minute_ago
        ]

        # Check limit
        request_count = len(self.requests[client_ip])
        is_allowed = request_count < self.rpm_limit

        # Add current request if allowed
        if is_allowed:
            self.requests[client_ip].append(now)

        stats = {
            "requests_in_window": request_count,
            "limit": self.rpm_limit,
            "requests_remaining": max(0, self.rpm_limit - request_count - 1) if is_allowed else 0,
        }

        return is_allowed, stats

    def reset_for_client(self, client_ip: str):
        """Reset rate limit for a client (admin use)"""
        if client_ip in self.requests:
            del self.requests[client_ip]


class Guardrails:
    """Safety checks and bounds for agent behavior"""

    # Max concurrent operations per session
    MAX_CONCURRENT_RUNS = 2

    # Tool execution timeout
    TOOL_TIMEOUT_SECS = config.TOOL_TIMEOUT_SECS

    # Max iterations per run
    MAX_ITERATIONS = config.MAX_ITERATIONS

    # Session expiry
    SESSION_EXPIRY_HOURS = config.SESSION_EXPIRY_HOURS

    # Write operation flags
    WRITE_OPERATIONS = {"create_support_ticket"}

    @staticmethod
    def check_write_operation_allowed(tool_name: str) -> Tuple[bool, str]:
        """Check if write operation is allowed"""
        if tool_name not in Guardrails.WRITE_OPERATIONS:
            return True, ""

        if not config.ALLOW_WRITE_OPERATIONS:
            return False, "Write operations are disabled"

        return True, ""

    @staticmethod
    def check_tool_exists(tool_name: str, available_tools: list[str]) -> Tuple[bool, str]:
        """Check if tool is available"""
        if tool_name not in available_tools:
            return False, f"Tool '{tool_name}' is not available"
        return True, ""

    @staticmethod
    def check_query_length(query: str, max_length: int = 50000) -> Tuple[bool, str]:
        """Check if query is within length bounds"""
        if len(query) > max_length:
            return False, f"Query too long ({len(query)} > {max_length})"
        return True, ""

    @staticmethod
    def check_iteration_budget(current_iteration: int, max_iterations: int = MAX_ITERATIONS) -> Tuple[bool, str]:
        """Check if we have iterations remaining"""
        if current_iteration >= max_iterations:
            return False, f"Max iterations ({max_iterations}) reached"
        return True, ""

    @staticmethod
    def check_concurrent_runs(session_id: str, active_runs: int) -> Tuple[bool, str]:
        """Check if session has too many concurrent runs"""
        if active_runs >= Guardrails.MAX_CONCURRENT_RUNS:
            return False, f"Too many concurrent requests. Max: {Guardrails.MAX_CONCURRENT_RUNS}"
        return True, ""

    @staticmethod
    def should_require_confirmation(tool_name: str) -> bool:
        """Check if tool needs user confirmation before execution"""
        return tool_name in Guardrails.WRITE_OPERATIONS


# Global rate limiter instance
rate_limiter = RateLimiter(rpm_limit=config.RATE_LIMIT_RPM)
