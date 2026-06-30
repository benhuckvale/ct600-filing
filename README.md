# ct600-filing

A command-line tool to file a CT600 Corporation Tax return with HMRC.

You fill in a YAML file with your company's figures, and the tool translates it into the XML format HMRC expects and submits it.

HMRC's free **Company Accounts and Tax Online (CATO)** service — the joint HMRC/Companies House service many small companies used to file accounts and a CT600 online — closed on **31 March 2026**, leaving commercial software as the main route to file. This is an open, self-hosted alternative for the micro-entity (FRS 105) case.

## How HMRC submission works

HMRC accepts CT600 returns as a `GovTalkMessage` XML document posted over HTTP to their Transaction Processing and Validation Service (TPVS). The document contains:

- An outer **GovTalk envelope** with your credentials and UTR (Unique Taxpayer Reference)
- An inner **IRenvelope** containing the CT600 form fields
- An **IRmark** — a SHA-1 hash of the canonicalised body, base64-encoded — which HMRC uses to verify the document hasn't been tampered with

There are three submission targets:

| Target | Command flag | What it does |
|--------|-------------|--------------|
| **LTS** | `--lts` (default) | Local Test Service — runs on your machine, no HMRC contact |
| **Test-in-Live (TIL)** | `--til` | Real HMRC endpoint, real credentials — validates end-to-end but doesn't file |
| **Production** | `--live` | Actual filing — asks for confirmation before submitting |

TIL works by appending `-TIL` to the message class (`HMRC-CT-CT600-TIL`). HMRC validates the submission fully and sends a confirmation email, but nothing is recorded as a real filing.

## Prerequisites

- Python 3.11+
- [PDM](https://pdm-project.org/) (`brew install pdm` or `pip install pdm`)
- Java (for the LTS) — `java -version` should work
- HMRC Government Gateway credentials (for TIL/live only)

## Setup

```bash
pdm install
```

## Credentials

For TIL and live submissions, put your Government Gateway credentials in a `.env` file:

```bash
cp .env.example .env
# edit .env with your real username and password
```

The `.env` file is gitignored. Credentials in `.env` override whatever is in the YAML file.

## Filling in your return

Copy `return.yaml` to `returns/return-YYYY-MM-DD.yaml` (the `returns/` directory is gitignored):

```bash
cp return.yaml returns/return-2025-09-30.yaml
```

Every field has a comment explaining what it is and which CT600 box it corresponds to. For a simple company with trading income only, you'll need:

- `company` — name, Companies House number, UTR
- `period` — accounting period start and end dates
- `no_accounts_reason` — must be one of the allowed values (see below)
- `turnover`, `income`, `corporation_tax` — your figures
- `small_profits_rate: true` — if your profits are below £50,000 (19% rate)
- `declaration` — name and role of the person signing

### Accounts and computations

HMRC requires iXBRL accounts and computations with a CT600. If you're filing accounts separately at Companies House (the normal approach for micro-entities), set `no_accounts_reason` to one of these exact values:

| Value | When to use |
|-------|-------------|
| `Other - PDF attached with explanation` | Micro-entity accounts filed separately at Companies House |
| `Company dormant` | |
| `Not within charge to CT` | |
| `Amendment - a/cs already submitted` | |

The value must match exactly — it's a fixed enumeration in HMRC's schema, not free text.

## Running

```bash
# Build the XML and print it — no submission
pdm run ct600-cli returns/return-2025-09-30.yaml --dry-run

# Submit to the local LTS
pdm run ct600-cli returns/return-2025-09-30.yaml --lts

# Submit to HMRC Test-in-Live (validates end-to-end, sends confirmation email)
pdm run ct600-cli returns/return-2025-09-30.yaml --til

# Production filing (will ask for confirmation)
pdm run ct600-cli returns/return-2025-09-30.yaml --live
```

Write the generated XML to a file for inspection:

```bash
pdm run ct600-cli returns/return-2025-09-30.yaml --dry-run --output submission.xml
```

## Recommended workflow

1. Fill in `returns/return-YYYY-MM-DD.yaml` with your figures
2. `--lts` — validates schema, business rules, and IRmark locally
3. `--til` — confirms your credentials work and HMRC accepts the submission end-to-end; you'll receive a confirmation email
4. `--live` — the real filing

## Testing

### Unit tests (no LTS needed)

```bash
pdm run test-unit
```

### Integration tests against the LTS

The **Local Test Service (LTS)** is a Java application provided by HMRC that runs a mock submission gateway on your machine. It validates your XML against the real CT600 XSD schema and ~2,400 Schematron business rules, and verifies the IRmark.

**First-time setup** — three steps, each only needed once:

```bash
# 1. Download and unzip the LTS itself (~33 MB) from HMRC
pdm run lts download

# 2. Download the CT600 schema and validation rules from the HMRC feed
pdm run lts install

# 3. Start it
pdm run lts start
```

The LTS download page is at:
https://www.gov.uk/government/publications/local-test-service-and-lts-update-manager

**Start/stop the LTS:**

```bash
pdm run lts start    # starts in background, polls until ready (~15s)
pdm run lts stop     # stops it
pdm run lts status   # check if it's running
```

**Run integration tests:**

```bash
pdm run test-lts
```

**Run everything:**

```bash
pdm run test         # integration tests skip cleanly if LTS isn't running
```

## Project structure

```
ct600/
  cli.py       — Click CLI entry point
  build.py     — translates the YAML data dict into GovTalkMessage XML
  ixbrl.py     — shared inline-XBRL builder (contexts, facts, units, dimensions)
  accounts.py  — FRS 105 micro-entity iXBRL accounts
  computation.py — CT computation iXBRL (detailed P&L + tax bridge)
  irmark.py    — computes the IRmark (SHA-1 of canonicalised body, element removed)
  submit.py    — HTTP POST to LTS / TIL / production; records to submissions/
  lts.py       — LTS manager (download, install artefacts, start, stop, status)
return.yaml    — CT600 template — copy to returns/ and fill in each year
returns/       — your actual returns (gitignored)
submissions/   — per-attempt request/response audit trail (gitignored)
tests/
  test_build.py    — unit tests for XML generation
  test_irmark.py   — unit tests for IRmark computation
  test_lts.py      — integration tests (require running LTS)
lts/               — HMRC's Local Test Service (Java, not committed to git)
reference/
  README.md    — technical references: HMRC specs, schema notes, links
  ct600/       — cybermaggedon/ct600 worked examples (gitignored; `pdm run fetch-reference`)
```

See `AGENTS.md` for the agent/CLI contract and `TROUBLESHOOTING.md` for the
HMRC validation error catalogue.

## What is the LTS?

The **Local Test Service** is a Java/Jetty application distributed by HMRC for software developers. It runs a local HTTP server on port 5665 that behaves like the production TPVS gateway — it validates your XML against the CT600 XSD schema, checks the IRmark, and returns a `GovTalkMessage` response. It never contacts HMRC.

The LTS is configured by **RIM artefacts** — per-service packages (XSD schema, Schematron rules) distributed separately by HMRC and installed with `pdm run lts install`.

## How this compares

There are good tools in this space already; this one fills a specific niche.

- **[microaccounts.uk](https://microaccounts.uk/)** is a hosted web form that
  generates FRS 105 micro-entity *accounts* iXBRL — a genuinely nice, friendly
  tool. It produces the accounts document only. You still have to submit it.
- **[cybermaggedon/ct600](https://github.com/cybermaggedon/ct600)** (with
  [ixbrl-reporter](https://github.com/cybermaggedon/ixbrl-reporter)) is a more
  general and mature toolchain: ixbrl-reporter builds accounts and computation
  iXBRL from configurable templates and accounting sources (e.g. GnuCash), and
  ct600 submits. More powerful and flexible — and correspondingly more moving
  parts to set up.

By contrast, **this project** is a single self-contained CLI aimed squarely at
the micro-entity (FRS 105) case:

- one version-controlled **YAML file** in → accounts iXBRL **and** computation
  iXBRL **and** the CT600 envelope **and** submission — no separate templating
  system or accounting-package dependency;
- everything runs **locally**; your figures never leave your machine;
- **reproducible** year to year (edit the numbers, diff, regenerate), with a
  built-in submission audit trail.

It deliberately trades generality for focus: if you want a configurable,
multi-format toolchain, cybermaggedon's is the richer choice; if you want one
file and one command to file a micro-entity return, this is leaner.

A perfectly sensible workflow, in fact, is to use microaccounts.uk's form to
produce your accounts iXBRL — the form is a genuinely helpful reminder of *which*
fields a micro-entity needs — and then automate the GovTalk/IRmark submission to
HMRC with a script or an agent (Claude included).

Still, this project has a complete end-to-end workflow for essentially that.
The `returns/*.yaml` file plays the role of the form (the same field
checklist, but version-controlled and reusable), and the tool generates both
the accounts *and* the computation iXBRL, builds the envelope,
computes the IRmark, and submits.

## Acknowledgements

HMRC's iXBRL validation is unforgiving and barely documented in practice; a few
open resources made it far less painful, and genuine thanks go to all of them.

The two reference projects described above — cybermaggedon's **ct600** /
**ixbrl-reporter** and **microaccounts.uk** — were the most valuable: the first
for understanding how iXBRL fits together (materialise its worked examples with
`pdm run fetch-reference`), the second for confirming correct tagging when older
references had gone stale. Alongside them:

- **[SureFile Accounts — supported taxonomies](https://www.surefileaccounts.com/technical/taxonomies.html)**
  — a clear cross-reference for the FRC taxonomy entry-point URLs, especially handy
  when the FRC servers block automated access.
- **[FRC Taxonomies](https://www.frc.org.uk/library/standards-codes-policy/accounting-and-reporting/frc-taxonomies/)**
  and **[Taxonomies accepted by HMRC](https://www.gov.uk/government/publications/taxonomies-accepted-by-hm-revenue-and-customs)**
  — authoritative on which taxonomy version and entry point is valid for a given
  accounting period.
- **[HMRC Corporation Tax: support for software developers](https://www.gov.uk/government/collections/corporation-tax-online-support-for-software-developers)**
  and the **Local Test Service** — the schema, Schematron rules, IRmark
  specification, and local validator.

The specifics of what each helped resolve are in `TROUBLESHOOTING.md`.
