from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

import backoff
import requests
from requests import session
from requests.exceptions import ChunkedEncodingError
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout
from singer import get_logger, metrics

from tap_sap_success_factors.auth import (build_basic_auth_header,
                                          build_token_request)
from tap_sap_success_factors.exceptions import (
    ERROR_CODE_EXCEPTION_MAPPING, SAPSuccessFactorsError,
    SAPSuccessFactorsRateLimitError, SAPSuccessFactorsServer5xxError)

LOGGER = get_logger()
REQUEST_TIMEOUT = 300


def _get_retry_after(exc) -> int:
    """Return wait seconds from Retry-After response header, or 60 as default.

    Used as the ``value`` predicate for the ``backoff.runtime`` wait generator
    on the 429 rate-limit backoff decorator.
    """
    retry_after = None
    if exc is not None and getattr(exc, "response", None) is not None:
        retry_after = exc.response.headers.get("Retry-After")
    if retry_after:
        LOGGER.warning(
            "Rate limited by SAP SuccessFactors. Retrying in %s seconds (Retry-After header).",
            retry_after,
        )
        try:
            return int(retry_after)
        except ValueError:
            LOGGER.warning(
                "Could not parse Retry-After header value '%s', using 60 seconds.", retry_after
            )
            return 60
    LOGGER.warning(
        "Rate limited by SAP SuccessFactors. No Retry-After header present. Retrying in 60 seconds."
    )
    return 60


def raise_for_error(response: requests.Response) -> None:
    """Raise mapped exception for non-success responses."""
    if response.status_code in (200, 201, 204):
        return

    try:
        response_json = response.json()
    except ValueError:  # pragma: no cover - response body may not be json
        response_json = {}

    mapped = ERROR_CODE_EXCEPTION_MAPPING.get(response.status_code, {})
    if not mapped and 500 <= response.status_code < 600:
        exc = SAPSuccessFactorsServer5xxError
        default_message = f"Server error ({response.status_code})."
    else:
        exc = mapped.get("raise_exception", SAPSuccessFactorsError)
        default_message = mapped.get("message", "Unknown API error")

    error_msg = (
        response_json.get("error_description")
        or response_json.get("error")
        or response_json.get("message")
        or getattr(response, "text", "")[:500]
        or default_message
    )

    raise exc(
        f"HTTP-error-code: {response.status_code}, Error: {error_msg}",
        response,
    )


class SAPSuccessFactorsClient:
    """HTTP client wrapper for SAP SuccessFactors APIs."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = dict(config)
        self._session = session()
        self.base_url = self.config["api_server"].rstrip("/")
        self.odata_path = self.config.get("odata_path", "/odata/v2")
        self._access_token = self.config.get("access_token")
        self._expires_at = None
        # Computed once at construction; None when not in basic-auth mode.
        self._basic_auth_header = build_basic_auth_header(config)

        config_request_timeout = self.config.get("request_timeout")
        self.request_timeout = (
            float(config_request_timeout) if config_request_timeout else REQUEST_TIMEOUT
        )

    def __enter__(self):
        self.refresh_access_token()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self._session.close()

    def refresh_access_token(self) -> None:
        """Get/refresh access token when static token is not supplied.

        For Basic-auth mode (``username`` + ``password`` in config) no OAuth
        token exchange is needed — every request is authenticated via the
        ``Authorization: Basic <base64>`` header built at construction time.
        """
        if self._basic_auth_header:
            # Basic auth — no token needed.
            return

        if self.config.get("access_token"):
            self._access_token = self.config["access_token"]
            return

        payload = build_token_request(self.config)
        token_url = self.base_url + "/oauth/token"

        response = self._session.post(
            token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.request_timeout,
        )
        raise_for_error(response)

        response_json = response.json()
        self._access_token = response_json.get("access_token")
        if not self._access_token:
            raise SAPSuccessFactorsError("OAuth response did not include access_token")

        expires_in_seconds = int(response_json.get("expires_in", 3600))
        self._expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in_seconds)

    def get_access_token(self) -> str:
        """Return a valid token."""
        if self._access_token and self._expires_at and self._expires_at > datetime.now(tz=timezone.utc):
            return self._access_token

        if self._access_token and self.config.get("access_token"):
            return self._access_token

        self.refresh_access_token()
        return self._access_token

    def get_auth_header(self) -> str:
        """Return the full ``Authorization`` header value for the configured
        authentication mode.

        - **Basic auth** (``username`` + ``password``): ``Basic <base64>``
        - **OAuth / SAML bearer** (all other modes): ``Bearer <token>``
        """
        if self._basic_auth_header:
            return self._basic_auth_header
        return f"Bearer {self.get_access_token()}"

    def authenticate(self, headers: Dict, params: Dict) -> Tuple[Dict, Dict]:
        """Inject auth headers and default OData params."""
        headers["Authorization"] = self.get_auth_header()
        headers["Accept"] = "application/json"
        params["$format"] = "json"
        return headers, params

    def get(self, path: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> Any:
        """Perform GET request."""
        params = dict(params or {})
        headers = dict(headers or {})
        headers, params = self.authenticate(headers, params)
        endpoint = f"{self.base_url}{path}"
        return self._make_request("GET", endpoint, headers=headers, params=params)

    def request_raw(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Perform raw request without json parsing."""
        return self._make_request(method, endpoint, parse_json=False, **kwargs)

    @backoff.on_exception(
        wait_gen=backoff.runtime,
        exception=SAPSuccessFactorsRateLimitError,
        max_tries=5,
        value=_get_retry_after,
    )
    @backoff.on_exception(
        wait_gen=backoff.expo,
        exception=(
            ConnectionResetError,
            RequestsConnectionError,
            ChunkedEncodingError,
            Timeout,
            SAPSuccessFactorsServer5xxError,
        ),
        max_tries=5,
        factor=2,
    )
    def _make_request(
        self,
        method: str,
        endpoint: str,
        parse_json: bool = True,
        **kwargs,
    ) -> Optional[Mapping[Any, Any]]:
        """Perform HTTP request; backoff decorators handle retries."""
        kwargs.setdefault("timeout", self.request_timeout)
        with metrics.http_request_timer(endpoint):
            response = self._session.request(method, endpoint, **kwargs)
        raise_for_error(response)
        if not parse_json:
            return response
        # 204 No Content or empty body — nothing to decode
        if response.status_code == 204 or not response.content or not response.content.strip():
            return None
        return response.json()
