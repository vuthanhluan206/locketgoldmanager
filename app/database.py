from contextlib import asynccontextmanager
import hashlib
import logging
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography import x509
from fastapi import FastAPI, Request
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
from .config import get_settings
from .profile import build_profile

logger = logging.getLogger(__name__)


def admin_document(settings):
    password_hash = settings.superadmin_password_hash.get_secret_value()
    return {
        'email': settings.superadmin_email,
        'password_hash': password_hash,
        'auth_version': hashlib.sha256(password_hash.encode('ascii')).hexdigest(),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.profile = None
    try:
        app.state.profile = build_profile(settings) if settings.nextdns_id else None
    except (ValueError, OSError, x509.ExtensionNotFound, InvalidSignature, UnsupportedAlgorithm) as exc:
        logger.error('PROFILE_CONFIG_INVALID: %s; profile download disabled', type(exc).__name__)
    
    client = AsyncIOMotorClient(
        settings.mongodb_uri.get_secret_value(),
        tz_aware=True,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=5000,
        timeoutMS=5000,
        maxPoolSize=20,
    )
    db = client[settings.mongodb_database]

    app.state.accounts = db.accounts
    app.state.admins = db.admins
    app.state.sessions = db.sessions
    app.state.login_limits = db.login_limits

    try:
        await client.admin.command('ping')
        await app.state.accounts.create_index('locket_id', unique=True)
        await db.admins.create_index('email', unique=True)
        await db.sessions.create_index('expires_at', expireAfterSeconds=0)
        await db.login_limits.create_index('expires_at', expireAfterSeconds=0)
        await db.dns_devices.create_index('token_hash', unique=True)
        await db.dns_devices.create_index('locket_id')
        await db.dns_devices.create_index([('created_at', -1)])

        await db.admins.update_one(
            {'_id': 'superadmin'},
            {'$setOnInsert': admin_document(settings)},
            upsert=True,
        )
    except PyMongoError as exc:
        logger.error('DATABASE_STARTUP_UNAVAILABLE: %s', type(exc).__name__)
    
    try:
        yield
    finally:
        client.close()


def get_accounts(request: Request):
    return request.app.state.accounts