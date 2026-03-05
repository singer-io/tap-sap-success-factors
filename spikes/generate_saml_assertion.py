""" Module to generate a SAML assertion for SuccessFactors API authentication using the OAuth Bearer flow.
    Following dependencies are required:
        - lxml
        - signxml
        - cryptography (for signxml)
        - python-dotenv (for loading environment variables from a .env file)
    Environment variables expected in .env file:
        - SF_CLIENT_ID: SuccessFactors API client_id
        - SF_USERNAME: SuccessFactors username
        - SF_TOKEN_URL: SuccessFactors token endpoint URL (e.g. https://api4.successfactors.com/sf/oauth/token)
        - SF_PRIVATE_KEY_FILE: Path to the private key file (PEM format) used for signing the assertion (default: private_key.pem)
        - SF_CERT_FILE: Path to the certificate file (PEM format) corresponding to the private key (default: certificate.pem)

    Run the script:
        - python generate_saml_assertion.py
    The output will be a base64 encoded SAML assertion that can be used in the OAuth

    NOTE: This workflow will be accomodated in the SuccessFactors API client library,
    so this script is primarily for demonstration and testing purposes.
"""

import base64
import os
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from lxml import etree
from signxml import XMLSigner, methods

# ==============================
# CONFIGURATION
# ==============================

load_dotenv()

CLIENT_ID = os.getenv("SF_CLIENT_ID")  # SuccessFactors API client_id
USERNAME = os.getenv("SF_USERNAME")      # SuccessFactors username
TOKEN_URL = os.getenv("SF_TOKEN_URL")    # SuccessFactors token endpoint URL (e.g. https://api4.successfactors.com/sf/oauth/token)

PRIVATE_KEY_FILE = os.getenv("SF_PRIVATE_KEY_FILE", "private_key.pem")
CERT_FILE = os.getenv("SF_CERT_FILE", "certificate.pem")


def generate_saml_assertion():

    now = datetime.now(timezone.utc)
    issue_instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    not_on_or_after = (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    assertion_id = "_" + str(uuid.uuid4())

    NSMAP = {
        "saml2": "urn:oasis:names:tc:SAML:2.0:assertion",
        "ds": "http://www.w3.org/2000/09/xmldsig#",
        "xs": "http://www.w3.org/2001/XMLSchema",
        "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    }

    assertion = etree.Element(
        "{urn:oasis:names:tc:SAML:2.0:assertion}Assertion",
        nsmap=NSMAP,
        ID=assertion_id,
        Version="2.0",
        IssueInstant=issue_instant,
    )

    # ----------------------
    # Issuer (must be client_id)
    # ----------------------
    issuer = etree.SubElement(
        assertion,
        "{urn:oasis:names:tc:SAML:2.0:assertion}Issuer"
    )
    issuer.text = CLIENT_ID

    # ----------------------
    # Subject (userId mode)
    # ----------------------
    subject = etree.SubElement(
        assertion,
        "{urn:oasis:names:tc:SAML:2.0:assertion}Subject"
    )

    name_id = etree.SubElement(
        subject,
        "{urn:oasis:names:tc:SAML:2.0:assertion}NameID",
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
    )
    name_id.text = USERNAME

    subject_confirmation = etree.SubElement(
        subject,
        "{urn:oasis:names:tc:SAML:2.0:assertion}SubjectConfirmation",
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer"
    )

    etree.SubElement(
        subject_confirmation,
        "{urn:oasis:names:tc:SAML:2.0:assertion}SubjectConfirmationData",
        NotOnOrAfter=not_on_or_after,
        Recipient=TOKEN_URL,
        InResponseTo=CLIENT_ID
    )

    # ----------------------
    # Conditions
    # ----------------------
    conditions = etree.SubElement(
        assertion,
        "{urn:oasis:names:tc:SAML:2.0:assertion}Conditions",
        NotBefore=issue_instant,
        NotOnOrAfter=not_on_or_after,
    )

    audience_restriction = etree.SubElement(
        conditions,
        "{urn:oasis:names:tc:SAML:2.0:assertion}AudienceRestriction"
    )

    audience = etree.SubElement(
        audience_restriction,
        "{urn:oasis:names:tc:SAML:2.0:assertion}Audience"
    )
    audience.text = TOKEN_URL

    # ----------------------
    # Required AttributeStatement
    # ----------------------
    attribute_statement = etree.SubElement(
        assertion,
        "{urn:oasis:names:tc:SAML:2.0:assertion}AttributeStatement"
    )

    def add_attribute(name, value):
        attr = etree.SubElement(
            attribute_statement,
            "{urn:oasis:names:tc:SAML:2.0:assertion}Attribute",
            Name=name
        )
        attr_value = etree.SubElement(
            attr,
            "{urn:oasis:names:tc:SAML:2.0:assertion}AttributeValue"
        )
        attr_value.set(
            "{http://www.w3.org/2001/XMLSchema-instance}type",
            "xs:string"
        )
        attr_value.text = value

    add_attribute("api_key", CLIENT_ID)
    add_attribute("use_username", "false")
    add_attribute("external_user", "false")

    # ----------------------
    # SIGN ASSERTION (SHA256)
    # ----------------------
    with open(PRIVATE_KEY_FILE, "rb") as key_file:
        private_key = key_file.read()

    with open(CERT_FILE, "rb") as cert_file:
        cert = cert_file.read()

    signer = XMLSigner(
        method=methods.enveloped,
        signature_algorithm="rsa-sha256",
        digest_algorithm="sha256",
        c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"
    )

    signed_assertion = signer.sign(
        assertion,
        key=private_key,
        cert=cert,
        reference_uri=assertion_id
    )

    saml_xml = etree.tostring(
        signed_assertion,
        xml_declaration=True,
        encoding="UTF-8"
    )

    return base64.b64encode(saml_xml).decode("utf-8")


if __name__ == "__main__":
    saml_assertion = generate_saml_assertion()

    print("\nBase64 Encoded SAML Assertion:\n")
    print(saml_assertion)