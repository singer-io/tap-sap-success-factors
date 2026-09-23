"""SAML assertion generation strategies for OAuth SAML2-Bearer grant.

    This module defines an abstract base class `AssertionStrategy` and a concrete
    implementation `SAMLBearerAssertionStrategy` for building, signing, and caching
    SAML 2.0 Bearer assertions.

    The Factory class `AssertionStrategyFactory` is used to create instances of the appropriate assertion strategy based on the configuration.
"""

import base64
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Type

from lxml import etree
from signxml import XMLSigner, methods
from singer import get_logger

LOGGER = get_logger()

ASSERTION_EXPIRY = timedelta(minutes=28)
ASSERTION_VALIDITY = timedelta(minutes=30)
SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"


class AssertionStrategy(ABC):
    """Interface implemented by every concrete assertion-generation strategy."""

    @abstractmethod
    def get_assertion(self):
        raise NotImplementedError

    @abstractmethod
    def set_assertion(self, assertion):
        raise NotImplementedError

    @abstractmethod
    def get_assertion_expiry(self):
        raise NotImplementedError

    @abstractmethod
    def set_assertion_expiry(self, expiry=None):
        raise NotImplementedError

    @abstractmethod
    def generate_assertion(self):
        """Return a cached assertion if still valid, otherwise build and cache a new one."""
        raise NotImplementedError


class SAMLBearerAssertionStrategy(AssertionStrategy):
    """Builds, signs and caches a SAML 2.0 Bearer assertion for the OAuth SAML2-Bearer grant."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.__assertion = None
        self.__assertion_expiry = None

    def get_assertion(self):
        return self.__assertion

    def set_assertion(self, assertion):
        self.__assertion = assertion

    def get_assertion_expiry(self):
        return self.__assertion_expiry

    def set_assertion_expiry(self, expiry=None):
        self.__assertion_expiry = datetime.now(tz=timezone.utc) + (expiry or ASSERTION_EXPIRY)

    def generate_assertion(self):
        expiry = self.get_assertion_expiry()
        if self.get_assertion() and expiry and expiry > datetime.now(tz=timezone.utc):
            LOGGER.info("Using cached assertion, expires at %s", expiry)
            return self.get_assertion()

        assertion = self._build_assertion()
        self.set_assertion(assertion)
        self.set_assertion_expiry()
        return assertion

    @staticmethod
    def _add_attribute(attribute_statement, name, value):
        attr = etree.SubElement(
            attribute_statement,
            f"{{{SAML_NS}}}Attribute",
            Name=name
        )
        attr_value = etree.SubElement(
            attr,
            f"{{{SAML_NS}}}AttributeValue"
        )
        attr_value.set(
            "{http://www.w3.org/2001/XMLSchema-instance}type",
            "xs:string"
        )
        attr_value.text = value

    def _clean_private_key(self, private_key: str) -> bytes:
        """Remove leading/trailing whitespace and encode to bytes, as required by signxml."""
        cleaned = "\n".join(line.strip() for line in private_key.strip().splitlines())
        if cleaned and '\\n' in cleaned:
            cleaned = cleaned.replace('\\n', '\n')

        return cleaned.encode("utf-8")

    def _build_assertion(self):
        """ Function to generate saml assertion for OAuth exchange workflow
        Returns the generated SAML assertion as a base64-encoded string.
        """

        client_id = self.config.get("client_id")
        user_id = self.config.get("user_id")
        token_url = self.config.get("api_server") + "/oauth/token"
        private_key = self._clean_private_key(self.config.get("private_key"))

        now = datetime.now(timezone.utc)
        issue_instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        not_on_or_after = (now + ASSERTION_VALIDITY).strftime("%Y-%m-%dT%H:%M:%SZ")

        assertion_id = "_" + str(uuid.uuid4())

        LOGGER.info("Building new SAML assertion...")
        nsmap = {
            "saml2": SAML_NS,
            "ds": "http://www.w3.org/2000/09/xmldsig#",
            "xs": "http://www.w3.org/2001/XMLSchema",
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        }

        assertion = etree.Element(
            f"{{{SAML_NS}}}Assertion",
            nsmap=nsmap,
            ID=assertion_id,
            Version="2.0",
            IssueInstant=issue_instant,
        )

        # ----------------------
        # Issuer (must be client_id)
        # ----------------------
        issuer = etree.SubElement(
            assertion,
            f"{{{SAML_NS}}}Issuer"
        )
        issuer.text = client_id

        # ----------------------
        # Subject (userId mode)
        # ----------------------
        subject = etree.SubElement(
            assertion,
            f"{{{SAML_NS}}}Subject"
        )

        name_id = etree.SubElement(
            subject,
            f"{{{SAML_NS}}}NameID",
            Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
        )
        name_id.text = user_id

        subject_confirmation = etree.SubElement(
            subject,
            f"{{{SAML_NS}}}SubjectConfirmation",
            Method="urn:oasis:names:tc:SAML:2.0:cm:bearer"
        )

        etree.SubElement(
            subject_confirmation,
            f"{{{SAML_NS}}}SubjectConfirmationData",
            NotOnOrAfter=not_on_or_after,
            Recipient=token_url,
            InResponseTo=client_id
        )

        # ----------------------
        # Conditions
        # ----------------------
        conditions = etree.SubElement(
            assertion,
            f"{{{SAML_NS}}}Conditions",
            NotBefore=issue_instant,
            NotOnOrAfter=not_on_or_after,
        )

        audience_restriction = etree.SubElement(
            conditions,
            f"{{{SAML_NS}}}AudienceRestriction"
        )

        audience = etree.SubElement(
            audience_restriction,
            f"{{{SAML_NS}}}Audience"
        )
        audience.text = token_url

        # ----------------------
        # Required AttributeStatement
        # ----------------------
        attribute_statement = etree.SubElement(
            assertion,
            f"{{{SAML_NS}}}AttributeStatement"
        )

        self._add_attribute(attribute_statement, "api_key", client_id)
        self._add_attribute(attribute_statement, "use_username", "false")
        self._add_attribute(attribute_statement, "external_user", "false")

        # ----------------------
        # SIGN ASSERTION (SHA256)
        # ----------------------

        signer = XMLSigner(
            method=methods.enveloped,
            signature_algorithm="rsa-sha256",
            digest_algorithm="sha256",
            c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"
        )

        signed_assertion = signer.sign(
            assertion,
            key=private_key,
            reference_uri=assertion_id
        )

        saml_xml = etree.tostring(
            signed_assertion,
            xml_declaration=True,
            encoding="UTF-8"
        )

        LOGGER.info("SAML assertion built successfully.")

        return base64.b64encode(saml_xml).decode("utf-8")


class AssertionStrategyFactory:
    """Factory class for creating assertion strategy instances.
    Resolves the appropriate `AssertionStrategy` implementation based on the provided configuration or assertion type.
    """

    _registry: Dict[str, Type[AssertionStrategy]] = {
        "saml_bearer_oauth": SAMLBearerAssertionStrategy,
    }

    @classmethod
    def register(cls, assertion_type: str, strategy_cls: Type[AssertionStrategy]) -> None:
        """ Method to add a new asertion strategy to the registry

        Args:
            assertion_type (str): Type of assertion
            strategy_cls (Type[AssertionStrategy]): AssertionStrategy Class implementation to register
        """
        cls._registry[assertion_type] = strategy_cls

    @classmethod
    def create(cls, config: dict, assertion_type: Optional[str] = None) -> AssertionStrategy:
        resolved_type = assertion_type or config.get("auth_method", "saml_bearer_oauth")
        try:
            strategy_cls = cls._registry[resolved_type]
        except KeyError as exc:
            raise ValueError(f"Unknown assertion strategy '{resolved_type}'") from exc
        return strategy_cls(config)
