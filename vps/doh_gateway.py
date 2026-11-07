"""Standalone RFC 8484 DNS-over-HTTPS gateway for Ubuntu VPS.

Owns no subscription logic. It obtains encrypted-DNS blocking policies from
the management API using a separate server-only credential.
"""
import asyncio
import base64
import logging
import os
import re
import time
from contextlib import asynccontextmanager

import dns.message
import dns.rcode
import httpx
from fastapi import FastAPI, HTTPException, Request, Response

log = logging.getLogger("doh-gateway")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
CACHE_TTL = 30
MAX_QUERY_BYTES = 4096
MAX_RESPONSE_BYTES = 65535


@asynccontextmanager
async def lifespan(app: FastAPI):
    endpoint = os.environ.get("MANAGER_API_ORIGIN", "").rstrip("/")
    key = os.environ.get("DNS_GATEWAY_API_TOKEN", "")
    upstream = os.environ.get("DOH_UPSTREAM", "https://cloudflare-dns.com/dns-query")
    if not endpoint.startswith("https://") or len(key) < 32 or not upstream.startswith("https://"):
        raise RuntimeError("MANAGER_API_ORIGIN (HTTPS), DNS_GATEWAY_API_TOKEN and HTTPS upstream required")
    if endpoint == upstream:
        raise RuntimeError("Manager and upstream must be separate")
    app.state.manager = endpoint
    app.state.key = key
    app.state.upstream = upstream
    app.state.cache = {}
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False)
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(title="Managed DoH Gateway", docs_url=None, redoc_url=None, lifespan=lifespan)


async def lookup_policy(request: Request, token: str) -> dict:
    state = request.app.state
    now = time.monotonic()
    cached = state.cache.get(token)
    if cached and cached[0] > now:
        return cached[1]
    # Fail-open for DNS reachability: manager outages should not break browsing.
    try:
        res = await state.http.post(
            f"{state.manager}/api/internal/dns/policy",
            headers={"Authorization": f"Bearer {state.key}"},
            json={"token": token},
        )
        res.raise_for_status()
        obj = res.json()
        if not isinstance(obj.get("block_domains"), list):
            raise ValueError("Invalid policy")
        policy = {
            "known": obj.get("known") is True,
            "block_domains": [
                x.lower().rstrip(".") for x in obj["block_domains"]
                if isinstance(x, str) and len(x) < 254
            ] if obj.get("active") is True else []
        }
        # Bound process memory for many devices.
        if len(state.cache) > 10000:
            state.cache.clear()
        state.cache[token] = (now + CACHE_TTL, policy)
        return policy
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.warning("Policy service unavailable: %s", type(exc).__name__)
        if cached:
            return cached[1]
        raise HTTPException(503, "Policy temporarily unavailable")


def denied_domain(domain: str, blocked: list[str]) -> bool:
    domain = domain.lower().rstrip(".")
    return any(domain == entry or domain.endswith("." + entry) for entry in blocked)


async def handle(request: Request, token: str) -> Response:
    if not TOKEN.fullmatch(token):
        raise HTTPException(404, "Unknown DNS configuration")
    if request.method == "GET":
        encoded = request.query_params.get("dns", "")
        if len(encoded) > 8192 or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", encoded):
            raise HTTPException(400, "Invalid DNS query")
        try:
            wire = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except (ValueError, base64.binascii.Error):
            raise HTTPException(400, "Invalid DNS query")
    else:
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/dns-message":
            raise HTTPException(415, "Expected application/dns-message")
        wire = await request.body()
    if len(wire) > MAX_QUERY_BYTES or not wire:
        raise HTTPException(413, "Invalid DNS message size")
    try:
        query = dns.message.from_wire(wire, ignore_trailing=False)
    except dns.exception.DNSException:
        raise HTTPException(400, "Invalid DNS message")
    if len(query.question) != 1:
        raise HTTPException(400, "Exactly one DNS question is required")
    policy = await lookup_policy(request, token)
    if not policy["known"]:
        raise HTTPException(403, "Unregistered DNS configuration")
    qname = query.question[0].name.to_text()
    if denied_domain(qname, policy["block_domains"]):
        answer = dns.message.make_response(query)
        answer.set_rcode(dns.rcode.NXDOMAIN)
        return Response(answer.to_wire(), media_type="application/dns-message",
                        headers={"Cache-Control": "no-store"})
    try:
        res = await request.app.state.http.post(
            request.app.state.upstream, content=wire,
            headers={"Content-Type": "application/dns-message", "Accept": "application/dns-message"}
        )
        res.raise_for_status()
        if not res.headers.get("content-type", "").lower().startswith("application/dns-message"):
            raise ValueError("Unexpected upstream media type")
        payload = res.content
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ValueError("Upstream response too large")
        decoded = dns.message.from_wire(payload)
        if decoded.id != query.id or decoded.question != query.question:
            raise ValueError("Upstream DNS response does not match query")
    except (httpx.HTTPError, dns.exception.DNSException, ValueError):
        # RFC 8484 HTTP 502 makes errors explicit.
        raise HTTPException(502, "Upstream DNS unavailable")
    return Response(payload, media_type="application/dns-message",
                    headers={"Cache-Control": "no-store"})


@app.api_route("/dns-query/{token}", methods=["GET", "POST"])
async def dns_query(request: Request, token: str):
    return await handle(request, token)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
