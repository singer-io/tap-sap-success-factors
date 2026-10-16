# Changelog

## 0.2.0
- Flatten to-one navigation properties into stream schemas and expand only selected lookups. Discovery now validates expansions, retains readable streams when optional lookups are unsupported, and marks those fields unsupported.[#8](https://github.com/singer-io/tap-sap-success-factors/pull/8)

## 0.1.1
- Fix stale `effective_bookmark` cache in `BaseStream.sync()` that let a stream re-synced multiple times in one run (e.g. a child stream synced once per parent record) silently drop valid records as the bookmark kept advancing mid-run.[#9](https://github.com/singer-io/tap-sap-success-factors/pull/9)

## 0.1.0
- Added support for SAML bearer OAuth authentication with private key.[#6](https://github.com/singer-io/tap-sap-success-factors/pull/6)

## 0.0.2
- Add changes to prevent SSRF.[#5](https://github.com/singer-io/tap-sap-success-factors/pull/5)

## 0.0.1
- Initial production-oriented implementation of `tap-sap-success-factors`.
