# tap-sap-success-factors

This is a [Singer](https://singer.io) tap that produces JSON-formatted data following the [Singer Spec](https://github.com/singer-io/getting-started/blob/master/docs/SPEC.md).

## Overview

`tap-sap-success-factors` extracts data from SAP SuccessFactors OData v2 endpoints and emits Singer `SCHEMA`, `RECORD`, and `STATE` messages.

## Supported Streams

This tap is **dynamic-only**. It discovers every entity set exposed by your tenant in `/odata/v2/$metadata` and builds the catalog/schema at runtime.

Example entities commonly present include `CalibrationTemplate`, `PerPerson`, `EmpJob`, `FOCompany`, and many others.

## Stream Blueprint (Dynamic)

For each discovered entity set:
- Endpoint: `/odata/v2/<EntitySet>`
- PK: entity key(s) from `$metadata`
- Replication key: inferred from `lastModifiedDateTime`, `lastModifiedOn`, or `lastModifiedDate` when present
- Method: `INCREMENTAL` when replication key is present, else `FULL_TABLE`
- Pagination: OData `d.__next`

## Authentication

Supported options:

1. Basic Authentication with username and password
2. OAuth token endpoint with either:
   - refresh token flow
   - saml assertion bearer flow

Example config:

```json
{
  "api_server": "https://<company>.successfactors.com",
  "client_id": "...",
  "user_id": "...",
  "company_id": "...",
  "username": "...",
  "password": "...",
  "start_date": "2024-01-01T00:00:00Z"
}
```

## Quick Start

```bash
python3 -m venv /usr/local/share/virtualenvs/tap-sap-success-factors
source /usr/local/share/virtualenvs/tap-sap-success-factors/bin/activate
cd /opt/code/tap-sap-success-factors
pip install -U pip
pip install -e .
```

Discover:

```bash
tap-sap-success-factors --config /tmp/tap_config.json --discover > /tmp/catalog.json
```

Sync:

```bash
tap-sap-success-factors --config /tmp/tap_config.json --catalog /tmp/catalog.json > /tmp/sync_output.json 2>/tmp/sync_errors.log
tail -1 /tmp/sync_output.json > /tmp/state.json
```

Sync with state:

```bash
tap-sap-success-factors --config /tmp/tap_config.json --catalog /tmp/catalog.json --state /tmp/state.json > /tmp/sync_output_2.json 2>/tmp/sync_errors_2.log
```

## Streams Requiring Special Access

Typical permissions needed:
- Employee Data Export
- Foundation Object access
- Position Management access
- Compensation access
- Time Off access
- Onboarding Integration (for onboarding entities if added)

## Rate Limiting

The tap retries HTTP `429` and `5xx` responses using exponential backoff and `Retry-After` when available.

## Pagination

Pagination uses OData v2 next-link (`d.__next`) traversal until exhaustion.

## Full API Reference Coverage

SAP API reference pages (including [CalibrationTemplate](https://help.sap.com/docs/successfactors-platform/sap-successfactors-api-reference-guide-odata-v2/calibrationtemplate))
explicitly point to API Center Data Dictionary and live `$metadata` for complete field-level definitions.

## Bookmarking

Incremental streams store bookmarks in Singer state using each stream's replication key:

```json
{
  "bookmarks": {
    "per_person": {
      "lastModifiedDateTime": "2024-10-10T00:00:00.000000Z"
    }
  }
}
```

## Parent-Child Streams

Tap uses Navigation Properties in OData metadata to identify parent-child relationships. Child streams are probed with filters based on parent stream replication keys.

## Development

Run tests:

```bash
pytest tests/unittests --verbose --cov=tap_sap_success_factors --cov-report=term-missing
```

Run lint:

```bash
pylint tap_sap_success_factors
flake8 tap_sap_success_factors --max-line-length=120
```
