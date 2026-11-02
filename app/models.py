from datetime import datetime, timezone
from typing import Annotated
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

AccountId = Annotated[str, Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_$:@.\-]+$')]


class AccountInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    locket_id: AccountId
    expires_date: AwareDatetime

    @field_validator('expires_date')
    @classmethod
    def future_date(cls, value: datetime) -> datetime:
        value = value.astimezone(timezone.utc)
        if value <= datetime.now(timezone.utc):
            raise ValueError('expires_date must be in the future and include a timezone')
        return value


class AccountOutput(BaseModel):
    locket_id: str
    expires_date: datetime


def subscriber_response(account_id: str, account: dict | None, now: datetime) -> dict:
    active = account is not None and account['expires_date'] > now
    entitlement = {'expires_date': account['expires_date'].isoformat().replace('+00:00', 'Z'),
                   'product_identifier': 'gold'} if active else None
    # RevenueCat-like local contract, not a replacement for the RevenueCat service.
    return {'request_date': now.isoformat().replace('+00:00', 'Z'),
            'request_date_ms': int(now.timestamp() * 1000),
            'subscriber': {'original_app_user_id': account_id,
                           'entitlements': {'Gold': entitlement} if active else {},
                           'subscriptions': {}}}
