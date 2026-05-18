# ct600-filing

A command-line tool to file a CT600 Corporation Tax return with HMRC.

You fill in a YAML file with your company's figures, and the tool translates it into the XML format HMRC expects and submits it.

## How HMRC submission works

HMRC accepts CT600 returns as a `GovTalkMessage` XML document posted over HTTP to their Transaction Processing and Validation Service (TPVS). The document contains:

- An outer **GovTalk envelope** with your credentials and UTR (Unique Taxpayer Reference)
- An inner **IRenvelope** containing the CT600 form fields
- An **IRmark** — a SHA-1 hash of the body, base64-encoded — which HMRC uses to verify the document hasn't been tampered with

There are three submission targets:

| Target | Command flag | What it does |
|--------|-------------|--------------|
| **LTS** | `--lts` (default) | Local Test Service — runs on your machine, safe for development |
| **Test-in-Live (TIL)** | `--til` | Real HMRC endpoint with test credentials — sends a confirmation email |
| **Production** | `--live` | Actual filing — asks for confirmation before submitting |

## Prerequisites

- Python 3.11+
- [PDM](https://pdm-project.org/) (`brew install pdm` or `pip install pdm`)
- Java (for the LTS) — `java -version` should work
- HMRC Government Gateway credentials (for TIL/live only)

## Setup

```bash
pdm install
```

## Filling in your return

Edit `return.yaml`. Every field has a comment explaining what it is and which CT600 box it corresponds to. For a simple company with trading income only, you'll need to set:

- `company` — name, Companies House number, UTR
- `period` — accounting period start and end dates
- `turnover`, `income`, `corporation_tax` — your figures
- `declaration` — name and role of the person signing
- `credentials` — your Government Gateway details (leave as `dummy` for LTS testing)

## Running

```bash
# Build the XML and print it — no submission
pdm run ct600-cli --dry-run

# Submit to the local LTS (see Testing below)
pdm run ct600-cli --lts

# Submit to HMRC Test-in-Live (real endpoint, test credentials)
pdm run ct600-cli --til

# Production filing (will ask for confirmation)
pdm run ct600-cli --live
```

You can also write the generated XML to a file for inspection:

```bash
pdm run ct600-cli --dry-run --output submission.xml
```

## Testing

### Unit tests (no LTS needed)

```bash
pdm run test-unit
```

### Integration tests against the LTS

The **Local Test Service (LTS)** is a Java application provided by HMRC that runs a mock submission gateway on your machine. It validates your XML against the real CT600 schema and checks the IRmark, so it catches structural errors before you touch any real HMRC systems.

**First-time setup** — three steps, each only needed once:

```bash
# 1. Download and unzip the LTS itself (~33 MB) from HMRC
pdm run lts download

# 2. Download the CT600 schema and validation rules from the HMRC feed
pdm run lts install

# 3. Start it
pdm run lts start
```

The LTS is distributed by HMRC at:
https://www.gov.uk/government/publications/local-test-service-and-lts-update-manager

`pdm run lts download` fetches the current version automatically via the HMRC feed.
If you ever need to download it manually, the zip is at:
https://www.tpvs.hmrc.gov.uk/tools/v2/LTS8.3.zip

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
  irmark.py    — computes the IRmark (SHA-1 of canonicalised body)
  submit.py    — HTTP POST to LTS / TIL / production
  lts.py       — LTS manager (download, install artefacts, start, stop, status)
return.yaml    — your CT600 return — fill this in each year
tests/
  test_build.py    — unit tests for XML generation
  test_irmark.py   — unit tests for IRmark computation
  test_lts.py      — integration tests (require running LTS)
LTS8.3/            — HMRC's Local Test Service (Java, not committed to git)
```

## What is the LTS?

The **Local Test Service** is a Java/Jetty application distributed by HMRC for software developers. It runs a local HTTP server on port 5665 that behaves like the production TPVS gateway — it validates your XML against the CT600 XSD schema, checks the IRmark, and returns a `GovTalkMessage` response. It never contacts HMRC.

The LTS is configured by **RIM artefacts** — per-service packages (XSD schema, Schematron rules, a calculator) distributed separately by HMRC and installed with `pdm run lts install`.
