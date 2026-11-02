from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pymongo.errors import DuplicateKeyError
from .config import get_settings
from .database import get_accounts
from .models import AccountId, AccountInput, AccountOutput, subscriber_response
from .profile import build_profile
from .security import require_admin, valid_token

router = APIRouter()
WEB = Path(__file__).resolve().parent.parent / 'web'
Accounts = Annotated[object, Depends(get_accounts)]


@router.get('/', response_class=HTMLResponse, include_in_schema=False)
async def home(admin: str | None = None):
    if admin is not None and not valid_token(admin):
        raise HTTPException(404, 'Not found')
    # The admin markup is never included in the public response.
    page = (WEB / 'index.html').read_text(encoding='utf-8')
    panel = (WEB / 'admin.html').read_text(encoding='utf-8') if admin is not None else ''
    return HTMLResponse(page.replace('<!-- ADMIN_PANEL -->', panel))


@router.get('/profile.mobileconfig')
async def download_profile():
    return Response(build_profile(get_settings()), media_type='application/x-apple-aspen-config',
                    headers={'Content-Disposition': 'attachment; filename="locket.mobileconfig"'})


@router.get('/v1/subscribers/{account_id}')
async def subscriber(account_id: AccountId, accounts: Accounts):
    account = await accounts.find_one({'locket_id': account_id}, {'_id': 0})
    return subscriber_response(account_id, account, datetime.now(timezone.utc))


admin_router = APIRouter(prefix='/admin', dependencies=[Depends(require_admin)])


@admin_router.post('/add-account', response_model=AccountOutput)
async def upsert_account(data: AccountInput, accounts: Accounts):
    document = data.model_dump()
    try:
        await accounts.update_one({'locket_id': data.locket_id}, {'$set': document}, upsert=True)
    except DuplicateKeyError:
        await accounts.update_one({'locket_id': data.locket_id}, {'$set': document})
    return document


@admin_router.get('/accounts', response_model=list[AccountOutput])
async def list_accounts(accounts: Accounts, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return await accounts.find({}, {'_id': 0}).sort('locket_id', 1).skip(skip).limit(limit).to_list(length=limit)


@admin_router.delete('/accounts/{account_id}', status_code=204)
async def delete_account(account_id: AccountId, accounts: Accounts):
    result = await accounts.delete_one({'locket_id': account_id})
    if not result.deleted_count:
        raise HTTPException(404, 'Account not found')
    return Response(status_code=204)
