from typing import Dict

from singer import get_logger

LOGGER = get_logger()


def build_token_request(config: Dict) -> Dict:
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
        "grant_type": "urn:ietf:params:oauth:grant-type:saml2-bearer",
        "assertion": config.get("assertion") or config.get("saml_assertion"),
    }

    if config.get("refresh_token"):
        payload = {
            "client_id": config.get("client_id"),
            "grant_type": "refresh_token",
            "refresh_token": config.get("refresh_token"),
        }

    return {k: v for k, v in payload.items() if v is not None}
