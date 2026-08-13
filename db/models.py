from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


# OPERATIONAL TABLES

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", back_populates="customer")
    tickets = relationship("SupportTicket", back_populates="customer")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    price = Column(Float)
    inventory = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", back_populates="product")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    quantity = Column(Integer, default=1)
    status = Column(String(50), default="pending", index=True)  # pending, shipped, delivered
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    customer = relationship("Customer", back_populates="orders")
    product = relationship("Product", back_populates="orders")


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    status = Column(String(50), default="open")  # open, in_progress, closed
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    customer = relationship("Customer", back_populates="tickets")


# AGENT / OBSERVABILITY TABLES

class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(255), index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_active_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="active")  # active, paused, expired
    expires_at = Column(DateTime)

    runs = relationship("AgentRun", back_populates="session")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("agent_sessions.id"), index=True, nullable=True)
    query = Column(Text, nullable=False)
    final_answer = Column(Text, nullable=True)
    status = Column(String(50), default="pending", index=True)  # pending, running, success, interrupted, failed
    total_iterations = Column(Integer, default=0)
    total_input_tokens = Column(Integer, default=0)
    total_output_tokens = Column(Integer, default=0)
    total_tokens_used = Column(Integer, default=0)
    total_duration_ms = Column(Integer, default=0)
    checkpoint_step = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)

    session = relationship("AgentSession", back_populates="runs")
    steps = relationship("AgentStep", back_populates="run", cascade="all, delete-orphan")
    audit_events = relationship("AuditLog", back_populates="run", cascade="all, delete-orphan")


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    tool_name = Column(String(255), nullable=False, index=True)
    tool_input = Column(JSON, nullable=False)
    tool_output = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    run = relationship("AgentRun", back_populates="steps")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String(36), ForeignKey("agent_runs.id"), index=True, nullable=True)
    event_type = Column(String(50), nullable=False, index=True)  # query, tool_call, error, security_flag, write_operation
    details = Column(JSON, nullable=False)
    severity = Column(String(20), default="info")  # info, warning, error
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    run = relationship("AgentRun", back_populates="audit_events")


# CONFIGURATION TABLES

class ToolDefinition(Base):
    __tablename__ = "tool_definitions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False)
    parameters_schema = Column(JSON, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ToolAudit(Base):
    __tablename__ = "tool_audit"

    id = Column(Integer, primary_key=True, index=True)
    tool_name = Column(String(255), ForeignKey("tool_definitions.name"), index=True, nullable=False)
    total_calls = Column(Integer, default=0)
    total_duration_ms = Column(Integer, default=0)
    avg_duration_ms = Column(Float, default=0.0)
    last_called_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


__all__ = [
    "Base",
    "Customer",
    "Product",
    "Order",
    "SupportTicket",
    "AgentSession",
    "AgentRun",
    "AgentStep",
    "AuditLog",
    "ToolDefinition",
    "ToolAudit",
]
