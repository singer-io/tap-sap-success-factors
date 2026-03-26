"""Test that all fields are replicated for every active stream."""
from base import SAPSuccessFactorsBaseTest
from tap_tester.base_suite_tests.all_fields_test import AllFieldsTest


class SAPSFAllFieldsTest(AllFieldsTest, SAPSuccessFactorsBaseTest):
    """Ensure running the tap with all streams and fields selected results in
    the replication of all fields present in the discovered schema.

    Streams are limited to the 11 streams that are confirmed to return data
    in the reference SAP SuccessFactors environment (see sync-07-report.md,
    Section 7).  The other 131 streams are excluded via ``streams_to_exclude()``
    inherited from ``SAPSuccessFactorsBaseTest``.

    ``MISSING_FIELDS``
    ------------------
    Populate this dict if the test account is known to not populate certain
    optional fields for a given stream.  Keys are stream names; values are
    lists of field names that the tap may legitimately omit.

    Example::

        MISSING_FIELDS = {
            "user": ["defaultFullName", "empInfo"],
        }
    """

    # Fields that may be absent in the test account's data even though they
    # are present in the schema.  Populate as needed after the first test run.
    MISSING_FIELDS = {
        "user": [
            "status",
            "password",
            "onboardingId"
        ]
    }

    # Use the same start date as the base class to capture the reference data.
    start_date = "2021-01-01T00:00:00Z"

    @staticmethod
    def name():
        """Unique test name used by the tap-tester framework."""
        return "tap_tester_sap_sf_all_fields_test"

    def streams_to_test(self):
        """Return the 11 streams known to return data in the reference environment."""
        return self.expected_stream_names().difference(self.streams_to_exclude())
