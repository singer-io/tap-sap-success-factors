"""Test that the tap respects the configured start date."""
from base import SAPSuccessFactorsBaseTest
from tap_tester.base_suite_tests.start_date_test import StartDateTest


class SAPSFStartDateTest(StartDateTest, SAPSuccessFactorsBaseTest):
    """Instantiate start date according to the desired data set and verify
    that the tap only returns records on or after the configured start date.

    Only INCREMENTAL streams that are confirmed to return data are exercised.
    For this tap in the reference environment those are:

      - ``rbp_role``  (replication key: ``lastModifiedDate``)
      - ``user``      (replication key: ``lastModifiedDateTime``)

    FULL_TABLE streams replicate all data regardless of start date and are
    therefore excluded from this test.

    Test flow
    ---------
    1. **Sync 1** — run with ``start_date_1`` (an older date) to capture a
       baseline set of records.
    2. **Sync 2** — run with ``start_date_2`` (a more recent date) to capture
       a subset of those records.
    3. Assert that every record returned in sync 2 also appears in sync 1
       (i.e. start date 2 is honoured and does not *add* new records that are
       older than start date 1 somehow).  Specifically, sync 2 record count
       must be ≤ sync 1 record count for INCREMENTAL streams.
    """

    @staticmethod
    def name():
        """Unique test name used by the tap-tester framework."""
        return "tap_tester_sap_sf_start_date_test"

    def streams_to_test(self):
        """Return only INCREMENTAL streams that have confirmed data.

        Derived by:
          1. Starting from all expected stream names.
          2. Removing the 131 excluded streams (no data or API errors).
          3. Keeping only INCREMENTAL streams — FULL_TABLE streams ignore the
             start date and are out of scope for this test.
          4. Removing child streams that carry no independent replication key.
        """
        incremental_streams = {
            stream
            for stream, meta in self.expected_metadata().items()
            if meta.get(self.REPLICATION_METHOD) == self.INCREMENTAL
        }
        return (
            self.expected_stream_names()
            .difference(self.streams_to_exclude())
            .intersection(incremental_streams)
            .difference(self.get_child_streams_with_no_replication_keys())
        )

    @property
    def start_date_1(self):
        """Older start date — sync 1 should return the full reference dataset."""
        return "2021-01-01T00:00:00Z"

    @property
    def start_date_2(self):
        """More recent start date — sync 2 should return fewer or equal records.
        """
        return "2026-02-21T20:06:33.000000Z"
