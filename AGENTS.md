# Agent guide — ct600-filing

Generates a CT600 Company Tax Return (GovTalk envelope) with embedded iXBRL
micro-entity accounts (FRS 105) and CT computation, and submits it to HMRC.

This file is committed and tool-agnostic. It must contain **no personal data**
(no UTR, figures, names, or address). Those live only in gitignored files.

## Golden rule: no personal data in git

The following are gitignored and must stay that way — they carry the UTR,
financial figures, address and credentials:

- `returns/` — the source YAML returns
- `.env` — HMRC credentials
- `submissions/` — request/response audit trail and the running log
- `tax_return_*.txt`, `*.mhtml`, generated `*.xml` at repo root

Before any commit, verify nothing sensitive is staged:
`pdm run check-history` (scans history) and eyeball `git diff --cached`.

## Commit style

One-line subject. No body unless genuinely needed. **No `Co-Authored-By`
trailer.**

## Division of labour: CLI vs agent

The deterministic tool and the agent write **different files** and must not
edit each other's:

- **`ct600-cli` owns (machine-generated — never hand-edit):** the built
  submission XML, and per attempt `submissions/<stamp>-<target>/request.xml`,
  `response-NNN-<qualifier>.xml`, `attempt.json`. These are reproducible and may
  be regenerated.
- **Agent + user own (prose / judgement):** `submissions/log.md` (the running
  evidence narrative), optional per-attempt `submissions/<stamp>-<target>/notes.md`
  (analysis, error interpretation — kept separate from the machine `attempt.json`
  so it is never clobbered), and `returns/*.yaml` (source data).

The agent *reads* the machine artifacts and writes interpretation into the prose
files. The CLI does not write prose. See `submissions/README.md` for the layout.

## Workflow ladder

Climb in order; don't skip:

1. Edit `returns/<period>.yaml` with final figures.
2. `pdm run ct600 returns/<period>.yaml --dry-run -o out.xml` — build only.
3. `pdm run preview` — render the full submission (decodes embedded iXBRL) and
   eyeball the numbers.
4. `pdm run lts` then `--lts` — local schema/schematron/IRmark validation. NB:
   LTS does **not** check taxonomy-version-vs-period; only the real gateway does.
5. `--til` — Test-in-Live: real gateway, real credentials, triggers a
   confirmation email, does **not** file. Use this to prove the substance.
6. Tag, then `--live` — see below.

## Tagging and the software-version fact

The embedded iXBRL records the production-software version from
`git describe --tags --always --dirty` at build time. So:

- Build the live submission only from a **clean** tree (no `-dirty`).
- **Tag the final commit right before `--live`** (e.g. `git tag -a v1.0.0`) so
  the fact reads the tag, not a bare SHA. Do **not** tag prematurely — if a
  TIL-driven fix lands, the tag must sit on the final commit.

## Submissions are asynchronous

HMRC (til/live) returns an *acknowledgement* + CorrelationID first; the real
result is fetched by polling until the qualifier stops being `acknowledgement`.
`ct600.submit` does this and records every reply. A CorrelationID is cleared
from HMRC's poll queue once retrieved or after it ages out — polling a dead one
returns a generic enumeration error, not the result, so capture results live.

## Taxonomy notes

FRS-105 `2024-01-01` (accounts) and ct-comp `2024-01-01` (computation). The
`dpl` detailed-P&L taxonomy was removed in 2024; detailed P&L lines are tagged
with FRC `uk-core` concepts (or left untagged where no concept fits) to avoid
duplicate concept+context facts.

## Commands

- `pdm run test-unit` — unit tests
- `pdm run preview` — render a built submission as readable HTML
- `pdm run check-history` — scan git history for sensitive values
- `pdm run ct600 <yaml> [--dry-run|--lts|--til|--live] [-o file]`
- `pdm run lts` — start the local test service
