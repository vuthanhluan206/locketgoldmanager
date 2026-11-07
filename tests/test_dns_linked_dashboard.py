"""Regression checks for the one-step linked DNS dashboard workflow."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.routers.dns_devices import DeviceInput, RenewInput, SetExpiryInput, create_linked_device, renew_device, set_device_expiry


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


def test_set_past_expiry_updates_linked_account_and_device():
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)
    coll = AsyncMock()
    coll.find_one.return_value = {
        "_id": "b" * 24, "label": "Test iPhone", "enabled": True,
        "locket_id": "sample_user", "expires_at": now + timedelta(days=10),
        "block_domains": []
    }
    coll.find_one_and_update.return_value = {
        **coll.find_one.return_value, "expires_at": past
    }
    accounts = AsyncMock()
    accounts.find_one.return_value = {"_id": "account"}
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(accounts=accounts)))
    with patch("app.routers.dns_devices.collection", return_value=coll):
        result = asyncio.run(set_device_expiry(
            "b" * 24, SetExpiryInput(expires_at=past), request
        ))
    assert result["expires_at"] == past
    accounts.update_one.assert_awaited_once_with(
        {"locket_id": "sample_user"}, {"$set": {"expires_date": past}}
    )
    assert coll.find_one_and_update.await_args.args[1] == {"$set": {"expires_at": past}}


def test_set_past_expiry_preserves_unlinked_account():
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)
    coll = AsyncMock()
    coll.find_one.return_value = {
        "_id": "c" * 24, "label": "Unlinked", "enabled": True,
        "expires_at": now + timedelta(days=10), "block_domains": []
    }
    coll.find_one_and_update.return_value = {
        **coll.find_one.return_value, "expires_at": past
    }
    accounts = AsyncMock()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(accounts=accounts)))
    with patch("app.routers.dns_devices.collection", return_value=coll):
        result = asyncio.run(set_device_expiry(
            "c" * 24, SetExpiryInput(expires_at=past), request
        ))
    assert result["expires_at"] == past
    accounts.update_one.assert_not_awaited()
