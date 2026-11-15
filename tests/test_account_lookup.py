from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_accounts
from app.routers.management import router


@pytest.fixture
def lookup_client():
    app = FastAPI()
    app.include_router(router)
    accounts = AsyncMock()
    app.dependency_overrides[get_accounts] = lambda: accounts
    with TestClient(app) as client:
        yield client, accounts


@pytest.mark.parametrize('query', [
    'alice', ' @alice ', 'https://locket.cam/alice',
    'locket.cam/alice/', 'https://locket.cam/alice?share=1',
])
@pytest.mark.parametrize('exists', [True, False])
def test_lookup_exact_database_match(lookup_client, query, exists):
    client, accounts = lookup_client
    accounts.find_one.return_value = {'_id': 'private'} if exists else None
    response = client.get('/api/accounts/lookup', params={'query': query})
    assert response.status_code == 200
    assert response.json() == {'exists': exists}
    accounts.find_one.assert_awaited_once_with({'locket_id': 'alice'}, {'_id': 1})
    accounts.update_one.assert_not_called()


@pytest.mark.parametrize('query', [
    '', ' ', 'https://example.com/alice', 'https://locket.cam.evil.test/alice',
    'https://locket.cam/', 'https://locket.cam/a/b', 'a' * 129,
    'https://locket.cam/%24%7Bbad%7D',
])
def test_invalid_lookup_does_not_query_database(lookup_client, query):
    client, accounts = lookup_client
    assert client.get('/api/accounts/lookup', params={'query': query}).status_code == 422
    accounts.find_one.assert_not_called()
