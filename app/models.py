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
    now = now if now is not None else datetime.now(timezone.utc)
    try:
        expiry = normalize_expiry(account['expires_date']) if account else None
    except (ValueError, TypeError, KeyError):
        expiry = None
    active = expiry is not None and expiry > now
    entitlement_expires = expiry.isoformat().replace('+00:00', 'Z') if active else None

    entitlement = {
        'expires_date': entitlement_expires,
        'product_identifier': 'gold'
    } if active else None

    return {
        'request_date': now.isoformat().replace('+00:00', 'Z'),
        'request_date_ms': int(now.timestamp() * 1000),
        'subscriber': {
            'original_app_user_id': account_id,
            'entitlements': {'Gold': entitlement} if active else {},
            'subscriptions': {}
        }
    }
