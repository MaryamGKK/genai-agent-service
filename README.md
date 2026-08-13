# GenAI Agent Service

A Python backend service exposing a REST API where an LLM-driven agent answers user requests by calling internal "tools" (functions), chaining multiple calls when needed.

## Overview

This service uses Groq's Qwen 3.6 27B model (via OpenAI-compatible API) to:
- Understand natural language queries
- Select and execute appropriate tools (functions)
- Chain multiple tool calls together
- Return clear answers with full observability

**Key Features:**
- ✅ Multi-step tool chaining
- ✅ Input validation & security (SQL injection detection, safety classification)
- ✅ Rate limiting (15 req/min)
- ✅ Audit logging & observability
- ✅ Interrupt/resume capability
- ✅ DB-backed tool schemas
- ✅ Beautiful web UI for testing
- ✅ Docker containerization
- ✅ Full token & latency tracking

---

## Quick Start

### Prerequisites

- Docker & Docker Compose (recommended)
- OR Python 3.11+ with pip

### Option 1: Docker (Recommended)

```bash
# 1. Get your Groq API key from console.groq.com (free tier available)

# 2. Create .env file
cp .env.example .env
# Edit .env and add your LLM_API_KEY

# 3. Build and start
docker build -t genai-agent-service .
docker run -p 8000:8000 --env-file .env genai-agent-service

# Or with docker-compose:
docker-compose up --build

# 4. Open browser to http://localhost:8000/static/
```

### Option 2: Local Setup

```bash
# 1. Install dependencies (uv recommended for speed)
uv pip install -r requirements.txt
# Or with pip: pip install -r requirements.txt

# 2. Create .env
cp .env.example .env
# Edit .env with your LLM_API_KEY from console.groq.com

# 3. Initialize database
python db/seed.py

# 4. Run server
python -m uvicorn main:app --reload

# 5. Open browser to http://localhost:8000/static/
```

---

## Configuration

### Environment Variables

```env
# Required
LLM_API_KEY=your_api_key_here                   # From console.groq.com
LLM_MODEL=qwen/qwen3.6-27b                      # Groq model name
LLM_BASE_URL=https://api.groq.com/openai/v1     # OpenAI-compatible endpoint

# Optional
DATABASE_URL=sqlite:///./agent.db               # SQLite database path
MAX_ITERATIONS=10                                # Max agent loop iterations
RATE_LIMIT_RPM=15                                # Requests per minute
TOOL_TIMEOUT_SECS=30                             # Max seconds per tool call
SESSION_EXPIRY_HOURS=24                          # Session timeout
ALLOW_WRITE_OPERATIONS=True                      # Enable write tools (tickets)
DEBUG=False                                      # Verbose logging
```

### Getting a Groq API Key

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up or sign in
3. Navigate to API Keys
4. Create a new API key
5. Copy and paste into `.env` as `LLM_API_KEY`

**Free tier limits:**
- 30 requests per minute
- 14,400 requests per day
- No credit card required

---

## API Endpoints

### POST /agent

Ask the agent a natural language question.

**Request:**
```json
{
  "query": "What's the status of order 1234 and how much inventory is left?",
  "session_id": "optional-uuid-for-conversation-continuity"
}
```

**Response:**
```json
{
  "answer": "Order 1234 is shipped. Product has 45 units in stock.",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "success",
  "iterations": 2,
  "duration_ms": 2340,
  "tokens": {
    "total": 498
  },
  "tool_trace": [
    {
      "step": 1,
      "tool": "get_order_status",
      "input": {"order_id": 1234},
      "output": {"order_id": 1234, "status": "shipped", "product_id": 42, ...},
      "duration_ms": 45,
      "tokens": {"input": 150, "output": 78, "total": 228}
    },
    {
      "step": 2,
      "tool": "get_product_inventory",
      "input": {"product_id": 42},
      "output": {"product_id": 42, "inventory": 45, ...},
      "duration_ms": 32,
      "tokens": {"input": 192, "output": 78, "total": 270}
    }
  ]
}
```

### DELETE /agent/{run_id}

Cancel an ongoing run.

**Response:**
```json
{
  "status": "interrupted",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Run cancelled. You can resume with the same run_id."
}
```

### GET /agent/{run_id}/resume

Resume a paused run from checkpoint.

**Response:**
```json
{
  "status": "resumed",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Run resumed from checkpoint"
}
```

### GET /health

Check service status.

**Response:**
```json
{
  "status": "ok",
  "database": "connected",
  "rate_limiter": "active"
}
```

### GET /observe/{run_id}

Get full details of an agent run including tool trace and audit trail.

**Response:**
```json
{
  "run": {
    "run_id": "...",
    "query": "...",
    "answer": "...",
    "status": "success",
    "iterations": 2,
    "duration_ms": 2340,
    "tokens": {"input": 342, "output": 156, "total": 498},
    "tool_trace": [...]
  },
  "audit_trail": [
    {
      "timestamp": "2024-01-15T10:00:00",
      "event_type": "tool_call",
      "severity": "info",
      "details": {...}
    }
  ]
}
```

### GET /observe/recent?limit=10

Get recent runs.

### GET /observe/stats

Get system statistics (total runs, success rate, tokens used, etc).

### GET /audit?run_id=optional&event_type=optional

Get audit log entries for security/debugging.

### GET /

Web UI (visit http://localhost:8000/static/)

---

## Available Tools

The agent has access to 4 tools:

### 1. `get_order_status(order_id: int)`
Get the status and details of an order.

**Example:**
```
Agent: "What's the status of order 1?"
→ Calls: get_order_status(order_id=1)
→ Returns: {order_id: 1, status: "shipped", customer_id: 1, product_id: 1, ...}
```

### 2. `get_product_inventory(product_id: int)`
Get the current inventory level of a product.

**Example:**
```
Agent: "How much inventory does product 2 have?"
→ Calls: get_product_inventory(product_id=2)
→ Returns: {product_id: 2, product_name: "Mouse", inventory: 50, price: 29.99}
```

### 3. `list_customer_orders(customer_id: int)`
List all orders for a customer.

**Example:**
```
Agent: "What orders does customer 1 have?"
→ Calls: list_customer_orders(customer_id=1)
→ Returns: {customer_id: 1, orders: [...], order_count: 2}
```

### 4. `create_support_ticket(customer_id: int, message: str)` [WRITE]
Create a support ticket (write operation).

**Example:**
```
Agent: "Create a support ticket for customer 1 about a missing item"
→ Calls: create_support_ticket(customer_id=1, message="Missing item in order")
→ Returns: {ticket_id: 123, customer_id: 1, status: "open", ...}
```

---

## Sample Requests & Responses

### 1. Single-Tool Request

**Request:**
```bash
curl -X POST http://localhost:8000/agent/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the status of order 1?"}'
```

**Response:**
```json
{
  "answer": "Order 1 is currently **shipped**. It was placed by Alice Johnson for a Laptop (Product ID 1), with a quantity of 1.",
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "session_id": null,
  "status": "success",
  "language": {"code": "en", "name": "English", "confidence": 0.95},
  "iterations": 2,
  "duration_ms": 1850,
  "tokens": {"total": 342},
  "tool_trace": [
    {
      "step": 1,
      "tool": "get_order_status",
      "input": {"order_id": 1},
      "output": {
        "order_id": 1,
        "customer_id": 1,
        "customer_name": "Alice Johnson",
        "product_id": 1,
        "product_name": "Laptop",
        "quantity": 1,
        "status": "shipped",
        "created_at": "2024-01-15T10:00:00"
      },
      "error": null,
      "duration_ms": 12,
      "tokens": {"input": 180, "output": 78, "total": 258}
    }
  ]
}
```

### 2. Chained Multi-Tool Request

**Request:**
```bash
curl -X POST http://localhost:8000/agent/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the status of order 1, and how much of that product is left in stock?"}'
```

**Response:**
```json
{
  "answer": "Order 1 is **shipped**. It contains a Laptop (Product ID 1). There are currently **5 units** of Laptop left in stock, priced at $999.99 each.",
  "run_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "status": "success",
  "language": {"code": "en", "name": "English", "confidence": 0.95},
  "iterations": 3,
  "duration_ms": 3200,
  "tokens": {"total": 498},
  "tool_trace": [
    {
      "step": 1,
      "tool": "get_order_status",
      "input": {"order_id": 1},
      "output": {
        "order_id": 1,
        "customer_id": 1,
        "customer_name": "Alice Johnson",
        "product_id": 1,
        "product_name": "Laptop",
        "quantity": 1,
        "status": "shipped",
        "created_at": "2024-01-15T10:00:00"
      },
      "error": null,
      "duration_ms": 10,
      "tokens": {"input": 180, "output": 78, "total": 258}
    },
    {
      "step": 2,
      "tool": "get_product_inventory",
      "input": {"product_id": 1},
      "output": {
        "product_id": 1,
        "product_name": "Laptop",
        "price": 999.99,
        "inventory": 5
      },
      "error": null,
      "duration_ms": 8,
      "tokens": {"input": 240, "output": 60, "total": 300}
    }
  ]
}
```

### 3. "No Suitable Tool" Scenario

**Request:**
```bash
curl -X POST http://localhost:8000/agent/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather today?"}'
```

**Response:**
```json
{
  "answer": "I am a customer service assistant. My only function is to answer questions regarding customer orders, products, inventory, and support tickets. I cannot help with weather information. Please ask me about your orders, products, or support needs!",
  "run_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "status": "success",
  "language": {"code": "en", "name": "English", "confidence": 0.95},
  "iterations": 1,
  "duration_ms": 980,
  "tokens": {"total": 120},
  "tool_trace": []
}
```

### 4. Error Scenario (Invalid ID)

**Request:**
```bash
curl -X POST http://localhost:8000/agent/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the status of order 9999?"}'
```

**Response:**
```json
{
  "answer": "I was unable to find order 9999. Please verify the order ID and try again. Valid order IDs in our system range from 1 to 5.",
  "run_id": "d4e5f6a7-b8c9-0123-defa-234567890123",
  "status": "success",
  "language": {"code": "en", "name": "English", "confidence": 0.95},
  "iterations": 2,
  "duration_ms": 1500,
  "tokens": {"total": 280},
  "tool_trace": [
    {
      "step": 1,
      "tool": "get_order_status",
      "input": {"order_id": 9999},
      "output": null,
      "error": "Order 9999 not found",
      "duration_ms": 5,
      "tokens": {"input": 180, "output": 40, "total": 220}
    }
  ]
}
```

---

## Mock Data

The service includes pre-seeded data:

**Customers:**
- ID 1: Alice Johnson (alice@example.com)
- ID 2: Bob Smith (bob@example.com)
- ID 3: Carol White (carol@example.com)

**Products:**
- ID 1: Laptop ($999.99, 5 in stock)
- ID 2: Mouse ($29.99, 50 in stock)
- ID 3: Keyboard ($79.99, 25 in stock)
- ID 4: Monitor ($299.99, 10 in stock)
- ID 5: USB Cable ($9.99, 100 in stock)

**Orders:**
- Order 1: Customer 1 → Product 1 (Laptop) | Status: shipped
- Order 2: Customer 1 → Product 2 (Mouse) | Status: delivered
- Order 3: Customer 2 → Product 3 (Keyboard) | Status: pending
- Order 4: Customer 2 → Product 4 (Monitor) | Status: shipped
- Order 5: Customer 3 → Product 5 (USB Cable) | Status: delivered

---

## Security & Guardrails

### Input Validation
- Query character whitelist (prevents binary injection)
- SQL injection pattern detection
- Query length limits (configurable)
- Blocked patterns: `<script>`, `drop`, `exec()`, `eval()`, etc.

### Safety Classification
- Flags suspicious patterns (data exfiltration, cross-customer access)
- Safety score 0-100
- Auto-blocks queries with score ≥ 70

### Rate Limiting
- 15 requests per minute per IP
- Graceful backoff with informative errors

### Tool Argument Validation
- Type checking (int vs string)
- Range validation (e.g., order_id 1-100000)
- String length limits
- SQL injection detection in string args

### Audit Logging
All events logged to database:
- `query_received` - new request
- `tool_call` - executed tool
- `write_operation` - flagged for tickets
- `validation_failed` - invalid input
- `security_flag` - suspicious query
- `error_occurred` - failures

### Write Operation Protection
- Write operations (like `create_support_ticket`) flagged in audit
- Can be disabled via `ALLOW_WRITE_OPERATIONS=False`
- Logged separately with warning severity

---

## Architecture

### High-level Flow

```
User Query
    ↓
Validation (QueryValidator)
    ↓
Safety Check (SafetyClassifier)
    ↓
Agent Loop (max 10 iterations):
  1. Call LLM (Groq) with available tools
  2. Parse response for tool calls
  3. Validate tool arguments
  4. Execute tool via registry
  5. Log step with tokens/latency
  6. Feed results back to LLM
  7. Continue or exit
    ↓
Final Answer + Full Trace
```

### Component Breakdown

- **`config.py`** - Environment & settings
- **`db/models.py`** - SQLAlchemy ORM (11 tables)
- **`db/session.py`** - Database connection setup
- **`db/seed.py`** - Mock data initialization
- **`security/validators.py`** - Input validation
- **`security/audit.py`** - Audit logging
- **`security/guardrails.py`** - Rate limiting, bounds checking
- **`tools/registry.py`** - Tool registry (loads schemas from DB)
- **`tools/operations.py`** - Tool implementations
- **`agent/loop.py`** - Main orchestrator loop
- **`observability/recorder.py`** - Run tracking & replay
- **`routes/agent.py`** - /agent endpoint
- **`routes/health.py`** - /health endpoint
- **`routes/observe.py`** - Observability endpoints
- **`main.py`** - FastAPI app entry point
- **`static/index.html`** - Web UI

---

## Running Tests

```bash
# Run all 123 tests
pytest tests/ -v

# Specific test class
pytest tests/test_agent_loop.py::TestAgentChaining -v

# Specific test
pytest tests/test_agent_loop.py::TestLanguageDetection::test_egyptian_arabic_enta_meen -v
```

---

## Troubleshooting

### "LLM_API_KEY not found"
- Make sure `.env` file exists
- Check you've added your actual API key from console.groq.com
- API key should start with "gsk_..."

### "Rate limit exceeded"
- Free tier allows 15 requests per minute
- Wait 60 seconds and try again
- Or use a new IP address

### "Database is locked"
- SQLite doesn't support high concurrency
- This is expected in single-instance setup
- For production, use PostgreSQL

### "Tool not found"
- Make sure tool is defined in `tool_definitions` table
- Check tool name matches exactly

### "Order/Product/Customer not found"
- Use IDs from the mock data (1-5)
- Try "What's the status of order 1?"

---

## Limitations & Future Improvements

### Current Limitations
- SQLite single-writer concurrency (fine for testing)
- Rate limiting per IP (configurable)
- No persistent conversation history (sessions expire after 24h)
- Tool parameters loaded from DB at startup only

### Future Improvements
- [ ] PostgreSQL support for production concurrency
- [ ] Streaming intermediate reasoning steps
- [ ] Confirmation step before write operations
- [ ] Conversation memory (multi-turn context)
- [ ] Tool audit metrics dashboard
- [ ] Retry/backoff on tool failures
- [ ] Custom tool registration endpoint
- [ ] Langsmith/Honeycomb integration for observability

---

## Development

### Project Structure
```
agent_service/
├── agent/              # Agent orchestrator
├── tools/              # Tool registry & implementations
├── db/                 # Database models & session
├── security/           # Validation, audit, guardrails
├── observability/      # Run recording & metrics
├── routes/             # FastAPI routes
├── static/             # Web UI
├── tests/              # Test suite
├── config.py           # Configuration
├── main.py             # FastAPI entry point
├── requirements.txt    # Dependencies
├── Dockerfile          # Container build
├── docker-compose.yml  # Multi-container orchestration
└── README.md           # This file
```

### Key Design Decisions

**Groq + Qwen 3.6 27B**: Fast inference with excellent multilingual/Arabic support via OpenAI-compatible API
**Custom Agent Loop**: Full control over reasoning flow (not a framework wrapper)
**DB-backed Tool Schemas**: Easy to manage tool definitions without code changes
**SQLite for Simplicity**: Easy to seed, no external dependencies
**Audit Logging**: Every action tracked for replay & debugging
**Swappable LLM**: Change provider by updating 3 env vars (any OpenAI-compatible endpoint)
**uv in Docker**: Uses [uv](https://github.com/astral-sh/uv) for fast dependency installation in container builds

---

## License

MIT

---

## Questions?

See `/static/` for web UI or `/docs` for auto-generated API docs.

Built for interview assessment at Konecta. ✨
