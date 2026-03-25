"""Test tap discovery mode and metadata."""
import re
from base import SAPSuccessFactorsBaseTest
from tap_tester.base_suite_tests.discovery_test import DiscoveryTest
from tap_tester import menagerie


class SAPSFDiscoveryTest(DiscoveryTest, SAPSuccessFactorsBaseTest):
    """Test tap discovery mode and metadata conforms to standards.

    Validates:
      - All expected *reachable* streams appear in the discovered catalog.
      - Each stream's replication method and replication key(s) match
        the values declared in ``expected_metadata()``.
      - Child streams carry the correct ``parent-tap-stream-id`` entry
        in their catalog root-level metadata.

    Note: SAP SuccessFactors performs a live HTTP probe during discovery
    and excludes streams that return HTTP 4xx/5xx (feature not enabled,
    insufficient permissions, etc.).  These streams are listed in
    ``streams_to_exclude()`` and are intentionally absent from the
    catalog.  All tests that iterate the catalog are scoped to the
    testable set (``expected_stream_names() - streams_to_exclude()``)
    so that probe-excluded streams do not cause false failures.
    """

    @staticmethod
    def name():
        """Unique test name used by the tap-tester framework."""
        return "tap_tester_sap_sf_discovery_test"

    def streams_to_test(self):
        """Return all streams actually present in the discovered catalog.

        SAP SF's discovery probe excludes streams that return HTTP 4xx/5xx
        (permissions not granted, feature not enabled, etc.).  Using the live
        catalog as the scope for ``streams_to_test()`` means that every
        per-stream test method (``test_unsupported_fields``,
        ``test_available_fields``, ``test_replication_metadata``, etc.) only
        iterates streams that are known to exist in ``found_catalogs``,
        avoiding ``IndexError`` on the catalog-lookup ``[...][0]`` calls.

        Falls back to ``expected_stream_names() - streams_to_exclude()`` before
        ``setUp()`` has populated ``found_catalogs``.
        """
        if DiscoveryTest.found_catalogs:
            return {c["stream_name"] for c in DiscoveryTest.found_catalogs}
        return self.expected_stream_names() - self.streams_to_exclude()

    # ---------------------------------------------------------------------- #
    # Overrides: relax strict equality to account for probe-excluded streams  #
    # ---------------------------------------------------------------------- #

    def test_number_of_streams(self):
        """Verify discovered catalog is within the expected stream-count bounds.

        The base asserts ``len(found_catalogs) == len(expected_stream_names())``.
        For SAP SF the probe dynamically excludes inaccessible streams, so an
        exact count cannot be hard-coded.  We assert:

        * At least every *testable* stream (``expected - excluded``) is present.
        * No more streams than the total expected set are in the catalog.
        """
        testable = self.expected_stream_names() - self.streams_to_exclude()
        n_found = len(self.found_catalogs)
        n_expected = len(self.expected_stream_names())
        n_testable = len(testable)
        with self.subTest(msg="validating number of actual streams discovered"):
            self.assertGreaterEqual(
                n_found, n_testable,
                logging=(
                    f"catalog has {n_found} streams; at least {n_testable} "
                    f"testable streams must be present"
                ),
            )
            self.assertLessEqual(
                n_found, n_expected,
                logging=(
                    f"catalog has {n_found} streams; must not exceed "
                    f"{n_expected} total expected streams"
                ),
            )

    def test_streams_discovered(self):
        """Verify catalog stream membership against expected_metadata.

        Three assertions (each a subTest):
        1. Every *testable* stream is in the catalog.
        2. No catalog stream is unknown (absent from ``expected_metadata()``).
        3. Every expected stream absent from the catalog is listed in
           ``streams_to_exclude()`` so the gap is intentional.
        """
        found_stream_names = {c["stream_name"] for c in self.found_catalogs}
        testable = self.expected_stream_names() - self.streams_to_exclude()

        with self.subTest(msg="validating testable streams present in catalog"):
            missing = testable - found_stream_names
            self.assertFalse(
                missing,
                msg=(
                    f"Testable streams missing from catalog: {missing}. "
                    f"Add them to streams_to_exclude() if inaccessible."
                ),
            )

        with self.subTest(
            msg="validating all catalog streams are known in expected_metadata"
        ):
            extra = found_stream_names - self.expected_stream_names()
            self.assertFalse(
                extra,
                msg=(
                    f"Catalog streams not in expected_metadata(): {extra}. "
                    f"Add them to expected_metadata()."
                ),
            )

        with self.subTest(
            msg="validating all absent expected streams are in streams_to_exclude"
        ):
            not_in_catalog = self.expected_stream_names() - found_stream_names
            uncovered = not_in_catalog - self.streams_to_exclude()
            self.assertFalse(
                uncovered,
                msg=(
                    f"Streams absent from catalog but not in streams_to_exclude(): "
                    f"{uncovered}. Add them to streams_to_exclude()."
                ),
            )

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
