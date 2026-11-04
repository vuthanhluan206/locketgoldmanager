from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from ..database import get_accounts
from ..models import AccountId, subscriber_response
from ..security import require_subscriber_access

router = APIRouter(tags=["Subscribers"])
Accounts = Annotated[object, Depends(get_accounts)]

@router.get('/v1/subscribers/{account_id}', dependencies=[Depends(require_subscriber_access)])
async def subscriber(account_id: AccountId, accounts: Accounts):
    account = await accounts.find_one({'locket_id': account_id}, {'_id': 0})
    if not account:
        return subscriber_response(account_id, None)
    return subscriber_response(account_id, account)