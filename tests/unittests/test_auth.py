from tap_sap_success_factors.auth import build_token_request


def test_build_token_request_access_token_mode():
    assert build_token_request({"access_token": "abc"}) == {}


def test_build_token_request_saml_mode():
    payload = build_token_request(
        {
            "client_id": "cid",
            "company_id": "co",
            "grant_type": "urn:ietf:params:oauth:grant-type:saml2-bearer",
            "saml_assertion": "assertion",
        }
    )

    assert payload["client_id"] == "cid"
    assert payload["assertion"] == "assertion"


def test_build_token_request_refresh_token_mode():
    payload = build_token_request(
        {
            "client_id": "cid",
            "refresh_token": "refresh",
        }
    )

    assert payload == {
        "client_id": "cid",
        "grant_type": "refresh_token",
        "refresh_token": "refresh",
    }
