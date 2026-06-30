# Reference Links

Technical references for the CT600 HMRC filing tool.

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
iXBRL accounts and computations have been mandatory for CT600 since April 2011. However, the CT600 XSD allows `<NoAccountsReason>` and `<NoComputationsReason>` instead. The valid reason codes are a fixed enumeration defined in the XSD (see below).

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

## Reference Implementations

### [cybermaggedon/ct600 (GitHub)](https://github.com/cybermaggedon/ct600)
Open-source Python/XSLT CT600 utility. Takes iXBRL accounts files and extracts data to populate CT600 fields. Supports LTS, Test-in-Live, and production submission. Useful as a reference for XML structure and LTS interaction, though it targets the full iXBRL workflow rather than the `no_accounts_reason` path used here.

Its worked iXBRL examples (`accts.html`, `ct.html`) are referenced throughout
`TROUBLESHOOTING.md`. They live in the gitignored `reference/ct600/` — run
**`pdm run fetch-reference`** to clone the project (pinned commit) and populate it.

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
| LTS (local test) | `http://localhost:5665/LTS/LTSPostServlet` | `GatewayTest=1`, dummy credentials |
| Test-in-Live | `https://transaction-engine.tax.service.gov.uk/submission` | `GatewayTest=1`, real credentials, sends confirmation email |
| Production | `https://transaction-engine.tax.service.gov.uk/submission` | `GatewayTest=0`, real credentials, actual filing |

Content-Type for all: `application/x-binary`
