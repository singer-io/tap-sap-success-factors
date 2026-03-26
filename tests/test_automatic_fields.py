"""Test that automatic fields are replicated even when no fields are selected."""
from base import SAPSuccessFactorsBaseTest
from tap_tester.base_suite_tests.automatic_fields_test import MinimumSelectionTest


class SAPSFAutomaticFieldsTest(MinimumSelectionTest, SAPSuccessFactorsBaseTest):
    """Test that with no fields selected for a stream the tap still replicates
    the automatic (non-deselectable) fields.

    Automatic fields are:
      - Primary key column(s) listed in ``table-key-properties`` catalog metadata.
      - The replication key column (for INCREMENTAL streams), listed in
        ``valid-replication-keys`` catalog metadata.

    Streams are limited to the 11 streams that return data in the reference
    environment.  All other streams are excluded via ``streams_to_exclude()``
    inherited from ``SAPSuccessFactorsBaseTest``.
    """

    # Use the same start date as the base class to capture the reference data.
    start_date = "2021-01-01T00:00:00Z"

    @staticmethod
    def name():
        """Unique test name used by the tap-tester framework."""
        return "tap_tester_sap_sf_automatic_fields_test"

    def streams_to_test(self):
        """Return the 11 streams known to return data in the reference environment."""
        return self.expected_stream_names().difference(self.streams_to_exclude())
