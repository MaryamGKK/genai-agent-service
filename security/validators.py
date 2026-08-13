import re
from typing import Tuple, Optional, Any, Dict
from pydantic import BaseModel, ValidationError


class QueryValidator:
    """Validates user queries for safety and format"""

    # Regex patterns for dangerous operations
    DANGEROUS_PATTERNS = [
        r"<script[^>]*>",
        r"drop\s+table",
        r"delete\s+from",
        r"exec\s*\(",
        r"eval\s*\(",
        r"import\s+",
        r"__.*__",
        r"os\.",
        r"subprocess",
        r"system\s*\(",
    ]

    @staticmethod
    def validate_query(query: str) -> Tuple[bool, Optional[str]]:
        """Validate query string. Returns (is_valid, error_reason)"""

        if not query or not isinstance(query, str):
            return False, "Query must be a non-empty string"

        query_lower = query.lower().strip()

        # Check for dangerous patterns
        for pattern in QueryValidator.DANGEROUS_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return False, f"Query contains forbidden pattern: {pattern[:20]}..."

        # Character whitelist check (loose - allow most punctuation)
        # This prevents binary/null byte injection
        if any(ord(c) < 32 for c in query):
            return False, "Query contains invalid control characters"

        return True, None


class ToolArgumentValidator:
    """Validates tool arguments before execution"""

    # SQL injection patterns in string arguments
    SQL_INJECTION_PATTERNS = [
        r"drop\s+",
        r"delete\s+",
        r"insert\s+",
        r"update\s+",
        r"select\s+",
        r"exec\s*\(",
        r";\s*--",
        r"union\s+",
        r"'\s*or\s*'",
    ]

    @staticmethod
    def validate_integer_arg(value: Any, min_val: int = 1, max_val: int = 1000000) -> Tuple[bool, Optional[str]]:
        """Validate integer argument (like order_id, product_id)"""
        if not isinstance(value, int):
            return False, f"Expected integer, got {type(value).__name__}"

        if value < min_val or value > max_val:
            return False, f"Value {value} out of range [{min_val}, {max_val}]"

        return True, None

    @staticmethod
    def validate_string_arg(value: Any, min_len: int = 1, max_len: int = 1000) -> Tuple[bool, Optional[str]]:
        """Validate string argument (like message for support ticket)"""
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}"

        if len(value) < min_len:
            return False, f"String too short (min {min_len} chars)"

        if len(value) > max_len:
            return False, f"String too long (max {max_len} chars)"

        # Check for SQL injection patterns in strings
        value_lower = value.lower()
        for pattern in ToolArgumentValidator.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value_lower):
                return False, "String contains forbidden SQL patterns"

        return True, None

    @staticmethod
    def validate_args(tool_name: str, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate arguments for a specific tool. Returns (is_valid, error_reason)"""

        if tool_name == "get_order_status":
            if "order_id" not in args:
                return False, "Missing required argument: order_id"
            valid, err = ToolArgumentValidator.validate_integer_arg(args["order_id"], min_val=1, max_val=100000)
            return valid, err

        elif tool_name == "get_product_inventory":
            if "product_id" not in args:
                return False, "Missing required argument: product_id"
            valid, err = ToolArgumentValidator.validate_integer_arg(args["product_id"], min_val=1, max_val=100000)
            return valid, err

        elif tool_name == "list_customer_orders":
            if "customer_id" not in args:
                return False, "Missing required argument: customer_id"
            valid, err = ToolArgumentValidator.validate_integer_arg(args["customer_id"], min_val=1, max_val=100000)
            return valid, err

        elif tool_name == "create_support_ticket":
            if "customer_id" not in args:
                return False, "Missing required argument: customer_id"
            if "message" not in args:
                return False, "Missing required argument: message"

            valid, err = ToolArgumentValidator.validate_integer_arg(args["customer_id"], min_val=1, max_val=100000)
            if not valid:
                return valid, err

            valid, err = ToolArgumentValidator.validate_string_arg(args["message"], min_len=1, max_len=1000)
            return valid, err

        else:
            return False, f"Unknown tool: {tool_name}"


class SafetyClassifier:
    """Classifies queries for potential safety issues"""

    class SafetyScore(BaseModel):
        score: int  # 0-100
        is_safe: bool  # True if score < 70
        reason: str
        flags: list[str]

    SUSPICIOUS_PATTERNS = {
        "multiple_writes": (r"create.*create", 50),  # Multiple create operations
        "data_exfiltration": (r"list.*all|export|download", 30),  # Trying to get all data
        "cross_customer": (r"customer.*[0-9]+.*customer.*[0-9]+", 40),  # Accessing multiple customers
        "probe_system": (r"system|config|version|internal", 45),  # Probing system info
    }

    @staticmethod
    def classify(query: str) -> SafetyScore:
        """Classify a query for safety. Returns SafetyScore"""
        score = 0
        flags = []
        query_lower = query.lower()

        # Check for suspicious patterns
        for pattern_name, (pattern, weight) in SafetyClassifier.SUSPICIOUS_PATTERNS.items():
            if re.search(pattern, query_lower, re.IGNORECASE):
                score += weight
                flags.append(pattern_name)

        # Check for excessive question marks (repeated queries)
        if query_lower.count("?") > 3:
            score += 20
            flags.append("excessive_questions")

        # Determine if safe
        is_safe = score < 70

        reason = "Query appears safe"
        if score >= 70:
            reason = "Query flagged as potentially problematic: " + ", ".join(flags)
        elif score >= 40:
            reason = "Query may be suspicious, but allowed: " + ", ".join(flags)

        return SafetyClassifier.SafetyScore(
            score=min(score, 100),
            is_safe=is_safe,
            reason=reason,
            flags=flags,
        )
