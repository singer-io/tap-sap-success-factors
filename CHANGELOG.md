# Changelog

## 0.1.1
- Fixed data loss on INCREMENTAL child streams (e.g. `per_email`): the child's own replication-key date filter was incorrectly combined with its parent-scoped filter, dropping historical records never independently modified. [SAC-32475](https://qlik-dev.atlassian.net/browse/SAC-32475)
- Fixed a pass-through parent stream (synced only to reach a selected child) incorrectly advancing its own bookmark before ever writing its records.

## 0.1.0
- Added support for SAML bearer OAuth authentication with private key.[#6](https://github.com/singer-io/tap-sap-success-factors/pull/6)

## 0.0.2
- Add changes to prevent SSRF.[#5](https://github.com/singer-io/tap-sap-success-factors/pull/5)

## 0.0.1
- Initial production-oriented implementation of `tap-sap-success-factors`.
