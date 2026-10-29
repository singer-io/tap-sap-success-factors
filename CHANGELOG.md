# Changelog

## 0.2.0
- Update parent-child relationship with key-composition based workflow.[#10](https://github.com/singer-io/tap-sap-success-factors/pull/10)

## 0.1.1
- Fix stale `effective_bookmark` cache in `BaseStream.sync()` that let a stream re-synced multiple times in one run (e.g. a child stream synced once per parent record) silently drop valid records as the bookmark kept advancing mid-run.[#9](https://github.com/singer-io/tap-sap-success-factors/pull/9)

## 0.1.0
- Added support for SAML bearer OAuth authentication with private key.[#6](https://github.com/singer-io/tap-sap-success-factors/pull/6)

## 0.0.2
- Add changes to prevent SSRF.[#5](https://github.com/singer-io/tap-sap-success-factors/pull/5)

## 0.0.1
- Initial production-oriented implementation of `tap-sap-success-factors`.
