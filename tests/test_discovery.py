"""Test tap discovery mode and metadata."""
import re
from base import SAPSuccessFactorsBaseTest
from tap_tester.base_suite_tests.discovery_test import DiscoveryTest
from tap_tester import menagerie


class SAPSFDiscoveryTest(DiscoveryTest, SAPSuccessFactorsBaseTest):
    """Test tap discovery mode and metadata conforms to standards.

    Validates:
      - All 142 expected streams appear in the discovered catalog.
      - Each stream's replication method and replication key(s) match
        the values declared in ``expected_metadata()``.
      - Child streams carry the correct ``parent-tap-stream-id`` entry
        in their catalog root-level metadata.
    """

    @staticmethod
    def name():
        """Unique test name used by the tap-tester framework."""
        return "tap_tester_sap_sf_discovery_test"

    def streams_to_test(self):
        """Discovery is independent of data availability.

        Return all 142 expected streams so that catalog structure and
        metadata are validated for every stream the tap can produce.
        """
        return self.expected_stream_names()

    # ---------------------------------------------------------------------- #
    # Custom test: replication metadata                                       #
    # ---------------------------------------------------------------------- #

    def test_replication_metadata(self):
        """Verify that every stream's catalog metadata contains the correct
        replication method and replication key(s)."""
        for stream in self.streams_to_test():
            with self.subTest(stream=stream):
                # Gather expectations from base
                expected_replication_keys = self.expected_replication_keys(stream)
                expected_replication_method = self.expected_replication_method(stream)

                # Retrieve the annotated schema from menagerie
                catalog = [
                    c for c in self.found_catalogs
                    if c["stream_name"] == stream
                ][0]
                metadata = menagerie.get_annotated_schema(
                    self.conn_id, catalog["stream_id"]
                )["metadata"]

                # Root-level metadata entry (empty breadcrumb)
                stream_properties = [
                    item for item in metadata if item.get("breadcrumb") == []
                ]
                self.assertIn("metadata", stream_properties[0])
                stream_metadata = stream_properties[0]["metadata"]

                actual_replication_method = stream_metadata.get(
                    self.REPLICATION_METHOD, None
                )
                actual_replication_keys = set(
                    stream_metadata.get(self.REPLICATION_KEYS, [])
                )

                # Replication method must be present and be a string
                self.assertIn(self.REPLICATION_METHOD, stream_metadata)
                self.assertTrue(isinstance(actual_replication_method, str))

                # Replication keys must match
                with self.subTest(msg="validating replication keys"):
                    self.assertSetEqual(
                        expected_replication_keys,
                        actual_replication_keys,
                        logging=(
                            f"verify {expected_replication_keys} "
                            f"is saved in metadata as a valid-replication-key"
                        ),
                    )

                # Replication method must match
                with self.subTest(msg="validating replication method"):
                    self.assertEqual(
                        expected_replication_method,
                        actual_replication_method,
                        logging=(
                            f"verify the replication method is "
                            f"{expected_replication_method}"
                        ),
                    )

                # Consistency check: if replication keys exist, method must be INCREMENTAL
                with self.subTest(msg="validating expectations consistency"):
                    if expected_replication_keys:
                        self.assertEqual(
                            actual_replication_method,
                            self.INCREMENTAL,
                            logging=(
                                f"verify the replication method is "
                                f"{self.INCREMENTAL} since a replication-key is present"
                            ),
                        )

    # ---------------------------------------------------------------------- #
    # Custom test: parent-child relationship metadata (SAP SF specific)       #
    # ---------------------------------------------------------------------- #

    def test_parent_stream_metadata(self):
        """Verify that child streams have the correct ``parent-tap-stream-id``
        written into their catalog root-level metadata.

        The value is set by ``metadata_discovery.py`` and stored under the
        ``parent-tap-stream-id`` key in the root breadcrumb metadata entry.
        Only streams listed in ``expected_metadata()`` with a
        ``PARENT_TAP_STREAM_ID`` entry are validated.
        """
        for stream in self.streams_to_test():
            expected = self.expected_metadata().get(stream, {})
            expected_parent = expected.get(self.PARENT_TAP_STREAM_ID)

            if expected_parent is None:
                # Top-level stream — no parent expected; skip silently.
                continue

            with self.subTest(stream=stream):
                catalog = [
                    c for c in self.found_catalogs
                    if c["stream_name"] == stream
                ][0]
                metadata = menagerie.get_annotated_schema(
                    self.conn_id, catalog["stream_id"]
                )["metadata"]

                stream_root = [
                    item for item in metadata if item.get("breadcrumb") == []
                ]
                self.assertTrue(
                    len(stream_root) > 0,
                    msg=f"No root-level metadata entry found for stream '{stream}'",
                )

                actual_parent = (
                    stream_root[0]
                    .get("metadata", {})
                    .get(self.PARENT_TAP_STREAM_ID)
                )
                self.assertEqual(
                    expected_parent,
                    actual_parent,
                    msg=(
                        f"Stream '{stream}': expected parent-tap-stream-id "
                        f"'{expected_parent}', got '{actual_parent}'"
                    ),
                )

    # ---------------------------------------------------------------------- #
    # Override: stream naming (allow digits for SAP SF version numbers)       #
    # ---------------------------------------------------------------------- #

    def test_stream_naming(self):
        """Verify stream names use only lowercase letters, digits, and underscores.

        The tap-tester base implementation uses ``[a-z_]+``, which rejects
        digits.  SAP SuccessFactors OData entity sets legitimately include
        version numbers in their names (e.g. ``ONB2ActivityNudgeDetails`` →
        ``onb2_activity_nudge_details``).  We broaden the allowed charset to
        ``[a-z0-9_]+`` while keeping all other assertions from the base class.
        """
        for stream in self.streams_to_test():
            with self.subTest(stream=stream):
                match = re.fullmatch(r"[a-z0-9_]+", stream)
                self.assertIsNotNone(
                    match,
                    msg=(
                        f"Stream name '{stream}' does not conform to the Singer "
                        f"naming convention [a-z0-9_]+"
                    ),
                )
                self.assertEqual(
                    match.group(0),
                    stream,
                    msg=f"Stream name '{stream}' contains invalid characters",
                )
