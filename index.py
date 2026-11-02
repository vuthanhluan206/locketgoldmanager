"""Vercel's native FastAPI entrypoint; local Uvicorn can keep using app.main:app."""
from app.main import app as app
