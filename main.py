from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from db.session import init_db
from db.seed import seed_database
from routes import agent, health, observe
import os
from pathlib import Path

# Initialize database
print("Initializing database...")
try:
    seed_database()
except Exception as e:
    print(f"Database already initialized or error: {e}")

# Create FastAPI app
app = FastAPI(
    title="GenAI Agent Service",
    description="LLM-driven agent that answers natural language queries by calling tools",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers FIRST
app.include_router(health.router)
app.include_router(agent.router)
app.include_router(observe.router)

# Direct route to index.html
@app.get("/")
async def root():
    return {"message": "GenAI Agent Service. Visit /static/ for UI or /docs for API documentation."}

# Serve static files LAST (must be after other routes)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")
    print(f"[OK] Static files mounted from {static_dir}")
else:
    print(f"[ERROR] Static directory not found at {static_dir}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
