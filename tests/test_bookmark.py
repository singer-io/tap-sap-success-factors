"""Test tap bookmark state is written and respected on subsequent syncs."""
from base import SAPSuccessFactorsBaseTest
from tap_tester.base_suite_tests.bookmark_test import BookmarkTest


class SAPSFBookmarkTest(BookmarkTest, SAPSuccessFactorsBaseTest):
    """Test tap sets a bookmark and respects it for the next sync of a stream.

    Only INCREMENTAL streams that are confirmed to return data in the reference
    SAP SuccessFactors environment are exercised.  For this tap those are:

      - ``rbp_role``  (replication key: ``lastModifiedDate``)
      - ``user``      (replication key: ``lastModifiedDateTime``)

    Sync flow
    ---------
    1. Sync 1 — run with ``initial_bookmarks`` injected so that a bounded
       (but non-empty) set of records is returned.
    2. Inject ``calculate_new_bookmarks()`` into the state between the two
       syncs.  The new bookmark dates should sit *inside* the sync-1 result
       window so that sync 2 returns a smaller but non-empty record set.
    3. Assert that the sync-2 record counts are ≤ sync-1 record counts and
       that the final bookmark advanced.

    .. note::
        ``initial_bookmarks`` and ``calculate_new_bookmarks()`` contain
        placeholder dates.  Replace them with actual timestamps from the
        target SAP SF instance after running the first real sync.
    """

    # Use the same start date as the base class; override here if a more
    # targeted window is needed for the test account.
    start_date = "2021-01-01T00:00:00Z"

    # Date format emitted by SAP SuccessFactors for lastModified* fields.
    bookmark_format = "%Y-%m-%dT%H:%M:%S.%fZ"

    initial_bookmarks = {
        "bookmarks": {
            "rbp_role": {"lastModifiedDate":     "2021-01-01T00:00:00.000Z"},
            "user":     {"lastModifiedDateTime": "2021-01-01T00:00:00.000Z"},
        }
    }

    @staticmethod
    def name():
        """Unique test name used by the tap-tester framework."""
        return "tap_tester_sap_sf_bookmark_test"

    def streams_to_test(self):
        """Return only INCREMENTAL streams that have confirmed data.

        Derived by:
          1. Starting from all expected stream names.
          2. Removing the 131 streams excluded by ``streams_to_exclude()``.
          3. Keeping only INCREMENTAL streams (FULL_TABLE streams do not use
             bookmarks and are therefore out of scope for this test).
          4. Removing child streams that carry no replication key of their own
             (their parent bookmark drives their replication window).
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

    def calculate_new_bookmarks(self):
        """Return bookmark state to inject between sync 1 and sync 2.

        The dates returned here should be:
          * **After** the oldest record in sync 1  — so sync 2 is not empty.
          * **Before** the newest record in sync 1  — so sync 2 is smaller
            than sync 1 (confirming the bookmark is respected).
        """

        return {
            "rbp_role": {"lastModifiedDate":     "2026-02-21T21:06:33.000000Z"},
            "user":     {"lastModifiedDateTime": "2026-02-21T00:00:00.000000Z"}
        }
