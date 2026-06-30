# Reference Links

The detailed technical companion to the top-level `README.md`: the specifications,
schema notes, iXBRL taxonomy details, and external resources behind how this tool
builds and files a CT600. For the HMRC validation error catalogue, see
`TROUBLESHOOTING.md`.

---

## HMRC Developer Documentation

### [Corporation Tax Online: Support for Software Developers](https://www.gov.uk/government/collections/corporation-tax-online-support-for-software-developers)
The authoritative GOV.UK collection for everything needed to build CT600 filing software. Contains CT600 appendices, valid XML samples, RIM artefacts, IRmark specifications, and links to the LTS. Start here when the schema or a validation rule is unclear.

### [Local Test Service and LTS Update Manager](https://www.gov.uk/government/publications/local-test-service-and-lts-update-manager)
The download page for the LTS (currently v8.3). Requires Java 11+. The LTS runs a local Jetty server on port 5665 that validates submitted XML against the real CT600 XSD schema and ~2,400 Schematron business rules, and verifies the IRmark.

### [HMRC Developer Hub — API Documentation](https://developer.service.hmrc.gov.uk/api-documentation/docs/api)
The HMRC Developer Hub. The CT600 submission API is an XML-over-HTTP service (GovTalkMessage envelope), not a REST/JSON API. This hub is mainly useful for the terms of use and for finding the production endpoint URL.

### [Corporation Tax Commercial Software Suppliers](https://www.gov.uk/government/publications/corporation-tax-commercial-software-suppliers/corporation-tax-commercial-software-suppliers)
Directory of 40+ commercial products that can file CT600. Useful as a reference for what features are required — products are categorised by capability (CT600 production, iXBRL submission, micro-entity support, etc.).

---

## Technical Specifications

### [Generic IRmark Specification v1.2 (PDF)](https://assets.publishing.service.gov.uk/media/5a7db692ed915d2ac884d1b4/generic-irmark-specification-v1-2.pdf)
The authoritative spec for computing the IRmark digital signature. Key points:
- Hash the `<Body>` element with the `<IRmark>` element **removed entirely** (not just emptied)
- Canonicalize using inclusive Canonical XML 1.0 (W3C, 2001)
- SHA-1 hash the C14N bytes
- Base64-encode the 20-byte digest → 28-character string

### [IRmark Step-by-Step Guide for GovTalk (PDF)](https://assets.publishing.service.gov.uk/media/5a74efece5274a3cb2868633/irmark_step_by_step_govtalk.pdf)
Worked example of the IRmark computation in the context of a GovTalk submission. Useful alongside the generic spec above.

### [XBRL Guide for UK Businesses](https://www.gov.uk/government/publications/xbrl-guide-for-uk-businesses/xbrl-guide-for-uk-businesses)
iXBRL accounts and computations have been mandatory for CT600 since April 2011. The CT600 XSD also allows `<NoAccountsReason>` / `<NoComputationsReason>` instead (fixed enumerations — see below).

This tool supports both paths: when the return YAML includes `accounts` and `computation` sections it **generates and embeds** FRS 105 micro-entity iXBRL accounts and a CT computation (the primary path — see *iXBRL Taxonomy* below); otherwise it falls back to a `NoAccountsReason` declaration.

---

## Schema Notes (from LTS XSD and Schematron)

The CT600 RIM artefacts are at `lts/LTS8.3/HMRCTools/RIMArtefacts/CT/CT600/2015-2016 v3/1.994/`.

| File | Contents |
|------|----------|
| `CT-2014-v1-994.xsd` | CT600 XML Schema — field types, lengths, enumerations |
| `CT-2014-v1-994.sch` | ~2,400 Schematron business rules (cross-field validation) |
| `envelope-v2-0-HMRC.xsd` | GovTalk envelope schema |

### `NoAccountsReason` / `NoComputationsReason` allowed values

These are fixed enumerations (max 40 chars). Use `"Other - PDF attached with explanation"` when filing accounts separately at Companies House.

**Accounts (`NoAccountsReason`):**
| Value | Meaning |
|-------|---------|
| `PoA differs from AP-a/cs with sep rtn` | Long period of account — accounts with accompanying return |
| `Company in liquidation` | |
| `Not within charge to CT` | |
| `Company dormant` | |
| `Amendment - a/cs already submitted` | |
| `Other - PDF attached with explanation` | Use this for micro-entity accounts filed separately |
| `PDF accounts attached with explanation` | |

**Computations (`NoComputationsReason`):**
| Value | Meaning |
|-------|---------|
| `PoA differs from AP-comp with sep rtn` | Long period of account — computations with accompanying return |
| `Company in liquidation` | |
| `Not within charge to CT` | |
| `Company dormant` | |
| `Amendment - comps already submitted` | |
| `Other - PDF attached with explanation` | Use this for computations filed separately |

### Key business rules (Schematron)

- **Rule 9150**: `LossesBroughtForward` (Box 160) must not be present if `Profits` (Box 155) is zero — omit the element rather than setting it to 0.
- **Rule 9145**: Company types 6, 7, 8 require a tax rate from the allowed set (full rate, small profits rate, or NI trading rate).
- **Rule 2021**: IRmark verification — the LTS recomputes the IRmark from the received body and rejects if it doesn't match.

---

## iXBRL Taxonomy

When the return YAML includes `accounts` and `computation` sections, the tool
tags the embedded documents against:

- **FRC accounts (FRS 105 micro-entity):** the unified FRS-102 entry point
  `https://xbrl.frc.org.uk/FRS-102/2024-01-01/FRS-102-2024-01-01.xsd` (FRC 2024
  suite — there is **no separate FRS-105 entry point after 2021**). Namespaces:
  `fr/2024-01-01/core` (uk-core), `cd/2024-01-01/business` (uk-bus),
  `cd/2024-01-01/countries` (uk-geo), `reports/2024-01-01/direp`.
- **CT computation:** `http://www.hmrc.gov.uk/schemas/ct/comp/2024-01-01/ct-comp-2024.xsd`
  (ct-comp 2024). Detailed P&L lines are tagged with FRC uk-core concepts — the
  separate HMRC `dpl` taxonomy was retired.

The hard part is the tagging itself (dimensional contexts, instant-vs-duration
periods, enumeration-by-dimension, concept renames such as `uk-bus:AccountsType`);
that is catalogued error-by-error in `TROUBLESHOOTING.md`.

### [FRC Taxonomies](https://www.frc.org.uk/library/standards-codes-policy/accounting-and-reporting/frc-taxonomies/)
The FRS 102 / FRS 105 accounts taxonomy suite. FRC servers block automated access,
so the entry-point URLs usually have to be cross-referenced from elsewhere.

### [Taxonomies accepted by HMRC](https://www.gov.uk/government/publications/taxonomies-accepted-by-hm-revenue-and-customs)
Which taxonomy version and entry point ChRIS accepts for a given accounting period
(the FRC 2024 suite is valid through 31 March 2027).

### [SureFile Accounts — supported taxonomies](https://www.surefileaccounts.com/technical/taxonomies.html)
A clear cross-reference for the FRC taxonomy entry-point URLs.

---

## Reference Implementations

### [cybermaggedon/ct600](https://github.com/cybermaggedon/ct600) + [ixbrl-reporter](https://github.com/cybermaggedon/ixbrl-reporter)
The open-source CT600 utility and its iXBRL generator. Together they were the
primary structural reference for this tool's GovTalk envelope, IRmark, and iXBRL
tagging. Their worked examples (`accts.html`, `ct.html`) are cited throughout
`TROUBLESHOOTING.md`; they live in the gitignored `reference/ct600/` — run
**`pdm run fetch-reference`** to clone the project (pinned commit) and populate it.

### [microaccounts.uk](https://microaccounts.uk/)
A hosted FRS 105 micro-entity accounts iXBRL generator. Generating a known-good
sample from its API confirmed the correct FRC 2024+ tagging (e.g. the
`uk-bus:AccountsType` rename) when the bundled 2021 reference had gone stale.

---

## Test-in-Live (TIL)

### [Basic guide for XML software developers — TIL](https://www.gov.uk/guidance/basic-guide-for-xml-software-developers#test-in-live-til)
TIL submits to HMRC's live gateway but doesn't reach their backend systems — credentials are validated, the XML is checked, but nothing is actually filed. Two requirements vs a normal submission:
1. `<Class>` must have a `-TIL` suffix: `HMRC-CT-CT600-TIL`
2. `GatewayTest` must be `0` (the live gateway schema rejects `1`)

The `--til` flag in this tool handles both automatically.

---

## Submission Endpoints

| Environment | URL | Notes |
|-------------|-----|-------|
| LTS (local test) | `http://localhost:5665/LTS/LTSPostServlet` | `GatewayTest=1`, class `HMRC-CT-CT600`, dummy credentials |
| Test-in-Live | `https://transaction-engine.tax.service.gov.uk/submission` | `GatewayTest=0`, class `HMRC-CT-CT600-TIL`, real credentials, sends confirmation email |
| Production | `https://transaction-engine.tax.service.gov.uk/submission` | `GatewayTest=0`, class `HMRC-CT-CT600`, real credentials, actual filing |

Content-Type for all: `application/x-binary`

HMRC (TIL/live) is **asynchronous**: the first POST returns an *acknowledgement*
with a CorrelationID; the real result is fetched by polling
`https://transaction-engine.tax.service.gov.uk/poll` until the qualifier stops
being `acknowledgement`. `ct600/submit.py` does this automatically and records
every exchange under `submissions/` (inspect with `pdm run show` / `pdm run poll`).
