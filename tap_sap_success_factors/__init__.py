import json
import sys

import singer

from tap_sap_success_factors.client import SAPSuccessFactorsClient
from tap_sap_success_factors.discover import discover
from tap_sap_success_factors.sync import sync

LOGGER = singer.get_logger()

REQUIRED_CONFIG_KEYS = ["username", "password", "api_server", "start_date"]


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
