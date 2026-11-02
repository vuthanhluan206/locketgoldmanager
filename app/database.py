from contextlib import asynccontextmanager
import hashlib
from fastapi import FastAPI, Request
from pymongo import AsyncMongoClient
from .config import get_settings
from .profile import build_profile


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Validate certificate once; no certificate file I/O during public downloads.
    app.state.profile = build_profile(settings) if settings.nextdns_id else None
    client = AsyncMongoClient(
        settings.mongodb_uri.get_secret_value(), tz_aware=True,
        serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
        socketTimeoutMS=5000, timeoutMS=5000, maxPoolSize=20,
    )
    try:
        await client.admin.command('ping')
        db = client[settings.mongodb_database]
        app.state.accounts = db.accounts
        app.state.admins = db.admins
        app.state.sessions = db.sessions
        # Unique IDs make concurrent renewals safe. Do not TTL-delete expired accounts.
        await app.state.accounts.create_index('locket_id', unique=True)
        await db.admins.create_index('email', unique=True)
        await db.sessions.create_index('expires_at', expireAfterSeconds=0)
        password_hash = settings.superadmin_password_hash.get_secret_value()
        # Env is authoritative for this single fixed account; changing its hash revokes all old sessions.
        await db.admins.update_one({'_id': 'superadmin'}, {'$set': {
            'email': settings.superadmin_email, 'password_hash': password_hash,
            'auth_version': hashlib.sha256(password_hash.encode('ascii')).hexdigest(),
        }}, upsert=True)
        yield
    finally:
        await client.close()


def get_accounts(request: Request):
    return request.app.state.accounts
