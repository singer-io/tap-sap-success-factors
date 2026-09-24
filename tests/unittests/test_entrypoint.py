import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import tap_sap_success_factors


class TestDoDiscover(unittest.TestCase):

    def test_writes_catalog_to_stdout(self):
        client = Mock()
        fake_catalog = Mock()
        fake_catalog.to_dict.return_value = {"streams": []}

        with patch("tap_sap_success_factors.discover", return_value=fake_catalog):
            with patch("json.dump") as dump_patch:
                tap_sap_success_factors.do_discover(client)
                dump_patch.assert_called_once()


class TestMain(unittest.TestCase):

    def test_discover_branch(self):
        parsed = SimpleNamespace(
            config={"api_server": "https://example.com", "start_date": "2024-01-01T00:00:00Z", "access_token": "abc"},
            state={},
            discover=True,
            catalog=None,
        )

        with patch("singer.utils.parse_args", return_value=parsed):
            with patch("tap_sap_success_factors.SAPSuccessFactorsClient") as client_cls:
                client_ctx = Mock()
                client_cls.return_value.__enter__.return_value = client_ctx
                with patch("tap_sap_success_factors.do_discover") as discover_patch:
                    tap_sap_success_factors.main()
                    discover_patch.assert_called_once_with(client_ctx)

    def test_sync_branch(self):
        parsed = SimpleNamespace(
            config={"api_server": "https://example.com", "start_date": "2024-01-01T00:00:00Z", "access_token": "abc"},
            state={"bookmarks": {}},
            discover=False,
            catalog=Mock(),
        )

        with patch("singer.utils.parse_args", return_value=parsed):
            with patch("tap_sap_success_factors.SAPSuccessFactorsClient") as client_cls:
                client_ctx = Mock()
                client_cls.return_value.__enter__.return_value = client_ctx
                with patch("tap_sap_success_factors.sync") as sync_patch:
                    tap_sap_success_factors.main()
                    sync_patch.assert_called_once()


class TestValidateAuthConfig(unittest.TestCase):

    def test_basic_auth_method_requires_username_password(self):
        with self.assertRaises(Exception):
            tap_sap_success_factors._validate_auth_config(
                {"auth_method": "basic_auth", "username": "user"}
            )

    def test_basic_auth_method_with_credentials_passes(self):
        tap_sap_success_factors._validate_auth_config(
            {"auth_method": "basic_auth", "username": "user", "password": "pw"}
        )

    def test_saml_bearer_auth_method_requires_all_keys(self):
        with self.assertRaises(Exception):
            tap_sap_success_factors._validate_auth_config(
                {"auth_method": "saml_bearer_oauth", "client_id": "cid"}
            )

    def test_saml_bearer_auth_method_with_all_keys_passes(self):
        tap_sap_success_factors._validate_auth_config(
            {
                "auth_method": "saml_bearer_oauth",
                "client_id": "cid",
                "user_id": "uid",
                "company_id": "co",
                "private_key": "key",
            }
        )

    def test_legacy_config_infers_basic_auth(self):
        tap_sap_success_factors._validate_auth_config(
            {"username": "user", "password": "pw"}
        )

    def test_legacy_config_infers_saml_bearer(self):
        tap_sap_success_factors._validate_auth_config(
            {
                "client_id": "cid",
                "user_id": "uid",
                "company_id": "co",
                "private_key": "key",
            }
        )

    def test_legacy_config_with_neither_complete_set_raises(self):
        with self.assertRaises(Exception):
            tap_sap_success_factors._validate_auth_config({"client_id": "cid"})
