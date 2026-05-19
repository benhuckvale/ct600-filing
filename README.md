# ct600-filing

A command-line tool to file a CT600 Corporation Tax return with HMRC.

You fill in a YAML file with your company's figures, and the tool translates it into the XML format HMRC expects and submits it.

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
  irmark.py    — computes the IRmark (SHA-1 of canonicalised body, element removed)
  submit.py    — HTTP POST to LTS / TIL / production
  lts.py       — LTS manager (download, install artefacts, start, stop, status)
return.yaml    — CT600 template — copy to returns/ and fill in each year
returns/       — your actual returns (gitignored)
tests/
  test_build.py    — unit tests for XML generation
  test_irmark.py   — unit tests for IRmark computation
  test_lts.py      — integration tests (require running LTS)
lts/               — HMRC's Local Test Service (Java, not committed to git)
reference/
  README.md    — technical references: HMRC specs, schema notes, links
```

## What is the LTS?

The **Local Test Service** is a Java/Jetty application distributed by HMRC for software developers. It runs a local HTTP server on port 5665 that behaves like the production TPVS gateway — it validates your XML against the CT600 XSD schema, checks the IRmark, and returns a `GovTalkMessage` response. It never contacts HMRC.

The LTS is configured by **RIM artefacts** — per-service packages (XSD schema, Schematron rules) distributed separately by HMRC and installed with `pdm run lts install`.
