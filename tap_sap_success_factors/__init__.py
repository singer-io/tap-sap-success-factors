import json
import sys

import singer

from tap_sap_success_factors.client import SAPSuccessFactorsClient
from tap_sap_success_factors.discover import discover
from tap_sap_success_factors.exceptions import SAPSuccessFactorsError
from tap_sap_success_factors.sync import sync

LOGGER = singer.get_logger()

REQUIRED_CONFIG_KEYS = ["api_server", "start_date"]

AUTH_METHOD_BASIC = "basic_auth"
AUTH_METHOD_SAML_BEARER = "saml_bearer_oauth"

_BASIC_AUTH_KEYS = {"username", "password"}
_SAML_BEARER_KEYS = {"client_id", "user_id", "company_id", "private_key"}


def _validate_auth_config(config):
    """Validate required config keys for the configured authentication mode.

    - auth_method == "basic_auth": requires username/password.
    - auth_method == "saml_bearer_oauth": requires client_id/user_id/company_id/private_key.
    - access_token present: static token mode, no further auth keys required.
    - Legacy configs with no auth_method are still supported by inferring the
      mode from whichever complete key set is present.
    """
    if config.get("access_token"):
        return

    auth_method = config.get("auth_method")

    if auth_method == AUTH_METHOD_BASIC:
        missing = sorted(key for key in _BASIC_AUTH_KEYS if not config.get(key))
        if missing:
            raise SAPSuccessFactorsError(
                f"auth_method is 'basic_auth' but config is missing required basic auth keys: {missing}."
            )
        return

    if auth_method == AUTH_METHOD_SAML_BEARER:
        missing = sorted(key for key in _SAML_BEARER_KEYS if not config.get(key))
        if missing:
            raise SAPSuccessFactorsError(
                f"auth_method is 'saml_bearer_oauth' but config is missing required keys: {missing}."
            )
        return

    has_basic = all(config.get(key) for key in _BASIC_AUTH_KEYS)
    has_saml_bearer = all(config.get(key) for key in _SAML_BEARER_KEYS)
    if not has_basic and not has_saml_bearer:
        missing_basic = sorted(key for key in _BASIC_AUTH_KEYS if not config.get(key))
        missing_saml_bearer = sorted(key for key in _SAML_BEARER_KEYS if not config.get(key))
        raise SAPSuccessFactorsError(
            "Config must contain either basic auth keys ({}) or SAML bearer keys ({}). "
            "Missing basic auth keys: {}. Missing SAML bearer keys: {}.".format(
                ", ".join(sorted(_BASIC_AUTH_KEYS)),
                ", ".join(sorted(_SAML_BEARER_KEYS)),
                missing_basic,
                missing_saml_bearer,
            )
        )


def do_discover(client: SAPSuccessFactorsClient):
    """Discover and emit the catalog."""
    LOGGER.info("Starting discover")
    catalog = discover(client)
    json.dump(catalog.to_dict(), sys.stdout, indent=2)
    LOGGER.info("Finished discover")


@singer.utils.handle_top_exception(LOGGER)
def main():
    """Run the tap entrypoint."""
    parsed_args = singer.utils.parse_args(REQUIRED_CONFIG_KEYS)
    _validate_auth_config(parsed_args.config)
    state = parsed_args.state or {}

    with SAPSuccessFactorsClient(parsed_args.config) as client:
        if parsed_args.discover:
            do_discover(client)
        elif parsed_args.catalog:
            sync(
                client=client,
                config=parsed_args.config,
                catalog=parsed_args.catalog,
                state=state,
            )


if __name__ == "__main__":
    main()
