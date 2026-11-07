"""Regression checks for the one-step linked DNS dashboard workflow."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routers.dns_devices import DeviceInput, RenewInput, create_linked_device, renew_device


def test_one_step_linked_create_updates_managed_account_and_issues_profile():
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=12)
    accounts = AsyncMock()
    accounts.find_one.return_value = {"_id": "account"}
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(accounts=accounts)))
    data = DeviceInput(label="iPhone", locket_id="sample_user", expires_at=expiry)
    with patch("app.routers.dns_devices.dns_origin", return_value="https://dns.example.com"), patch(
        "app.routers.dns_devices.create_device", new_callable=AsyncMock
    ) as create:
        create.return_value = {"profile_download_url": "/dns/profiles/example.mobileconfig"}
        result = asyncio.run(create_linked_device(data, request))
    assert result["profile_download_url"].startswith("/dns/profiles/")
    accounts.update_one.assert_awaited_once_with(
        {"locket_id": "sample_user"},
        {"$setOnInsert": {"locket_id": "sample_user"}, "$max": {"expires_date": expiry}},
        upsert=True,
    )
    create.assert_awaited_once_with(data, request)


def test_renew_updates_linked_account_and_device_without_token_rotation():
    now = datetime.now(timezone.utc)
    existing = now + timedelta(days=4)
    coll = AsyncMock()
    coll.find_one.return_value = {
        "_id": "a" * 24, "label": "iPhone", "enabled": True,
        "locket_id": "sample_user", "expires_at": existing, "block_domains": []
    }
    coll.find_one_and_update.return_value = {
        **coll.find_one.return_value, "expires_at": existing + timedelta(days=30)
    }
    accounts = AsyncMock()
    accounts.find_one.return_value = {"_id": "account"}
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(accounts=accounts)))
    with patch("app.routers.dns_devices.collection", return_value=coll):
        result = asyncio.run(renew_device("a" * 24, RenewInput(days=30), request))
    assert result["locket_id"] == "sample_user"
    assert result["expires_at"] == existing + timedelta(days=30)
    accounts.update_one.assert_awaited_once_with(
        {"locket_id": "sample_user"}, {"$max": {"expires_date": existing + timedelta(days=30)}}
    )
    assert "$max" in coll.find_one_and_update.await_args.args[1]
