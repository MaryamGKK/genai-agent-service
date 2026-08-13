import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from db.session import SessionLocal, init_db
from db.seed import seed_database
from tools.registry import ToolRegistry
from tools.operations import ToolOperations, bind_tools_to_registry
from observability.recorder import AgentRunRecorder
from agent.loop import AgentOrchestrator
from security.validators import QueryValidator, SafetyClassifier, ToolArgumentValidator
from security.guardrails import Guardrails, RateLimiter
from security.language import LanguageDetector


@pytest.fixture(scope="session")
def db():
    """Set up test database"""
    init_db()
    seed_database()
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def registry(db):
    """Create tool registry with loaded schemas"""
    reg = ToolRegistry(db)
    reg.load_schemas_from_db()
    bind_tools_to_registry(reg, db)
    return reg


@pytest.fixture
def recorder(db):
    """Create recorder"""
    return AgentRunRecorder(db)


@pytest.fixture
def orchestrator(db, registry, recorder):
    """Create agent orchestrator for tests"""
    return AgentOrchestrator(registry, recorder, db)


# ============================================================
# 1. Query Validation Tests
# ============================================================
class TestQueryValidation:
    """Test input validation for user queries"""

    def test_valid_english_query(self):
        is_valid, error = QueryValidator.validate_query("What is the status of order 1?")
        assert is_valid
        assert error is None

    def test_valid_arabic_query(self):
        is_valid, error = QueryValidator.validate_query("ما حالة الطلب رقم 1؟")
        assert is_valid
        assert error is None

    def test_empty_query(self):
        is_valid, error = QueryValidator.validate_query("")
        assert not is_valid

    def test_none_query(self):
        is_valid, error = QueryValidator.validate_query(None)
        assert not is_valid

    def test_sql_injection_drop_table(self):
        is_valid, error = QueryValidator.validate_query("drop table customers")
        assert not is_valid
        assert "forbidden" in error.lower()

    def test_sql_injection_delete_from(self):
        is_valid, error = QueryValidator.validate_query("delete from orders")
        assert not is_valid

    def test_xss_script_tag(self):
        is_valid, error = QueryValidator.validate_query("<script>alert('xss')</script>")
        assert not is_valid

    def test_code_injection_eval(self):
        is_valid, error = QueryValidator.validate_query("eval('malicious code')")
        assert not is_valid

    def test_code_injection_exec(self):
        is_valid, error = QueryValidator.validate_query("exec(something)")
        assert not is_valid

    def test_os_injection(self):
        is_valid, error = QueryValidator.validate_query("os.system('rm -rf /')")
        assert not is_valid

    def test_subprocess_injection(self):
        is_valid, error = QueryValidator.validate_query("subprocess.call(['ls'])")
        assert not is_valid

    def test_dunder_injection(self):
        is_valid, error = QueryValidator.validate_query("__import__('os')")
        assert not is_valid

    def test_control_characters_rejected(self):
        is_valid, error = QueryValidator.validate_query("hello\x00world")
        assert not is_valid
        assert "control" in error.lower()

    def test_normal_punctuation_allowed(self):
        is_valid, error = QueryValidator.validate_query("What's order #1? (urgent!)")
        assert is_valid

    def test_long_valid_query(self):
        query = "What is the status of order 1? " * 100
        is_valid, error = QueryValidator.validate_query(query)
        assert is_valid


# ============================================================
# 2. Safety Classifier Tests
# ============================================================
class TestSafetyClassifier:
    """Test safety classification of queries"""

    def test_safe_simple_query(self):
        score = SafetyClassifier.classify("What are my orders?")
        assert score.is_safe
        assert score.score < 70

    def test_safe_order_status(self):
        score = SafetyClassifier.classify("What is the status of order 5?")
        assert score.is_safe

    def test_data_exfiltration_pattern(self):
        score = SafetyClassifier.classify("list all customers and export data")
        assert score.score > 0
        assert "data_exfiltration" in score.flags

    def test_multiple_write_operations(self):
        score = SafetyClassifier.classify("create a ticket and create another ticket")
        assert "multiple_writes" in score.flags

    def test_cross_customer_access(self):
        score = SafetyClassifier.classify("Show customer 1 orders and customer 2 orders")
        assert "cross_customer" in score.flags

    def test_system_probe(self):
        score = SafetyClassifier.classify("What version is the system running?")
        assert "probe_system" in score.flags

    def test_excessive_questions(self):
        score = SafetyClassifier.classify("Why? Why? Why? Why?")
        assert "excessive_questions" in score.flags

    def test_combined_flags_block(self):
        score = SafetyClassifier.classify(
            "list all customers and export data, system config version internal"
        )
        assert not score.is_safe
        assert score.score >= 70

    def test_score_capped_at_100(self):
        score = SafetyClassifier.classify(
            "list all export download system config create create ???? internal version"
        )
        assert score.score <= 100


# ============================================================
# 3. Tool Argument Validation Tests
# ============================================================
class TestToolArgumentValidation:
    """Test tool argument validation"""

    def test_valid_order_id(self):
        is_valid, err = ToolArgumentValidator.validate_args(
            "get_order_status", {"order_id": 1}
        )
        assert is_valid

    def test_missing_order_id(self):
        is_valid, err = ToolArgumentValidator.validate_args("get_order_status", {})
        assert not is_valid
        assert "order_id" in err

    def test_invalid_order_id_type(self):
        is_valid, err = ToolArgumentValidator.validate_integer_arg("not_a_number")
        assert not is_valid

    def test_order_id_out_of_range(self):
        is_valid, err = ToolArgumentValidator.validate_integer_arg(-1)
        assert not is_valid

    def test_order_id_zero(self):
        is_valid, err = ToolArgumentValidator.validate_integer_arg(0)
        assert not is_valid

    def test_valid_product_id(self):
        is_valid, err = ToolArgumentValidator.validate_args(
            "get_product_inventory", {"product_id": 3}
        )
        assert is_valid

    def test_missing_product_id(self):
        is_valid, err = ToolArgumentValidator.validate_args("get_product_inventory", {})
        assert not is_valid

    def test_valid_customer_id(self):
        is_valid, err = ToolArgumentValidator.validate_args(
            "list_customer_orders", {"customer_id": 1}
        )
        assert is_valid

    def test_missing_customer_id(self):
        is_valid, err = ToolArgumentValidator.validate_args("list_customer_orders", {})
        assert not is_valid

    def test_valid_support_ticket(self):
        is_valid, err = ToolArgumentValidator.validate_args(
            "create_support_ticket",
            {"customer_id": 1, "message": "My order is late"},
        )
        assert is_valid

    def test_ticket_missing_message(self):
        is_valid, err = ToolArgumentValidator.validate_args(
            "create_support_ticket", {"customer_id": 1}
        )
        assert not is_valid
        assert "message" in err

    def test_ticket_missing_customer_id(self):
        is_valid, err = ToolArgumentValidator.validate_args(
            "create_support_ticket", {"message": "help"}
        )
        assert not is_valid
        assert "customer_id" in err

    def test_ticket_empty_message(self):
        is_valid, err = ToolArgumentValidator.validate_string_arg("")
        assert not is_valid

    def test_ticket_message_too_long(self):
        is_valid, err = ToolArgumentValidator.validate_string_arg("x" * 1001)
        assert not is_valid

    def test_sql_injection_in_message(self):
        is_valid, err = ToolArgumentValidator.validate_string_arg("'; DROP TABLE orders; --")
        assert not is_valid

    def test_sql_union_in_message(self):
        is_valid, err = ToolArgumentValidator.validate_string_arg("1 UNION SELECT * FROM users")
        assert not is_valid

    def test_unknown_tool(self):
        is_valid, err = ToolArgumentValidator.validate_args("nonexistent_tool", {})
        assert not is_valid
        assert "Unknown tool" in err


# ============================================================
# 4. Language Detection Tests
# ============================================================
class TestLanguageDetection:
    """Test language detection for multilingual support"""

    def test_english_detection(self):
        code, name, conf = LanguageDetector.detect_language("What is the status of order 1?")
        assert code == "en"

    def test_arabic_msa_detection(self):
        code, name, conf = LanguageDetector.detect_language("ما هو حالة الطلب رقم واحد؟")
        assert code == "ar"

    def test_egyptian_arabic_enta_meen(self):
        code, name, conf = LanguageDetector.detect_language("انت مين؟")
        assert code == "ar-eg"

    def test_egyptian_arabic_ezay(self):
        code, name, conf = LanguageDetector.detect_language("إزاي حالك؟")
        assert code == "ar-eg"

    def test_egyptian_arabic_fein(self):
        code, name, conf = LanguageDetector.detect_language("الطلب فين؟")
        assert code == "ar-eg"

    def test_egyptian_arabic_ayeh(self):
        code, name, conf = LanguageDetector.detect_language("ايه حالة الطلب؟")
        assert code == "ar-eg"

    def test_egyptian_arabic_keda(self):
        code, name, conf = LanguageDetector.detect_language("تمام كده")
        assert code == "ar-eg"

    def test_egyptian_arabic_3ayez(self):
        code, name, conf = LanguageDetector.detect_language("عايز اعرف حالة الطلب")
        assert code == "ar-eg"

    def test_egyptian_arabic_delwa2ti(self):
        code, name, conf = LanguageDetector.detect_language("عايز الطلب دلوقتي")
        assert code == "ar-eg"

    def test_egyptian_arabic_meen(self):
        code, name, conf = LanguageDetector.detect_language("مين اللي طلب ده؟")
        assert code == "ar-eg"

    def test_short_arabic_fallback(self):
        code, name, conf = LanguageDetector.detect_language("مرحبا")
        assert code in ("ar", "ar-eg")

    def test_system_prompt_english(self):
        prompt = LanguageDetector.get_system_prompt("en")
        assert "English" in prompt
        assert "customer service" in prompt.lower()

    def test_system_prompt_arabic(self):
        prompt = LanguageDetector.get_system_prompt("ar")
        assert "عربية" in prompt or "العربية" in prompt

    def test_system_prompt_egyptian(self):
        prompt = LanguageDetector.get_system_prompt("ar-eg")
        assert "مصري" in prompt or "المصري" in prompt

    def test_unknown_language_defaults_english(self):
        prompt = LanguageDetector.get_system_prompt("zh")
        assert "English" in prompt

    def test_confidence_increases_with_indicators(self):
        _, _, conf1 = LanguageDetector.detect_language("فين")
        _, _, conf2 = LanguageDetector.detect_language("فين ايه تمام كده")
        assert conf2 > conf1

    def test_language_response_keys(self):
        resp = LanguageDetector.get_language_response("en", "error_generic")
        assert len(resp) > 0

    def test_language_response_arabic(self):
        resp = LanguageDetector.get_language_response("ar", "error_not_found")
        assert len(resp) > 0

    def test_language_response_invalid_key(self):
        resp = LanguageDetector.get_language_response("en", "nonexistent_key")
        assert resp == ""


# ============================================================
# 5. Rate Limiter Tests
# ============================================================
class TestRateLimiter:
    """Test rate limiting"""

    def test_allows_first_request(self):
        limiter = RateLimiter(rpm_limit=5)
        is_allowed, stats = limiter.is_allowed("10.0.0.1")
        assert is_allowed

    def test_blocks_after_limit(self):
        limiter = RateLimiter(rpm_limit=3)
        for _ in range(3):
            limiter.is_allowed("10.0.0.2")
        is_allowed, stats = limiter.is_allowed("10.0.0.2")
        assert not is_allowed

    def test_different_ips_independent(self):
        limiter = RateLimiter(rpm_limit=2)
        limiter.is_allowed("10.0.0.3")
        limiter.is_allowed("10.0.0.3")
        is_allowed, _ = limiter.is_allowed("10.0.0.4")
        assert is_allowed

    def test_stats_show_remaining(self):
        limiter = RateLimiter(rpm_limit=5)
        _, stats = limiter.is_allowed("10.0.0.5")
        assert stats["limit"] == 5
        assert stats["requests_remaining"] >= 0

    def test_reset_for_client(self):
        limiter = RateLimiter(rpm_limit=2)
        limiter.is_allowed("10.0.0.6")
        limiter.is_allowed("10.0.0.6")
        limiter.reset_for_client("10.0.0.6")
        is_allowed, _ = limiter.is_allowed("10.0.0.6")
        assert is_allowed


# ============================================================
# 6. Guardrails Tests
# ============================================================
class TestGuardrails:
    """Test agent guardrails and safety bounds"""

    def test_write_operations_allowed_by_default(self):
        is_allowed, msg = Guardrails.check_write_operation_allowed("create_support_ticket")
        assert is_allowed

    def test_read_operations_always_allowed(self):
        is_allowed, msg = Guardrails.check_write_operation_allowed("get_order_status")
        assert is_allowed

    def test_iteration_budget_within_limit(self):
        is_ok, msg = Guardrails.check_iteration_budget(5, max_iterations=10)
        assert is_ok

    def test_iteration_budget_exceeded(self):
        is_ok, msg = Guardrails.check_iteration_budget(11, max_iterations=10)
        assert not is_ok

    def test_iteration_budget_at_limit(self):
        is_ok, msg = Guardrails.check_iteration_budget(10, max_iterations=10)
        assert not is_ok

    def test_query_length_ok(self):
        is_ok, msg = Guardrails.check_query_length("short query")
        assert is_ok

    def test_query_length_exceeded(self):
        is_ok, msg = Guardrails.check_query_length("x" * 50001)
        assert not is_ok

    def test_tool_exists(self):
        is_ok, msg = Guardrails.check_tool_exists("get_order_status", ["get_order_status"])
        assert is_ok

    def test_tool_not_exists(self):
        is_ok, msg = Guardrails.check_tool_exists("hack_system", ["get_order_status"])
        assert not is_ok

    def test_concurrent_runs_within_limit(self):
        is_ok, msg = Guardrails.check_concurrent_runs("session1", active_runs=1)
        assert is_ok

    def test_concurrent_runs_exceeded(self):
        is_ok, msg = Guardrails.check_concurrent_runs("session1", active_runs=2)
        assert not is_ok

    def test_should_require_confirmation_write(self):
        assert Guardrails.should_require_confirmation("create_support_ticket")

    def test_should_not_require_confirmation_read(self):
        assert not Guardrails.should_require_confirmation("get_order_status")


# ============================================================
# 7. Tool Operations Tests (against real DB)
# ============================================================
class TestToolOperations:
    """Test tool implementations against seeded database"""

    def test_get_order_status_valid(self, db):
        result = ToolOperations.get_order_status(db, order_id=1)
        assert result["order_id"] == 1
        assert "status" in result
        assert "customer_name" in result
        assert "product_name" in result

    def test_get_order_status_invalid(self, db):
        with pytest.raises(ValueError, match="not found"):
            ToolOperations.get_order_status(db, order_id=9999)

    def test_get_product_inventory_valid(self, db):
        result = ToolOperations.get_product_inventory(db, product_id=1)
        assert result["product_id"] == 1
        assert "inventory" in result
        assert "price" in result
        assert "product_name" in result

    def test_get_product_inventory_invalid(self, db):
        with pytest.raises(ValueError, match="not found"):
            ToolOperations.get_product_inventory(db, product_id=9999)

    def test_list_customer_orders_valid(self, db):
        result = ToolOperations.list_customer_orders(db, customer_id=1)
        assert result["customer_id"] == 1
        assert "orders" in result
        assert isinstance(result["orders"], list)
        assert result["order_count"] > 0

    def test_list_customer_orders_invalid_customer(self, db):
        with pytest.raises(ValueError, match="not found"):
            ToolOperations.list_customer_orders(db, customer_id=9999)

    def test_create_support_ticket_valid(self, db):
        result = ToolOperations.create_support_ticket(db, customer_id=1, message="Test issue")
        assert "ticket_id" in result
        assert result["customer_id"] == 1
        assert result["message"] == "Test issue"
        assert result["status"] == "open"

    def test_create_support_ticket_invalid_customer(self, db):
        with pytest.raises(ValueError, match="not found"):
            ToolOperations.create_support_ticket(db, customer_id=9999, message="Test")

    def test_create_support_ticket_empty_message(self, db):
        with pytest.raises(ValueError, match="empty"):
            ToolOperations.create_support_ticket(db, customer_id=1, message="")

    def test_order_has_all_fields(self, db):
        result = ToolOperations.get_order_status(db, order_id=1)
        expected_fields = ["order_id", "customer_id", "customer_name", "product_id",
                          "product_name", "quantity", "status", "created_at"]
        for field in expected_fields:
            assert field in result, f"Missing field: {field}"

    def test_product_has_all_fields(self, db):
        result = ToolOperations.get_product_inventory(db, product_id=1)
        expected_fields = ["product_id", "product_name", "price", "inventory"]
        for field in expected_fields:
            assert field in result, f"Missing field: {field}"


# ============================================================
# 8. Tool Registry Tests
# ============================================================
class TestToolRegistry:
    """Test tool registry loading and execution"""

    def test_load_schemas_from_db(self, registry):
        schemas = registry.get_schemas()
        assert len(schemas) >= 4

    def test_schema_has_required_fields(self, registry):
        schemas = registry.get_schemas()
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema
            assert "parameters" in schema

    def test_execute_valid_tool(self, registry):
        result, error, duration = registry.execute("get_order_status", {"order_id": 1})
        assert result is not None
        assert error is None
        assert duration >= 0

    def test_execute_unknown_tool(self, registry):
        result, error, duration = registry.execute("nonexistent_tool", {})
        assert result is None
        assert "Unknown tool" in error

    def test_execute_invalid_args(self, registry):
        result, error, duration = registry.execute("get_order_status", {"order_id": -1})
        assert result is None
        assert error is not None

    def test_execute_missing_args(self, registry):
        result, error, duration = registry.execute("get_order_status", {})
        assert result is None
        assert "order_id" in error

    def test_execute_tool_not_found_error(self, registry):
        result, error, duration = registry.execute("get_order_status", {"order_id": 9999})
        assert result is None
        assert "not found" in error

    def test_registry_length(self, registry):
        assert len(registry) >= 4

    def test_registry_repr(self, registry):
        assert "ToolRegistry" in repr(registry)


# ============================================================
# 9. Observability Recorder Tests
# ============================================================
class TestRecorder:
    """Test observability recorder"""

    def test_create_session(self, recorder):
        session_id = recorder.create_session()
        assert session_id is not None
        assert len(session_id) > 0

    def test_start_run(self, recorder):
        run_id = recorder.start_run("Test query")
        assert run_id is not None

    def test_start_run_with_session(self, recorder):
        session_id = recorder.create_session()
        run_id = recorder.start_run("Test query", session_id=session_id)
        assert run_id is not None

    def test_record_step(self, recorder):
        run_id = recorder.start_run("Test query")
        recorder.record_step(
            run_id=run_id,
            step_num=1,
            tool_name="get_order_status",
            tool_input={"order_id": 1},
            tool_output={"order_id": 1, "status": "shipped"},
            duration_ms=100,
            input_tokens=50,
            output_tokens=30,
        )
        steps = recorder.get_steps(run_id)
        assert len(steps) == 1
        assert steps[0]["tool"] == "get_order_status"
        assert steps[0]["tokens"]["total"] == 80

    def test_end_run(self, recorder):
        run_id = recorder.start_run("Test query")
        recorder.end_run(
            run_id, final_answer="Test answer",
            iterations=2, status="success", total_duration_ms=500
        )
        details = recorder.get_run_details(run_id)
        assert details["status"] == "success"
        assert details["answer"] == "Test answer"

    def test_get_run_details(self, recorder):
        run_id = recorder.start_run("Details test query")
        recorder.end_run(run_id, final_answer="Answer", status="success")
        details = recorder.get_run_details(run_id)
        assert details is not None
        assert details["query"] == "Details test query"
        assert "tool_trace" in details
        assert "tokens" in details

    def test_get_run_details_nonexistent(self, recorder):
        details = recorder.get_run_details("nonexistent-id")
        assert details is None

    def test_get_recent_runs(self, recorder):
        recorder.start_run("Recent test 1")
        recorder.start_run("Recent test 2")
        recent = recorder.get_recent_runs(limit=5)
        assert len(recent) >= 2

    def test_pause_and_resume_run(self, recorder):
        run_id = recorder.start_run("Pause test")
        recorder.update_run_status(run_id, "running")
        recorder.pause_run(run_id, checkpoint_step=3)
        details = recorder.get_run_details(run_id)
        assert details["status"] == "interrupted"

        success = recorder.resume_run(run_id)
        assert success
        details = recorder.get_run_details(run_id)
        assert details["status"] == "running"

    def test_resume_non_interrupted_run_fails(self, recorder):
        run_id = recorder.start_run("Non-interrupted")
        recorder.end_run(run_id, status="success")
        success = recorder.resume_run(run_id)
        assert not success

    def test_token_aggregation(self, recorder):
        run_id = recorder.start_run("Token test")
        recorder.record_step(
            run_id=run_id, step_num=1, tool_name="tool_a",
            tool_input={}, tool_output={},
            input_tokens=100, output_tokens=50,
        )
        recorder.record_step(
            run_id=run_id, step_num=2, tool_name="tool_b",
            tool_input={}, tool_output={},
            input_tokens=200, output_tokens=100,
        )
        recorder.end_run(run_id, status="success")
        details = recorder.get_run_details(run_id)
        assert details["tokens"]["input"] == 300
        assert details["tokens"]["output"] == 150
        assert details["tokens"]["total"] == 450


# ============================================================
# 10. Multi-Step Agent Chaining (mocked LLM)
# ============================================================
class TestAgentChaining:
    """Test multi-step tool chaining with mocked LLM responses"""

    @pytest.mark.asyncio
    async def test_single_tool_call(self, orchestrator):
        """Test that agent handles a single tool call correctly"""
        tool_call_msg = MagicMock()
        tool_call_msg.content = None
        tool_call = MagicMock()
        tool_call.id = "call_001"
        tool_call.function.name = "get_order_status"
        tool_call.function.arguments = json.dumps({"order_id": 1})
        tool_call_msg.tool_calls = [tool_call]

        final_msg = MagicMock()
        final_msg.content = "Order 1 is shipped."
        final_msg.tool_calls = None

        response_1 = MagicMock()
        response_1.choices = [MagicMock()]
        response_1.choices[0].finish_reason = "tool_calls"
        response_1.choices[0].message = tool_call_msg
        response_1.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        response_2 = MagicMock()
        response_2.choices = [MagicMock()]
        response_2.choices[0].finish_reason = "stop"
        response_2.choices[0].message = final_msg
        response_2.usage = MagicMock(prompt_tokens=150, completion_tokens=30)

        with patch.object(orchestrator.client.chat.completions, "create",
                         side_effect=[response_1, response_2]):
            result = await orchestrator.run("What's the status of order 1?")

        assert result["status"] == "success"
        assert "Order 1" in result["answer"]
        assert len(result["tool_trace"]) == 1
        assert result["tool_trace"][0]["tool"] == "get_order_status"

    @pytest.mark.asyncio
    async def test_multi_step_chained_call(self, orchestrator):
        """Test agent chains two tool calls: get_order_status -> get_product_inventory"""
        # Step 1: LLM calls get_order_status
        tc1_msg = MagicMock()
        tc1_msg.content = None
        tc1 = MagicMock()
        tc1.id = "call_010"
        tc1.function.name = "get_order_status"
        tc1.function.arguments = json.dumps({"order_id": 1})
        tc1_msg.tool_calls = [tc1]

        resp1 = MagicMock()
        resp1.choices = [MagicMock()]
        resp1.choices[0].finish_reason = "tool_calls"
        resp1.choices[0].message = tc1_msg
        resp1.usage = MagicMock(prompt_tokens=100, completion_tokens=40)

        # Step 2: LLM sees order has product_id=1, calls get_product_inventory
        tc2_msg = MagicMock()
        tc2_msg.content = None
        tc2 = MagicMock()
        tc2.id = "call_011"
        tc2.function.name = "get_product_inventory"
        tc2.function.arguments = json.dumps({"product_id": 1})
        tc2_msg.tool_calls = [tc2]

        resp2 = MagicMock()
        resp2.choices = [MagicMock()]
        resp2.choices[0].finish_reason = "tool_calls"
        resp2.choices[0].message = tc2_msg
        resp2.usage = MagicMock(prompt_tokens=200, completion_tokens=40)

        # Step 3: LLM gives final answer
        final_msg = MagicMock()
        final_msg.content = "Order 1 is shipped. The product (Laptop) has 5 units in stock."
        final_msg.tool_calls = None

        resp3 = MagicMock()
        resp3.choices = [MagicMock()]
        resp3.choices[0].finish_reason = "stop"
        resp3.choices[0].message = final_msg
        resp3.usage = MagicMock(prompt_tokens=300, completion_tokens=50)

        with patch.object(orchestrator.client.chat.completions, "create",
                         side_effect=[resp1, resp2, resp3]):
            result = await orchestrator.run(
                "What's the status of order 1 and how much inventory does its product have?"
            )

        assert result["status"] == "success"
        assert result["iterations"] == 3
        assert len(result["tool_trace"]) == 2
        assert result["tool_trace"][0]["tool"] == "get_order_status"
        assert result["tool_trace"][1]["tool"] == "get_product_inventory"

    @pytest.mark.asyncio
    async def test_no_tool_call_direct_answer(self, orchestrator):
        """Test agent responds directly when no tool is needed (out-of-scope)"""
        final_msg = MagicMock()
        final_msg.content = "I can only help with orders, products, inventory, and support tickets."
        final_msg.tool_calls = None

        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].finish_reason = "stop"
        response.choices[0].message = final_msg
        response.usage = MagicMock(prompt_tokens=80, completion_tokens=20)

        with patch.object(orchestrator.client.chat.completions, "create",
                         return_value=response):
            result = await orchestrator.run("What is the weather today?")

        assert result["status"] == "success"
        assert len(result["tool_trace"]) == 0

    @pytest.mark.asyncio
    async def test_tool_call_with_error(self, orchestrator):
        """Test agent handles tool returning an error (invalid ID)"""
        tc_msg = MagicMock()
        tc_msg.content = None
        tc = MagicMock()
        tc.id = "call_err"
        tc.function.name = "get_order_status"
        tc.function.arguments = json.dumps({"order_id": 9999})
        tc_msg.tool_calls = [tc]

        resp1 = MagicMock()
        resp1.choices = [MagicMock()]
        resp1.choices[0].finish_reason = "tool_calls"
        resp1.choices[0].message = tc_msg
        resp1.usage = MagicMock(prompt_tokens=100, completion_tokens=30)

        final_msg = MagicMock()
        final_msg.content = "I couldn't find order 9999. Please check the order ID."
        final_msg.tool_calls = None

        resp2 = MagicMock()
        resp2.choices = [MagicMock()]
        resp2.choices[0].finish_reason = "stop"
        resp2.choices[0].message = final_msg
        resp2.usage = MagicMock(prompt_tokens=200, completion_tokens=30)

        with patch.object(orchestrator.client.chat.completions, "create",
                         side_effect=[resp1, resp2]):
            result = await orchestrator.run("What's the status of order 9999?")

        assert result["status"] == "success"
        assert "9999" in result["answer"]

    @pytest.mark.asyncio
    async def test_llm_api_error(self, orchestrator):
        """Test agent handles LLM API failure gracefully"""
        with patch.object(orchestrator.client.chat.completions, "create",
                         side_effect=Exception("API rate limit exceeded")):
            result = await orchestrator.run("What's order 1?")

        assert result["status"] == "error"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_request(self, orchestrator):
        """Test that rate limiter blocks excessive requests"""
        with patch("agent.loop.rate_limiter") as mock_limiter:
            mock_limiter.is_allowed.return_value = (False, {"requests_in_window": 15, "limit": 15, "requests_remaining": 0})
            result = await orchestrator.run("What's order 1?", client_ip="10.0.0.99")

        assert result["status"] == "rate_limited"

    @pytest.mark.asyncio
    async def test_validation_rejects_bad_input(self, orchestrator):
        """Test that dangerous queries are rejected before LLM call"""
        result = await orchestrator.run("drop table orders")
        assert result["status"] == "invalid_query"

    @pytest.mark.asyncio
    async def test_safety_blocks_suspicious_query(self, orchestrator):
        """Test that safety classifier blocks dangerous patterns"""
        result = await orchestrator.run(
            "list all customers export data system config version internal"
        )
        assert result["status"] == "security_check_failed"


# ============================================================
# 11. API Integration Tests (FastAPI TestClient)
# ============================================================
class TestAPIEndpoints:
    """Test REST API endpoints via FastAPI TestClient"""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        from main import app
        from httpx import AsyncClient, ASGITransport
        self.app = app
        self.transport = ASGITransport(app=app)

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        async with __import__("httpx").AsyncClient(
            transport=self.transport, base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_agent_empty_query(self):
        async with __import__("httpx").AsyncClient(
            transport=self.transport, base_url="http://test"
        ) as client:
            resp = await client.post("/agent/", json={"query": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") in ("invalid_query", "error")

    @pytest.mark.asyncio
    async def test_agent_missing_query_field(self):
        async with __import__("httpx").AsyncClient(
            transport=self.transport, base_url="http://test"
        ) as client:
            resp = await client.post("/agent/", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_observe_recent(self):
        async with __import__("httpx").AsyncClient(
            transport=self.transport, base_url="http://test"
        ) as client:
            resp = await client.get("/observe/recent")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_observe_stats(self):
        async with __import__("httpx").AsyncClient(
            transport=self.transport, base_url="http://test"
        ) as client:
            resp = await client.get("/observe/stats")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_observe_nonexistent_run(self):
        async with __import__("httpx").AsyncClient(
            transport=self.transport, base_url="http://test"
        ) as client:
            resp = await client.get("/observe/nonexistent-run-id")
        assert resp.status_code in (200, 404)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
