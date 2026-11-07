"""Expiry checks for locally managed access; never creates third-party Gold entitlements."""
from datetime import datetime, timezone

from app.models import normalize_expiry


def unexpired(value, now: datetime | None = None) -> bool:
    """Invalid/missing timestamps fail closed."""
    now = now or datetime.now(timezone.utc)
    try:
        return normalize_expiry(value) > now
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


async def device_active(device: dict | None, accounts, now: datetime | None = None) -> bool:
    """For linked devices, both the device expiry and managed account must be valid."""
    if not device or device.get("enabled") is not True or not unexpired(device.get("expires_at"), now):
        return False
    account_id = device.get("locket_id")
    if not account_id:
        return True  # Preserve existing unlinked DNS-only device behavior.
    account = await accounts.find_one({"locket_id": account_id}, {"expires_date": 1, "is_active": 1})
    return bool(account and account.get("is_active") is not False and unexpired(account.get("expires_date"), now))
