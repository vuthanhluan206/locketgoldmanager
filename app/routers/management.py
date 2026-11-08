from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pymongo.errors import DuplicateKeyError
from ..database import get_accounts
from ..models import AccountInput, AccountOutput, AccountId
from ..security import require_admin
from ..config import get_settings

router = APIRouter()
WEB = Path(__file__).resolve().parent.parent.parent / 'web'
Accounts = Annotated[object, Depends(get_accounts)]

@router.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse(WEB / 'favicon.ico', media_type='image/vnd.microsoft.icon')

@router.get('/apple-touch-icon.png', include_in_schema=False)
@router.get('/apple-touch-icon-precomposed.png', include_in_schema=False)
async def apple_touch_icon():
    return FileResponse(WEB / 'apple-touch-icon.png', media_type='image/png')

@router.get('/', response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request):
    if 'admin' in request.query_params:
        raise HTTPException(400, 'URL tokens are disabled. Open /admin to sign in.')
    return render_page(False, request)

@router.get('/robots.txt', include_in_schema=False)
async def robots_txt():
    return PlainTextResponse("User-agent: *\nDisallow: /")

# PAC hẹp: Chỉ định tuyến đúng domain Locket và RevenueCat, tránh rò rỉ token/bảo mật
@router.get('/proxy.pac', response_class=Response)
@router.get('/proxy/proxy.pac', response_class=Response)
async def get_root_pac_file(request: Request):
    host = request.headers.get("host", "locketgold-premium.vercel.app")
    pac_content = f"""function FindProxyForURL(url, host) {{
    if (shExpMatch(host, "*locketcamera.com*") || shExpMatch(host, "*revenuecat.com*")) {{
        return "PROXY {host}";
    }}
    return "DIRECT";
}}"""
    return Response(content=pac_content, media_type="application/x-ns-proxy-autoconfig")

def render_page(admin: bool, request: Request) -> HTMLResponse:
    page = (WEB / 'index.html').read_text(encoding='utf-8')
    start, end = ('<!-- PUBLIC_START -->', '<!-- PUBLIC_END -->') if admin else ('<!-- ADMIN_START -->', '<!-- ADMIN_END -->')
    before, rest = page.split(start)
    _, after = rest.split(end)
    page = before + after
    page = page.replace('__TURNSTILE_SITE_KEY__', get_settings().turnstile_site_key)
    return HTMLResponse(page.replace('__NONCE__', request.state.csp_nonce).replace('__VIEW__', 'admin' if admin else 'public'))

@router.get('/admin', response_class=HTMLResponse, include_in_schema=False)
async def admin_login(request: Request):
    return render_page(True, request)

@router.get('/profile.mobileconfig')
async def download_profile(request: Request):
    if not request.app.state.profile:
        raise HTTPException(503, 'Cấu hình DNS hoặc chứng chỉ chưa sẵn sàng.')
    return Response(request.app.state.profile, media_type='application/x-apple-aspen-config',
                    headers={'Content-Disposition': 'attachment; filename="locket.mobileconfig"'})

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
async def list_accounts(accounts: Accounts, skip: int = Query(0, ge=0, le=10000), limit: int = Query(50, ge=1, le=100)):
    return await accounts.find({}, {'_id': 0}).sort('locket_id', 1).skip(skip).limit(limit).to_list(length=limit)

@admin_router.delete('/accounts/{account_id}', status_code=204)
async def delete_account(account_id: AccountId, accounts: Accounts):
    result = await accounts.delete_one({'locket_id': account_id})
    if not result.deleted_count:
        raise HTTPException(404, 'Account not found')
    return Response(status_code=204)