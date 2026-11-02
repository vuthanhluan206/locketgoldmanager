from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from pymongo import AsyncMongoClient
from .config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    client = AsyncMongoClient(settings.mongodb_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
    try:
        await client.admin.command('ping')
        app.state.accounts = client[settings.mongodb_database].accounts
        # Unique IDs make concurrent renewals safe. Do not TTL-delete expired accounts.
        await app.state.accounts.create_index('locket_id', unique=True)
        yield
    finally:
        await client.close()


def get_accounts(request: Request):
    return request.app.state.accounts
