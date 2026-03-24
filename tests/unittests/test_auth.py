import base64
import unittest

from tap_sap_success_factors.auth import build_basic_auth_header, build_token_request


# ---------------------------------------------------------------------------
# build_basic_auth_header
# ---------------------------------------------------------------------------

class TestBuildBasicAuthHeader(unittest.TestCase):

    def test_returns_basic_token(self):
        """Valid username+password produces a correctly encoded Basic header."""
        header = build_basic_auth_header(
            {
                "username": "test_username",
                "password": "not_a_real_password",
            }
        )
        self.assertIsNotNone(header)
        self.assertTrue(header.startswith("Basic "))
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode()
        self.assertEqual(decoded, "test_username:not_a_real_password")

    def test_missing_password_returns_none(self):
        """Only username present — must return None (fall back to OAuth)."""
        self.assertIsNone(build_basic_auth_header({"username": "user"}))

    def test_missing_username_returns_none(self):
        """Only password present — must return None."""
        self.assertIsNone(build_basic_auth_header({"password": "pass"}))

    def test_empty_config_returns_none(self):
        """Empty config — must return None."""
        self.assertIsNone(build_basic_auth_header({}))

    def test_special_characters_encoded_correctly(self):
        """Colons and special chars in password must survive round-trip base64 encoding."""
        header = build_basic_auth_header(
            {"username": "user@company.com", "password": "p@ss:word!"}
        )
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode()
        self.assertEqual(decoded, "user@company.com:p@ss:word!")


# ---------------------------------------------------------------------------
# build_token_request
# ---------------------------------------------------------------------------

class TestBuildTokenRequest(unittest.TestCase):

    def test_access_token_mode(self):
        self.assertEqual(build_token_request({"access_token": "abc"}), {})

    def test_saml_mode(self):
        payload = build_token_request(
            {
                "client_id": "cid",
                "company_id": "co",
                "grant_type": "urn:ietf:params:oauth:grant-type:saml2-bearer",
                "saml_assertion": "assertion",
            }
        )
        self.assertEqual(payload["client_id"], "cid")
        self.assertEqual(payload["assertion"], "assertion")

    def test_refresh_token_mode(self):
        payload = build_token_request(
            {
                "client_id": "cid",
                "refresh_token": "refresh",
            }
        )
        self.assertEqual(
            payload,
            {
                "client_id": "cid",
                "grant_type": "refresh_token",
                "refresh_token": "refresh",
            },
        )
