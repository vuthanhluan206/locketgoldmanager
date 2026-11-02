from datetime import date, datetime, timezone
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator

AccountId = Annotated[str, Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_$:@.\-]+$')]


class AccountInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    locket_id: AccountId
    expires_date: date

    @field_validator('expires_date')
    @classmethod
    def future_date(cls, value: date) -> date:
        if value < date.today():
            raise ValueError('expires_date must be today or in the future')
        return value


class AccountOutput(BaseModel):
    locket_id: str
    expires_date: date


def subscriber_response(account_id: str, account: dict | None) -> dict:
    today = date.today()
    active = False
    exp_date_obj = None

    if account and 'expires_date' in account:
        exp = account['expires_date']
        if isinstance(exp, datetime):
            exp_date_obj = exp.date()
        elif isinstance(exp, date):
            exp_date_obj = exp
        elif isinstance(exp, str):
            exp_date_obj = date.fromisoformat(exp[:10])
        
        if exp_date_obj and exp_date_obj >= today:
            active = True

    now = datetime.now(timezone.utc)
    
    # Quy đổi ngày hết hạn thành cuối ngày (23:59:59 UTC) để khớp định dạng JSON trả về cho app Locket
    if active and exp_date_obj:
        exp_dt = datetime(exp_date_obj.year, exp_date_obj.month, exp_date_obj.day, 23, 59, 59, tzinfo=timezone.utc)
        entitlement_expires = exp_dt.isoformat().replace('+00:00', 'Z')
    else:
        entitlement_expires = None

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