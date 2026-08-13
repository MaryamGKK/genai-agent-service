import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.6-27b")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agent.db")
    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "10"))
    RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "15"))
    TOOL_TIMEOUT_SECS = int(os.getenv("TOOL_TIMEOUT_SECS", "30"))
    SESSION_EXPIRY_HOURS = int(os.getenv("SESSION_EXPIRY_HOURS", "24"))
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    ALLOW_WRITE_OPERATIONS = os.getenv("ALLOW_WRITE_OPERATIONS", "True").lower() == "true"


config = Config()
