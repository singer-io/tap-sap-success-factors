from unittest.mock import Mock

import pytest

from tap_sap_success_factors.client import SAPSuccessFactorsClient
from tap_sap_success_factors.exceptions import SAPSuccessFactorsError


class DummyResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_refresh_access_token_with_static_token():
    client = SAPSuccessFactorsClient(
        {
            "api_server": "https://example.com",
            "start_date": "2024-01-01T00:00:00Z",
            "access_token": "static",
        }
    )
    client.refresh_access_token()
    assert client.get_access_token() == "static"


def test_refresh_access_token_oauth_flow_success():
    client = SAPSuccessFactorsClient(
        {
            "api_server": "https://example.com",
            "start_date": "2024-01-01T00:00:00Z",
            "client_id": "cid",
            "saml_assertion": "assertion",
        }
    )
    client._session = Mock()
    client._session.post.return_value = DummyResponse(
        200,
        {"access_token": "oauth_token", "expires_in": 3600},
    )

    client.refresh_access_token()
    assert client.get_access_token() == "oauth_token"


def test_refresh_access_token_missing_oauth_endpoint():
    """When no credentials are supplied the OAuth POST fails and SAPSuccessFactorsError is raised."""
    client = SAPSuccessFactorsClient(
        {
            "api_server": "https://example.com",
            "start_date": "2024-01-01T00:00:00Z",
        }
    )
    client._session = Mock()
    client._session.post.return_value = DummyResponse(
        401,
        {"error": "unauthorized", "error_description": "Missing credentials"},
    )

    with pytest.raises(SAPSuccessFactorsError):
        client.refresh_access_token()


def test_refresh_access_token_missing_access_token_in_response():
    client = SAPSuccessFactorsClient(
        {
            "api_server": "https://example.com",
            "start_date": "2024-01-01T00:00:00Z",
            "client_id": "cid",
            "saml_assertion": "assertion",
        }
    )
    client._session = Mock()
    client._session.post.return_value = DummyResponse(200, {"expires_in": 3600})

    with pytest.raises(SAPSuccessFactorsError):
        client.refresh_access_token()
