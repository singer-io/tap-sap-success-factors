import base64
import unittest
from unittest.mock import Mock

from tap_sap_success_factors.client import SAPSuccessFactorsClient
from tap_sap_success_factors.exceptions import SAPSuccessFactorsError


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

class DummyResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


# ---------------------------------------------------------------------------
# Basic auth tests
# ---------------------------------------------------------------------------

class TestBasicAuth(unittest.TestCase):

    def test_header_is_set_on_construction(self):
        """When username+password are supplied the client stores a Basic header."""
        client = SAPSuccessFactorsClient(
            {
                "api_server": "https://example.com",
                "start_date": "2024-01-01T00:00:00Z",
                "username": "test_username",
                "password": "not_a_real_password",
            }
        )
        self.assertIsNotNone(client._basic_auth_header)
        self.assertTrue(client._basic_auth_header.startswith("Basic "))
        decoded = base64.b64decode(client._basic_auth_header.split(" ", 1)[1]).decode()
        self.assertEqual(decoded, "test_username:not_a_real_password")

    def test_refresh_token_is_skipped(self):
        """refresh_access_token must be a no-op when basic auth is configured."""
        client = SAPSuccessFactorsClient(
            {
                "api_server": "https://example.com",
                "start_date": "2024-01-01T00:00:00Z",
                "username": "test_username",
                "password": "not_a_real_password",
            }
        )
        client._session = Mock()
        client.refresh_access_token()
        client._session.post.assert_not_called()

    def test_get_auth_header_returns_basic(self):
        """get_auth_header() must return the Basic header, not a Bearer token."""
        client = SAPSuccessFactorsClient(
            {
                "api_server": "https://example.com",
                "start_date": "2024-01-01T00:00:00Z",
                "username": "user",
                "password": "not_a_real_password",
            }
        )
        header = client.get_auth_header()
        self.assertTrue(header.startswith("Basic "))
        self.assertNotIn("Bearer", header)

    def test_basic_auth_takes_precedence_over_access_token(self):
        """When both username/password and access_token are present, Basic auth wins."""
        client = SAPSuccessFactorsClient(
            {
                "api_server": "https://example.com",
                "start_date": "2024-01-01T00:00:00Z",
                "username": "user",
                "password": "not_a_real_password",
                "access_token": "should_be_ignored",
            }
        )
        self.assertTrue(client.get_auth_header().startswith("Basic "))

    def test_authenticate_injects_basic_auth_header(self):
        """authenticate() must set Authorization: Basic ... on the headers dict."""
        client = SAPSuccessFactorsClient(
            {
                "api_server": "https://example.com",
                "start_date": "2024-01-01T00:00:00Z",
                "username": "user",
                "password": "not_a_real_password",
            }
        )
        headers, params = client.authenticate({}, {})
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertEqual(params["$format"], "json")


# ---------------------------------------------------------------------------
# OAuth / static token tests
# ---------------------------------------------------------------------------

class TestOAuthAndStaticToken(unittest.TestCase):

    def test_get_auth_header_returns_bearer_for_static_token(self):
        """get_auth_header() must return Bearer <token> when access_token is configured."""
        client = SAPSuccessFactorsClient(
            {
                "api_server": "https://example.com",
                "start_date": "2024-01-01T00:00:00Z",
                "access_token": "my_static_token",
            }
        )
        self.assertEqual(client.get_auth_header(), "Bearer my_static_token")

    def test_get_auth_header_returns_bearer_after_oauth_flow(self):
        """get_auth_header() must return Bearer <token> after a successful OAuth exchange."""
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
            200, {"access_token": "oauth_token", "expires_in": 3600}
        )
        client.refresh_access_token()
        self.assertEqual(client.get_auth_header(), "Bearer oauth_token")

    def test_refresh_access_token_with_static_token(self):
        client = SAPSuccessFactorsClient(
            {
                "api_server": "https://example.com",
                "start_date": "2024-01-01T00:00:00Z",
                "access_token": "static",
            }
        )
        client.refresh_access_token()
        self.assertEqual(client.get_access_token(), "static")

    def test_refresh_access_token_oauth_flow_success(self):
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
        self.assertEqual(client.get_access_token(), "oauth_token")

    def test_refresh_access_token_missing_oauth_endpoint(self):
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
        with self.assertRaises(SAPSuccessFactorsError):
            client.refresh_access_token()

    def test_refresh_access_token_missing_access_token_in_response(self):
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
        with self.assertRaises(SAPSuccessFactorsError):
            client.refresh_access_token()
