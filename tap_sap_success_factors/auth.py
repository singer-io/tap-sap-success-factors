import base64
from typing import Dict, Optional

from singer import get_logger

LOGGER = get_logger()

SAML_BEARER_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:saml2-bearer"


def build_basic_auth_header(config: Dict) -> Optional[str]:
    """Return a ``Basic <base64>`` authorization header value when the config
    contains ``username`` and ``password``.

    The encoded token is ``base64(username:password)`` per RFC 7617.
    Returns ``None`` when the required keys are absent so callers can fall
    back to the OAuth / SAML bearer flow.
    """
    username = config.get("username")
    password = config.get("password")
    if username and password:
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        LOGGER.info("Using HTTP Basic authentication mechanism with provided username and password.")
        return f"Basic {token}"
    return None


def build_saml_token_request(config: Dict, saml_assertion) -> Dict:
    """Build OAuth token request payload.

    Supported modes:
    - static token in `access_token`
    - SAML bearer flow with `saml_assertion`
    """
    if config.get("access_token"):
        return {}

    payload = {
        "client_id": config.get("client_id"),
        "company_id": config.get("company_id"),
        "grant_type": SAML_BEARER_GRANT_TYPE,
        "assertion": saml_assertion,
    }

    if config.get("refresh_token"):
        payload = {
            "client_id": config.get("client_id"),
            "grant_type": "refresh_token",
            "refresh_token": config.get("refresh_token"),
        }

    return {k: v for k, v in payload.items() if v is not None}
