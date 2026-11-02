"""Salted, deliberately expensive password hashing using the standard library."""
import hashlib
import secrets

ITERATIONS = 600000


def validate_password_hash(encoded: str) -> tuple[int, bytes, bytes]:
    try:
        algorithm, count, salt, digest = encoded.split('$')
        iterations = int(count)
        if algorithm != 'pbkdf2_sha256' or not ITERATIONS <= iterations <= 2000000:
            raise ValueError
        salt_bytes, digest_bytes = bytes.fromhex(salt), bytes.fromhex(digest)
        if len(salt_bytes) != 16 or len(digest_bytes) != 32:
            raise ValueError
        return iterations, salt_bytes, digest_bytes
    except (ValueError, TypeError):
        raise ValueError('A valid PBKDF2-SHA256 password hash is required') from None


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError('Password must contain 12-256 characters')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        iterations, salt, expected = validate_password_hash(encoded)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return secrets.compare_digest(actual, expected)
