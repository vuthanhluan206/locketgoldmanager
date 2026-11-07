from datetime import date, datetime, time, timezone
from typing import Annotated
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

AccountId = Annotated[str, Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_$:@.\-]+$')]


def normalize_expiry(value) -> datetime:
    if isinstance(value, str):
        value = date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value.replace('Z', '+00:00'))
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time(23, 59, 59), tzinfo=timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('expires_date must be a date or a datetime with timezone')
    return value.astimezone(timezone.utc)


class AccountInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    locket_id: AccountId
    expires_date: AwareDatetime

    @field_validator('expires_date', mode='before')
    @classmethod
    def parse_expiry(cls, value):
        return normalize_expiry(value)

    @field_validator('expires_date')
    @classmethod
    def future_date(cls, value: datetime) -> datetime:
        if value <= datetime.now(timezone.utc):
            raise ValueError('expires_date must be in the future')
        return value


class AccountOutput(BaseModel):
    locket_id: str
    expires_date: AwareDatetime


def subscriber_response(account_id: str, account: dict | None, now: datetime | None = None) -> dict:
    """Report this service's managed access without forging Locket Gold purchases.

    A locally configured expiry is NOT evidence of a paid third-party subscription.
    Keep the legacy subscriber response fields empty for compatibility and expose
    independent management status under 'managed_access'.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    try:
        expiry = normalize_expiry(account['expires_date']) if account else None
    except (ValueError, TypeError, KeyError):
        expiry = None

    active = bool(expiry is not None and expiry > now)
    now_str = now.isoformat().replace('+00:00', 'Z')
    expiry_str = expiry.isoformat().replace('+00:00', 'Z') if expiry else None
    return {
        'request_date': now_str,
        'request_date_ms': int(now.timestamp() * 1000),
        'subscriber': {
            'original_app_user_id': account_id,
            'entitlements': {},
            'subscriptions': {},
            'non_subscriptions': {},
        },
        'managed_access': {
            'active': active,
            'expires_at': expiry_str,
            'source': 'local_management',
            'gold_verified': False,
            'note': 'Managed access is not a verified Locket Gold subscription.',
        },
    }
