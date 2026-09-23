import base64
import unittest
from datetime import timedelta
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from tap_sap_success_factors.saml_assertion import (
    AssertionStrategy, AssertionStrategyFactory, SAMLBearerAssertionStrategy)

TEST_PRIVATE_KEY_PEM = (
    rsa.generate_private_key(public_exponent=65537, key_size=2048)
    .private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    .decode("utf-8")
)


def _config(**overrides):
    config = {
        "client_id": "cid",
        "user_id": "uid",
        "api_server": "https://example.com",
        "private_key": TEST_PRIVATE_KEY_PEM,
    }
    config.update(overrides)
    return config


# ---------------------------------------------------------------------------
# SAMLBearerAssertionStrategy — get/set assertion & expiry
# ---------------------------------------------------------------------------

class TestAssertionAndExpiryAccessors(unittest.TestCase):

    def test_assertion_defaults_to_none(self):
        strategy = SAMLBearerAssertionStrategy(_config())
        self.assertIsNone(strategy.get_assertion())
        self.assertIsNone(strategy.get_assertion_expiry())

    def test_set_assertion_stores_value(self):
        strategy = SAMLBearerAssertionStrategy(_config())
        strategy.set_assertion("my-assertion")
        self.assertEqual(strategy.get_assertion(), "my-assertion")

    def test_set_assertion_expiry_uses_default_window(self):
        strategy = SAMLBearerAssertionStrategy(_config())
        before = strategy.get_assertion_expiry()
        strategy.set_assertion_expiry()
        self.assertIsNone(before)
        self.assertIsNotNone(strategy.get_assertion_expiry())

    def test_set_assertion_expiry_accepts_custom_window(self):
        strategy = SAMLBearerAssertionStrategy(_config())
        strategy.set_assertion_expiry(timedelta(minutes=5))
        strategy.set_assertion(None)  # does not touch expiry
        self.assertIsNotNone(strategy.get_assertion_expiry())


# ---------------------------------------------------------------------------
# SAMLBearerAssertionStrategy — generate_assertion caching
# ---------------------------------------------------------------------------

class TestGenerateAssertionCaching(unittest.TestCase):

    def test_builds_and_caches_assertion(self):
        """A fresh strategy must build once, then reuse the cached value."""
        strategy = SAMLBearerAssertionStrategy(_config())
        with patch.object(
            strategy, "_build_assertion", wraps=strategy._build_assertion
        ) as mock_build:
            first = strategy.generate_assertion()
            second = strategy.generate_assertion()
            self.assertEqual(first, second)
            mock_build.assert_called_once()

    def test_regenerates_after_expiry(self):
        """Once the cached assertion is expired, generate_assertion must rebuild it."""
        strategy = SAMLBearerAssertionStrategy(_config())
        with patch.object(
            strategy, "_build_assertion", wraps=strategy._build_assertion
        ) as mock_build:
            strategy.generate_assertion()
            strategy.set_assertion_expiry(timedelta(minutes=-1))  # force expiry into the past
            strategy.generate_assertion()
            self.assertEqual(mock_build.call_count, 2)

    def test_generated_assertion_is_valid_base64(self):
        strategy = SAMLBearerAssertionStrategy(_config())
        assertion = strategy.generate_assertion()
        decoded = base64.b64decode(assertion)
        self.assertIn(b"urn:oasis:names:tc:SAML:2.0:assertion", decoded)
        self.assertIn(b"Signature", decoded)


# ---------------------------------------------------------------------------
# AssertionStrategyFactory
# ---------------------------------------------------------------------------

class TestAssertionStrategyFactory(unittest.TestCase):

    def test_create_defaults_to_saml_bearer_oauth(self):
        strategy = AssertionStrategyFactory.create(_config())
        self.assertIsInstance(strategy, SAMLBearerAssertionStrategy)

    def test_create_resolves_from_config_auth_method(self):
        strategy = AssertionStrategyFactory.create(
            _config(auth_method="saml_bearer_oauth")
        )
        self.assertIsInstance(strategy, SAMLBearerAssertionStrategy)

    def test_explicit_assertion_type_overrides_config(self):
        strategy = AssertionStrategyFactory.create(
            _config(auth_method="something_else"), assertion_type="saml_bearer_oauth"
        )
        self.assertIsInstance(strategy, SAMLBearerAssertionStrategy)

    def test_unknown_assertion_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            AssertionStrategyFactory.create(_config(), assertion_type="not_registered")

    def test_register_adds_new_strategy(self):
        class DummyStrategy(AssertionStrategy):
            def __init__(self, config):
                self.config = config

            def get_assertion(self):
                return "dummy"

            def set_assertion(self, assertion):
                pass

            def get_assertion_expiry(self):
                return None

            def set_assertion_expiry(self, expiry=None):
                pass

            def generate_assertion(self):
                return "dummy"

        AssertionStrategyFactory.register("dummy_method", DummyStrategy)
        try:
            strategy = AssertionStrategyFactory.create(
                _config(), assertion_type="dummy_method"
            )
            self.assertIsInstance(strategy, DummyStrategy)
            self.assertEqual(strategy.generate_assertion(), "dummy")
        finally:
            del AssertionStrategyFactory._registry["dummy_method"]
