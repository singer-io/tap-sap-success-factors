"""Test tap can replicate multiple pages of data for paginated streams."""
from base import SAPSuccessFactorsBaseTest
from tap_tester.base_suite_tests.pagination_test import PaginationTest


class SAPSFPaginationTest(PaginationTest, SAPSuccessFactorsBaseTest):
    """Ensure tap can replicate multiple pages of data for streams that use
    pagination.

    SAP SuccessFactors OData V2 paginates results using ``$top`` / ``$skip``
    query parameters.  A stream must contain more records than the configured
    page size for this test to be meaningful.  Based on the reference sync
    (sync-07-report.md) only three streams reliably exceed the default page
    size of 100 records in the test environment:

      - ``rbp_basic_permission``  — 503 records
      - ``territory``             — 249 records
      - ``entity``                — 142 records
    """

    @staticmethod
    def name():
        """Unique test name used by the tap-tester framework."""
        return "tap_tester_sap_sf_pagination_test"

    def streams_to_test(self):
        """Return streams known to span at least two OData pages.

        Only streams confirmed to hold more than the default page size
        (100 records) in the reference environment are included.  Add
        additional stream names here when the test account is populated
        with more data.
        """
        return {
            "rbp_basic_permission",  # 503 records in reference environment
        }
