"""Run python -m app.bootstrap to configure an admin without saving a plaintext password."""
from getpass import getpass
from pathlib import Path
import re
import sys
import asyncio

from .passwords import hash_password, verify_password


async def sync_admin(settings):
    from motor.motor_asyncio import AsyncIOMotorClient
    from .database import admin_document

    client = AsyncIOMotorClient(
        settings.mongodb_uri.get_secret_value(),
        serverSelectionTimeoutMS=5000,
        timeoutMS=10000,
    )
    try:
        await client[settings.mongodb_database].admins.update_one(
            {'_id': 'superadmin'},
            {'$set': admin_document(settings)},
            upsert=True,
        )
    finally:
        client.close()


def update_env(values: dict[str, str]):
    path = Path('.env')
    text = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    for name, value in values.items():
        pattern = rf'(?m)^\s*{name}\s*=.*$'
        line = f"{name}='{value}'"
        text = re.sub(pattern, lambda match: line, text) if re.search(pattern, text) else text.rstrip('\n') + '\n' + line + '\n'
    text = re.sub(r'(?m)^\s*ADMIN_TOKEN\s*=.*\n?', '', text)
    path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    if sys.argv[1:] == ['--sync-db']:
        from .config import get_settings

        try:
            asyncio.run(sync_admin(get_settings()))
        except Exception as exc:
            raise SystemExit('Admin update failed: ' + type(exc).__name__) from None
        print('Updated admin in the configured MongoDB. Previous password sessions are invalidated.')
        raise SystemExit(0)
    if sys.argv[1:] == ['--check']:
        from .config import get_settings

        settings = get_settings()
        print('Configured email: ' + settings.superadmin_email)
        valid = verify_password(
            getpass('Password to verify (hidden): '),
            settings.superadmin_password_hash.get_secret_value(),
        )
        print('Password matches local configuration.' if valid else 'Password does NOT match local configuration.')
        raise SystemExit(0 if valid else 1)
    email = input('Superadmin email: ').strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9._+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", email):
        raise SystemExit('Invalid email')
    password = getpass('Superadmin password (12+ characters): ')
    if password != getpass('Confirm password: '):
        raise SystemExit('Passwords do not match')
    update_env({'SUPERADMIN_EMAIL': email, 'SUPERADMIN_PASSWORD_HASH': hash_password(password)})
    print('Updated .env. For an existing database, run python -m app.bootstrap --sync-db to apply credentials.')