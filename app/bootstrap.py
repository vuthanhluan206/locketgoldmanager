"""Run python -m app.bootstrap to configure an admin without saving a plaintext password."""
from getpass import getpass
from pathlib import Path
import re

from .passwords import hash_password


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
    email = input('Superadmin email: ').strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9._+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", email):
        raise SystemExit('Invalid email')
    password = getpass('Superadmin password (12+ characters): ')
    if password != getpass('Confirm password: '):
        raise SystemExit('Passwords do not match')
    update_env({'SUPERADMIN_EMAIL': email, 'SUPERADMIN_PASSWORD_HASH': hash_password(password)})
    print('Updated .env with email and salted password hash. Restart the server.')
