"""
main.py — FastAPI application entry point

Run:
    uvicorn main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()  # load .env file before anything else

from api.chat import router as chat_router
from api.conversations import router as conversations_router
from api.providers import router as providers_router
from api.skills import router as skills_router
from db.storage import init_db
from core.skill_loader import sync_skills_to_db, reload_skills


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await sync_skills_to_db()
    await reload_skills()
    yield


app = FastAPI(
    title="Agent Template",
    description="Pluggable AI agent framework — add providers & skills, start chatting.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(providers_router)
app.include_router(skills_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
