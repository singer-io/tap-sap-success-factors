"""Unit tests for tap_sap_success_factors.stream_probe."""
import unittest
from unittest.mock import MagicMock, Mock, patch

from tap_sap_success_factors.stream_probe import (
    PROBE_MAX_WORKERS,
    PROBE_TIMEOUT,
    probe_all_streams,
    probe_stream,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, text: str = "") -> Mock:
    """Return a minimal requests.Response-like mock."""
    resp = Mock()
    resp.status_code = status_code
    resp.text = text
    return resp


def _mock_client(base_url: str = "https://api.example.com") -> Mock:
    """Return a minimal tap client mock."""
    client = Mock()
    client.base_url = base_url
    client.get_auth_header.return_value = "Bearer test-token"
    client.config = {"user_id": "testuser", "start_date": "2000-01-01T00:00:00Z"}
    return client


# ---------------------------------------------------------------------------
# probe_stream — single-stream unit tests
# ---------------------------------------------------------------------------

class TestProbeStream(unittest.TestCase):
    """Tests for :func:`stream_probe.probe_stream`."""

    @patch("tap_sap_success_factors.stream_probe.requests.get")
    def test_200_returns_ok_status(self, mock_get):
        """A 200 response yields status=200 and no error."""
        mock_get.return_value = _mock_response(200)

        result = probe_stream(
            "Bearer tok", "https://api.example.com", "currency", "/odata/v2/Currency"
        )

        self.assertEqual(result["stream"], "currency")
        self.assertEqual(result["status"], 200)
        self.assertIsNone(result["error"])

    @patch("tap_sap_success_factors.stream_probe.requests.get")
    def test_400_returns_status_and_error_snippet(self, mock_get):
        """A 400 response yields status=400 with error body snippet."""
        body = '{"error":{"code":"COE0025","message":"Unsupported feature"}}'
        mock_get.return_value = _mock_response(400, body)

        result = probe_stream(
            "Bearer tok", "https://api.example.com", "inner_message", "/odata/v2/InnerMessage"
        )

        self.assertEqual(result["stream"], "inner_message")
        self.assertEqual(result["status"], 400)
        self.assertIn("COE0025", result["error"])

    @patch("tap_sap_success_factors.stream_probe.requests.get")
    def test_403_returns_status_and_error_snippet(self, mock_get):
        """A 403 response yields status=403 with error body snippet (excluded)."""
        mock_get.return_value = _mock_response(403, "Forbidden")

        result = probe_stream(
            "Bearer tok", "https://api.example.com", "calibration_session",
            "/odata/v2/CalibrationSession"
        )

        self.assertEqual(result["status"], 403)
        self.assertIn("Forbidden", result["error"])

    @patch("tap_sap_success_factors.stream_probe.requests.get")
    def test_500_returns_status_and_error_snippet(self, mock_get):
        """A 500 response yields status=500 with error body snippet (excluded)."""
        mock_get.return_value = _mock_response(500, "Internal Server Error")

        result = probe_stream(
            "Bearer tok", "https://api.example.com", "anonymization_request_entity",
            "/odata/v2/AnonymizationRequestEntity"
        )

        self.assertEqual(result["status"], 500)
        self.assertIn("Internal Server Error", result["error"])

    @patch(
        "tap_sap_success_factors.stream_probe.requests.get",
        side_effect=__import__("requests").exceptions.Timeout,
    )
    def test_timeout_returns_none_status(self, _mock_get):
        """A network timeout returns status=None with error='timeout'."""
        result = probe_stream(
            "Bearer tok", "https://api.example.com", "some_stream", "/odata/v2/SomeStream"
        )

        self.assertIsNone(result["status"])
        self.assertEqual(result["error"], "timeout")

    @patch(
        "tap_sap_success_factors.stream_probe.requests.get",
        side_effect=__import__("requests").exceptions.ConnectionError("conn refused"),
    )
    def test_network_error_returns_none_status(self, _mock_get):
        """A generic network error returns status=None with error message."""
        result = probe_stream(
            "Bearer tok", "https://api.example.com", "some_stream", "/odata/v2/SomeStream"
        )

        self.assertIsNone(result["status"])
        self.assertIn("conn refused", result["error"])

    @patch("tap_sap_success_factors.stream_probe.requests.get")
    def test_correct_url_and_params_sent(self, mock_get):
        """probe_stream builds the full URL and passes $top=1 & $format."""
        mock_get.return_value = _mock_response(200)

        probe_stream(
            "Bearer tok", "https://api.example.com", "currency", "/odata/v2/Currency"
        )

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs[0][0], "https://api.example.com/odata/v2/Currency")
        params = call_kwargs[1]["params"]
        self.assertEqual(params["$top"], "1")
        self.assertEqual(params["$format"], "json")
        self.assertEqual(call_kwargs[1]["timeout"], PROBE_TIMEOUT)

    @patch("tap_sap_success_factors.stream_probe.requests.get")
    def test_auth_header_forwarded(self, mock_get):
        """probe_stream forwards the Authorization header verbatim."""
        mock_get.return_value = _mock_response(200)

        probe_stream(
            "Basic dXNlcjpwYXNz", "https://api.example.com", "s", "/odata/v2/S"
        )

        headers = mock_get.call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Basic dXNlcjpwYXNz")

    @patch("tap_sap_success_factors.stream_probe.requests.get")
    def test_400_error_snippet_truncated_to_300_chars(self, mock_get):
        """Error body is capped at 300 characters for 400 responses."""
        long_body = "x" * 500
        mock_get.return_value = _mock_response(400, long_body)

        result = probe_stream(
            "Bearer tok", "https://api.example.com", "s", "/odata/v2/S"
        )

        self.assertEqual(len(result["error"]), 300)

    @patch("tap_sap_success_factors.stream_probe.requests.get")
    def test_400_empty_body_returns_no_body_message(self, mock_get):
        """An empty 400 body yields the placeholder '(no body)'."""
        mock_get.return_value = _mock_response(400, "")

        result = probe_stream(
            "Bearer tok", "https://api.example.com", "s", "/odata/v2/S"
        )

        self.assertEqual(result["error"], "(no body)")


# ---------------------------------------------------------------------------
# probe_all_streams — orchestrator unit tests
# ---------------------------------------------------------------------------

class TestProbeAllStreams(unittest.TestCase):
    """Tests for :func:`stream_probe.probe_all_streams`."""

    def _stream_defs(self, names):
        """Build minimal stream_defs dict for the given stream names."""
        return {
            name: {
                "path": f"/odata/v2/{name.title().replace('_', '')}",
                "parent_filter_field": None,
                "parent_filter_field_schema": {},
                "expand_parent_entity_set": None,
                "replication_keys": [],
            }
            for name in names
        }

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_400_streams_are_excluded(self, mock_probe):
        """Streams returning 400 appear in the excluded set."""
        def _side_effect(auth, base, name, path, extra_params=None):
            status = 400 if name in {"inner_message", "dg_filter"} else 200
            return {
                "stream": name,
                "status": status,
                "error": "err" if status == 400 else None,
            }

        mock_probe.side_effect = _side_effect
        client = _mock_client()
        stream_defs = self._stream_defs(["currency", "inner_message", "dg_filter"])

        excluded = probe_all_streams(client, stream_defs)

        self.assertEqual(excluded, {"inner_message", "dg_filter"})

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_200_streams_not_excluded(self, mock_probe):
        """Streams returning 200 are never added to the excluded set."""
        mock_probe.side_effect = lambda auth, base, name, path, extra_params=None: {
            "stream": name, "status": 200, "error": None
        }
        client = _mock_client()

        excluded = probe_all_streams(client, self._stream_defs(["currency", "user"]))

        self.assertEqual(excluded, set())

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_403_streams_are_excluded(self, mock_probe):
        """403 responses are excluded (permanent access denial)."""
        mock_probe.side_effect = lambda auth, base, name, path, extra_params=None: {
            "stream": name, "status": 403, "error": "Forbidden"
        }
        client = _mock_client()

        excluded = probe_all_streams(client, self._stream_defs(["calibration_session"]))

        self.assertEqual(excluded, {"calibration_session"})

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_500_streams_are_excluded(self, mock_probe):
        """5xx responses are excluded (server-side permanent errors)."""
        mock_probe.side_effect = lambda auth, base, name, path, extra_params=None: {
            "stream": name, "status": 500, "error": "Internal Server Error"
        }
        client = _mock_client()

        excluded = probe_all_streams(
            client, self._stream_defs(["anonymization_request_entity"])
        )

        self.assertEqual(excluded, {"anonymization_request_entity"})

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_network_error_streams_not_excluded(self, mock_probe):
        """Streams that time out or hit network errors are kept in catalog."""
        mock_probe.side_effect = lambda auth, base, name, path, extra_params=None: {
            "stream": name, "status": None, "error": "timeout"
        }
        client = _mock_client()

        excluded = probe_all_streams(client, self._stream_defs(["some_stream"]))

        self.assertEqual(excluded, set())

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_empty_stream_defs_returns_empty_set(self, mock_probe):
        """No probes are submitted when stream_defs is empty."""
        client = _mock_client()

        excluded = probe_all_streams(client, {})

        self.assertEqual(excluded, set())
        mock_probe.assert_not_called()

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_client_auth_header_forwarded_to_probe(self, mock_probe):
        """The auth header from client.get_auth_header() is passed to probes."""
        mock_probe.return_value = {"stream": "s", "status": 200, "error": None}
        client = _mock_client()
        client.get_auth_header.return_value = "Bearer special-token"

        probe_all_streams(client, self._stream_defs(["s"]))

        call_args = mock_probe.call_args
        self.assertEqual(call_args[0][0], "Bearer special-token")

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_client_base_url_forwarded_to_probe(self, mock_probe):
        """The base_url from client.base_url is passed to probes."""
        mock_probe.return_value = {"stream": "s", "status": 200, "error": None}
        client = _mock_client("https://custom.sf.example.com")

        probe_all_streams(client, self._stream_defs(["s"]))

        call_args = mock_probe.call_args
        self.assertEqual(call_args[0][1], "https://custom.sf.example.com")

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_4xx_5xx_mixed_batch_correctly_partitioned(self, mock_probe):
        """Mixed batch: all 4xx/5xx are excluded; 2xx and timeouts are kept."""
        responses = {
            "ok_stream": 200,
            "bad_stream_a": 400,
            "forbidden_stream": 403,
            "bad_stream_b": 400,
            "error_stream": 500,
            "timeout_stream": None,
        }

        def _side_effect(auth, base, name, path, extra_params=None):
            st = responses[name]
            return {
                "stream": name,
                "status": st,
                "error": "err" if st and st >= 400 else (
                    None if st else "timeout"
                ),
            }

        mock_probe.side_effect = _side_effect
        client = _mock_client()

        excluded = probe_all_streams(
            client, self._stream_defs(list(responses.keys()))
        )

        self.assertEqual(
            excluded,
            {"bad_stream_a", "forbidden_stream", "bad_stream_b", "error_stream"},
        )


    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_child_streams_are_probed_with_parent_filter(self, mock_probe):
        """Child streams probed with a type-aware $filter expression.

        The filter value is chosen based on the parent_filter_field schema:
          string  -> eq '<user_id>'
          integer -> eq 0
          date-time -> ge datetime'2000-01-01T00:00:00'
        This prevents type-validation 400s from causing false exclusions.
        """
        mock_probe.return_value = {"stream": "s", "status": 200, "error": None}
        client = _mock_client()  # client.config['user_id'] == 'testuser'
        stream_defs = {
            "goal_plan_state": {
                "path": "/odata/v2/GoalPlanState",
                "parent_filter_field": "userId",
                "parent_filter_field_schema": {
                    "type": ["null", "string"]
                },
                "expand_parent_entity_set": None,
                "replication_keys": [],
            },
            "employee_time_mex": {
                "path": "/odata/v2/EmployeeTimeMEX",
                "parent_filter_field": "externalCode",
                "parent_filter_field_schema": {
                    "type": ["null", "integer"]
                },
                "expand_parent_entity_set": None,
                "replication_keys": [],
            },
            "na_reporting_entity": {
                "path": "/odata/v2/NaReportingEntity",
                "parent_filter_field": "startDate",
                "parent_filter_field_schema": {
                    "type": ["null", "string"],
                    "format": "date-time",
                },
                "expand_parent_entity_set": None,
                "replication_keys": [],
            },
            "currency": {
                "path": "/odata/v2/Currency",
                "parent_filter_field": None,
                "parent_filter_field_schema": {},
                "expand_parent_entity_set": None,
                "replication_keys": [],
            },
        }

        probe_all_streams(client, stream_defs)

        calls_by_name = {c[0][2]: c for c in mock_probe.call_args_list}
        self.assertIn("currency", calls_by_name)
        self.assertIn("goal_plan_state", calls_by_name)
        self.assertIn("employee_time_mex", calls_by_name)
        self.assertIn("na_reporting_entity", calls_by_name)

        def _extra(call):
            return (
                call[0][4]
                if len(call[0]) > 4
                else call[1].get("extra_params", {})
            )

        # String -> eq '<user_id>'
        gps = _extra(calls_by_name["goal_plan_state"])
        self.assertEqual(gps.get("$filter"), "userId eq 'testuser'")

        # Integer -> eq 0
        etm = _extra(calls_by_name["employee_time_mex"])
        self.assertEqual(etm.get("$filter"), "externalCode eq 0")

        # Date-time -> ge datetime'...'
        nre = _extra(calls_by_name["na_reporting_entity"])
        self.assertEqual(
            nre.get("$filter"),
            "startDate ge datetime'2000-01-01T00:00:00'",
        )

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_child_403_is_excluded(self, mock_probe):
        """A child stream returning 403 is excluded (permission block)."""
        mock_probe.side_effect = lambda auth, base, name, path, extra_params=None: {
            "stream": name,
            "status": 403,
            "error": "COE0020 permission required",
        }
        client = _mock_client()
        stream_defs = {
            "calibration_session_reviewer": {
                "path": "/odata/v2/CalibrationSessionReviewer",
                "parent_filter_field": "sessionId",
                "parent_filter_field_schema": {
                    "type": ["null", "string"]
                },
                "expand_parent_entity_set": None,
                "replication_keys": [],
            },
        }

        excluded = probe_all_streams(client, stream_defs)

        self.assertIn("calibration_session_reviewer", excluded)

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_child_400_not_filterable_is_excluded(self, mock_probe):
        """A child stream returning 400 COE0003 (not filterable) is excluded.

        COE0003 means the join field cannot be used in a $filter expression
        at all — the stream will fail at sync time too, so it is correctly
        excluded at discovery.
        """
        mock_probe.side_effect = lambda auth, base, name, path, extra_params=None: {
            "stream": name,
            "status": 400,
            "error": '{"error": {"code": "COE_BAD_PROPERTY_EXPRESSION", '
                     '"message": {"lang": "en-US", "value": "'
                     '[COE0003]formDataId is not filterable"}}}',
        }
        client = _mock_client()
        stream_defs = {
            "form_audit_trail": {
                "path": "/odata/v2/FormAuditTrail",
                "parent_filter_field": "formDataId",
                "parent_filter_field_schema": {
                    "type": ["null", "integer"]
                },
                "expand_parent_entity_set": None,
                "replication_keys": [],
            },
        }

        excluded = probe_all_streams(client, stream_defs)

        self.assertIn("form_audit_trail", excluded)

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_child_400_type_mismatch_is_kept(self, mock_probe):
        """A child stream returning 400 for a type mismatch is kept.

        Errors like "wrong type" or "not valid number" are probe-time false
        positives — the stream will work at sync time with real parent key
        values (correct types and valid IDs from actual parent records).
        """
        mock_probe.side_effect = lambda auth, base, name, path, extra_params=None: {
            "stream": name,
            "status": 400,
            "error": '{"error": {"code": "COE_HRIS_QUERY_USING_WRONG_TYPE_IN_FILTER",'
                     ' "message": {"lang": "en-US", "value": '
                     '"only support Long for WorkflowAllowedActionList"}}}',
        }
        client = _mock_client()
        stream_defs = {
            "workflow_allowed_action_list": {
                "path": "/odata/v2/WorkflowAllowedActionList",
                "parent_filter_field": "wfRequestId",
                "parent_filter_field_schema": {
                    "type": ["null", "integer"]
                },
                "expand_parent_entity_set": None,
                "replication_keys": [],
            },
        }

        excluded = probe_all_streams(client, stream_defs)

        self.assertNotIn("workflow_allowed_action_list", excluded)

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_expand_only_streams_are_skipped(self, mock_probe):
        """Streams with expand_parent_entity_set set are never probed directly.

        Expand-only streams (e.g. emp_compensation_calculated) must be fetched
        via OData $expand and reject direct queries with COE0025/COE0018.
        """
        mock_probe.return_value = {"stream": "s", "status": 200, "error": None}
        client = _mock_client()
        stream_defs = {
            "emp_compensation_calculated": {
                "path": "/odata/v2/EmpCompensationCalculated",
                "parent_filter_field": None,
                "expand_parent_entity_set": "EmpCompensation",
                "replication_keys": [],
            },
            "currency": {
                "path": "/odata/v2/Currency",
                "parent_filter_field": None,
                "expand_parent_entity_set": None,
                "replication_keys": [],
            },
        }

        probe_all_streams(client, stream_defs)

        probed_names = [call[0][2] for call in mock_probe.call_args_list]
        self.assertIn("currency", probed_names)
        self.assertNotIn("emp_compensation_calculated", probed_names)

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_incremental_streams_probed_with_date_filter(self, mock_probe):
        """INCREMENTAL streams are probed with a $filter on the replication key.

        Without the filter SAP rejects streams like ExternalLearner with
        HTTP 400, causing false exclusions.
        """
        mock_probe.return_value = {
            "stream": "external_learner", "status": 200, "error": None
        }
        client = _mock_client()
        client.config = {"start_date": "2020-01-01T00:00:00Z"}
        stream_defs = {
            "external_learner": {
                "path": "/odata/v2/ExternalLearner",
                "parent_filter_field": None,
                "expand_parent_entity_set": None,
                "replication_keys": ["lastModifiedDateTime"],
            },
        }

        probe_all_streams(client, stream_defs)

        call_kwargs = mock_probe.call_args
        extra = call_kwargs[0][4]  # 5th positional arg: extra_params
        self.assertIsNotNone(extra)
        self.assertIn("$filter", extra)
        self.assertIn("lastModifiedDateTime", extra["$filter"])
        self.assertIn("2020-01-01T00:00:00Z", extra["$filter"])

    @patch("tap_sap_success_factors.stream_probe.probe_stream")
    def test_expand_only_child_excluded_when_parent_excluded(self, mock_probe):
        """Expand-only streams whose expand parent returned HTTP 400 must
        also be excluded (cascade exclusion).

        Real example:
          form_custom_element         → HTTP 400 (probed directly)
          form_custom_element_list_value → expand_parent=FormCustomElement
          → at sync time hits FormCustomElement → also 400
          → must be excluded during discovery.
        """
        mock_probe.side_effect = (
            lambda auth, base, name, path, extra_params=None: {
                "stream": name,
                "status": 400 if name == "form_custom_element" else 200,
                "error": "COE0018" if name == "form_custom_element" else None,
            }
        )
        client = _mock_client()
        stream_defs = {
            "form_custom_element": {
                "path": "/odata/v2/FormCustomElement",
                "entity_set": "FormCustomElement",
                "parent_filter_field": None,
                "expand_parent_entity_set": None,
                "replication_keys": [],
            },
            "form_custom_element_list_value": {
                "path": "/odata/v2/FormCustomElementListValue",
                "entity_set": "FormCustomElementListValue",
                "parent_filter_field": None,
                "expand_parent_entity_set": "FormCustomElement",
                "replication_keys": [],
            },
            "currency": {
                "path": "/odata/v2/Currency",
                "entity_set": "Currency",
                "parent_filter_field": None,
                "expand_parent_entity_set": None,
                "replication_keys": [],
            },
        }

        excluded = probe_all_streams(client, stream_defs)

        self.assertIn(
            "form_custom_element", excluded,
            "Direct 400 stream must be excluded",
        )
        self.assertIn(
            "form_custom_element_list_value", excluded,
            "Expand-only child of excluded parent must be cascade-excluded",
        )
        self.assertNotIn("currency", excluded)

# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


class TestProbeConstants(unittest.TestCase):
    def test_probe_timeout_positive(self):
        self.assertGreater(PROBE_TIMEOUT, 0)

    def test_probe_max_workers_positive(self):
        self.assertGreater(PROBE_MAX_WORKERS, 0)
