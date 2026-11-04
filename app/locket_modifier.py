import asyncio
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .config import get_settings
from .models import normalize_expiry, subscriber_response
from .profile import build_profile

router = APIRouter(prefix="/proxy", tags=["Locket Proxy"])

UPSTREAM_TARGET = "https://api.locketcamera.com"


def _forward_upstream(url: str, body: bytes | None, headers: dict[str, str], method: str, timeout: float):
    req = urllib.request.Request(url, data=body if body else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as upstream_response:
            return (
                upstream_response.status,
                dict(upstream_response.headers.items()),
                upstream_response.read(),
            )
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()), e.read()


def _extract_locket_id(path: str, data: dict, user_token: str) -> str:
    parts = [p for p in path.split("/") if p]
    if "subscribers" in parts:
        idx = parts.index("subscribers")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if isinstance(data, dict):
        sub = data.get("subscriber")
        if isinstance(sub, dict) and sub.get("original_app_user_id"):
            return str(sub["original_app_user_id"])
        for key in ("locket_id", "uid", "user_id", "id"):
            if isinstance(data.get(key), str) and data[key]:
                return data[key]
        user_obj = data.get("user") or data.get("data")
        if isinstance(user_obj, dict):
            for key in ("uid", "user_id", "id", "locket_id"):
                if isinstance(user_obj.get(key), str) and user_obj[key]:
                    return user_obj[key]
    return user_token


@router.get("/install", response_class=Response)
async def download_proxy_profile(request: Request):
    profile_bytes = getattr(request.app.state, "profile", None)
    if not profile_bytes:
        settings = get_settings()
        if not settings.nextdns_id:
            raise HTTPException(503, "Chưa cấu hình NEXTDNS_ID trên server.")
        profile_bytes = build_profile(settings)
    return Response(
        content=profile_bytes,
        media_type="application/x-apple-aspen-config",
        headers={"Content-Disposition": 'attachment; filename="locket.mobileconfig"'},
    )


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def dynamic_reverse_proxy(request: Request, path: str):
    url = f"{UPSTREAM_TARGET}/{path}"
    query_params = str(request.url.query)
    if query_params:
        url += f"?{query_params}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers["Host"] = "api.locketcamera.com"

    method = request.method
    content_type_header = headers.get("content-type", "")
    auth_header = headers.get("authorization", "")
    user_token = auth_header.replace("Bearer ", "").strip()

    is_upload = method in ["POST", "PUT", "PATCH"] and (
        "multipart/form-data" in content_type_header
        or "octet-stream" in content_type_header
        or "video/" in content_type_header
        or "image/" in content_type_header
    )
    body = await request.body()
    timeout_limit = 60.0 if is_upload else 30.0

    try:
        upstream_status, upstream_headers, upstream_content = await asyncio.to_thread(
            _forward_upstream, url, body, headers, method, timeout_limit
        )
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"Bad Gateway to Upstream: {type(exc).__name__}"})

    response_headers = {
        k: v for k, v in upstream_headers.items()
        if k.lower() not in ["content-length", "transfer-encoding", "content-encoding"]
    }

    if is_upload:
        return Response(
            content=upstream_content,
            status_code=upstream_status,
            headers=response_headers,
            media_type=upstream_headers.get("content-type"),
        )

    content_type = upstream_headers.get("content-type", "")
    accounts_col = getattr(request.app.state, "accounts", None)
    viewers_col = getattr(request.app.state, "viewers_history", None)

    if "application/json" in content_type and upstream_content:
        try:
            data = json.loads(upstream_content.decode("utf-8"))

            if "moments" in path or "posts" in path or "viewer" in path:
                dynamic_viewers = []
                if viewers_col is not None and user_token:
                    try:
                        cursor = viewers_col.find({"token": user_token}).sort("viewed_at", -1).limit(10)
                        records = await cursor.to_list(length=10)
                        for record in records:
                            dynamic_viewers.append({
                                "user_id": str(record.get("viewer_id", "unknown_id")),
                                "username": record.get("username", "friend"),
                                "display_name": record.get("display_name", "Member"),
                                "viewed_at": record.get("viewed_at", "2026-06-06T15:00:00Z"),
                            })
                    except Exception:
                        pass

                if dynamic_viewers:
                    if isinstance(data, dict):
                        data["viewers"] = dynamic_viewers
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                item["viewers"] = dynamic_viewers

            elif "subscribers" in path or "user" in path:
                if isinstance(data, dict):
                    candidate_id = _extract_locket_id(path, data, user_token)
                    account_record = None
                    if accounts_col is not None and candidate_id:
                        try:
                            account_record = await accounts_col.find_one(
                                {"locket_id": candidate_id}, {"_id": 0}
                            )
                            if not account_record and user_token and user_token != candidate_id:
                                account_record = await accounts_col.find_one(
                                    {"locket_id": user_token}, {"_id": 0}
                                )
                        except Exception:
                            account_record = None

                    now = datetime.now(timezone.utc)
                    sub_payload = subscriber_response(candidate_id or "locket_user", account_record, now)
                    if "subscriber" not in data or not isinstance(data["subscriber"], dict):
                        data["subscriber"] = sub_payload["subscriber"]
                    else:
                        data["subscriber"]["entitlements"] = sub_payload["subscriber"]["entitlements"]
                        data["subscriber"]["subscriptions"] = sub_payload["subscriber"]["subscriptions"]

            return JSONResponse(content=data, status_code=upstream_status, headers=response_headers)
        except Exception:
            pass

    return Response(
        content=upstream_content,
        status_code=upstream_status,
        headers=response_headers,
        media_type=upstream_headers.get("content-type"),
    )