# Troubleshooting — CT600 / iXBRL submission

Field notes from getting a micro-entity (FRS 105) CT600 to validate against
HMRC's live gateway. Written for agents: the error messages are cryptic and the
fixes are specific, so this is an **error → meaning → fix** catalogue keyed on
the actual ChRIS text (grep for the message you got). Committed, no personal data.

See also `AGENTS.md` (workflow, data rules) and `submissions/README.md`.

## How submissions are validated (where each error surfaces)

Validation happens in stages, and errors surface **one stage at a time** — fixing
a stage reveals the next. Knowing the order saves confusion ("I fixed it, now
there are *more* errors" usually means you progressed to a deeper stage):

1. **GovTalk envelope schema** (transport). Malformed envelope → immediate error.
2. **XHTML well-formedness / schema** of the embedded iXBRL (e.g. the `<meta>`
   tag). ChRIS rejects here *before* it looks at any XBRL.
3. **Taxonomy resolution** — can ChRIS fetch the `schemaRef`? If not, every
   concept falls back to an anonymous type and you get a cascade.
4. **XBRL structure** — period types (instant/duration), units, dimensional
   validity against the taxonomy's hypercubes.
5. **Business rules** (ChRIS "Department" / joint-filing checks) — required
   facts, requires-element arcs, completeness indicators.

**LTS does not reach stages 3–5.** The local test service checks the envelope,
schematron and IRmark, but *not* taxonomy-version-vs-period or full XBRL/
dimensional validity. Those are only enforced at the real gateway (TIL or live).
So a green LTS proves very little about the iXBRL — **use TIL to validate
substance.**

## Diagnosis tools

- `pdm run show [attempt-dir]` — parse a recorded attempt and print the outcome
  + the list of ChRIS errors (default: latest). This is how you read results.
- `pdm run poll [attempt-dir]` — re-poll a pending CorrelationID and record the
  reply. HMRC is async: the first POST only *acknowledges*; the real result is
  fetched by polling. A CorrelationID is **cleared from the poll queue once
  retrieved or after it ages out** — polling a dead one returns a generic
  `enumeration '[request]'` error, not the result, so capture results promptly.
- The full request/response XML for every attempt is under `submissions/`.
- **When you don't know the correct tagging**, generate a known-good reference:
  `microaccounts.uk` has a live FRS 105 generator at `POST /api/accounts/generate`
  (JSON body; send `Origin: https://microaccounts.uk` or it 403s with "Request
  origin unknown"). Use **dummy data** — never send the real company's figures to
  a third party. Diff its iXBRL against ours to find the right concept/dimension.
- `reference/ct600/accts.html` + `ct.html` are worked examples (from
  cybermaggedon/ct600; run `pdm run fetch-reference` to materialise the gitignored
  `reference/ct600/`), but they are an **older taxonomy** (2021/2014) — good for
  structure, but concept names and modelling changed; verify against a current
  sample (above) before trusting them.

## Error catalogue

### `Attribute 'charset' not allowed in 'meta'` / `Attribute 'content' must appear`
- **Cause:** HTML5 `<meta charset="UTF-8">` is invalid in XHTML, which HMRC
  validates against.
- **Fix:** use the `http-equiv`/`content` form:
  `<meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>`.
  See `ct600/ixbrl.py` (IxbrlDocument head).

### `schemaRef … could not be obtained` / `error in the Taxonomy reference`
- **Cause:** the FRC schema URL doesn't resolve in ChRIS's catalog. We pointed at
  a **separate FRS-105 entry point** (`…/FRS-105/2024-01-01/FRS-105-2024-01-01.xsd`)
  which **does not exist after the 2021 suite**.
- **Fix:** micro-entities tag against the **unified FRS-102 entry point**
  (`https://xbrl.frc.org.uk/FRS-102/2024-01-01/FRS-102-2024-01-01.xsd`), which
  subsumes FRS 105, DPL and SECR. See `ct600/accounts.py` `FRC_ACCOUNTS_SCHEMA`.
- **Tell-tale:** when the schema doesn't resolve, you *also* get a cascade of
  errors 1–N below (every FRC concept reported as an anonymous type). Fix the
  schemaRef first and most of them vanish.

### `cvc-length-valid: Value 'X' … length '0' for type '#AnonType_fixedItemType'`<br>and `Element 'uk-bus:…' must have no element [children]`
- **Cause (if the schema is resolving):** the concept is an **enumeration tagged
  by dimension**, not free text. ChRIS wants the element **empty**, with the value
  carried by an explicit dimension member.
- **Fix:** emit an empty `ix:nonNumeric`, and put the value in the context as an
  `explicitMember`. Mapping we use (see `ct600/accounts.py` `dim_row`):
  | concept | dimension | member |
  |---|---|---|
  | `AccountingStandardsApplied` | `AccountingStandardsDimension` | `Micro-entities` |
  | `AccountsStatusAuditedOrUnaudited` | `AccountsStatusDimension` | `AuditExempt-NoAccountantsReport` |
  | `LegalFormEntity` | `LegalFormEntityDimension` | `PrivateLimitedCompanyLtd` |
  | `CountryFormationOrIncorporation` (uk-geo) | `CountriesRegionsDimension` | `EnglandWales` |
  | `DirectorSigningFinancialStatements` | `EntityOfficersDimension` | `Director1` |
- **Cause (if the schema is *not* resolving):** see the schemaRef error above —
  this is just the cascade.

### `Monetary item '…' uses non-ISO-4217 currency measure '{http://www.iso.org/iso/iso4217}GBP'`
- **Cause:** wrong namespace for the currency unit. XBRL's ISO-4217 namespace is
  **xbrl.org's**, not iso.org's.
- **Fix:** `iso4217` = `http://www.xbrl.org/2003/iso4217`. See `ct600/ixbrl.py`.

### `Item '…' requires an instant but its context contains a duration` (PeriodTypeDurationError)
- **Cause:** the concept is **instant**-typed but we put it in a start/end
  (duration) context. Affects identity/date items: ct-comp `CompanyName`,
  `TaxReference`, `StartOfPeriodCoveredByReturn`, `…PeriodOfAccount…`,
  `NameOfProductionSoftware`, `VersionOfProductionSoftware`; uk-bus
  `StartDateForPeriodCoveredByReport`, `EndDateForPeriodCoveredByReport`,
  `DateFormationOrIncorporation`.
- **Fix:** give them an instant context (we use the period-end date). Note
  `CompanyIsAPartnerInAFirm` is the exception — it's **duration**-typed.

### `The presence of '…CompanyName' requires the presence of '…CompanyIsAPartnerInAFirm'`
- **Cause:** a requires-element arc — reporting CompanyName obliges you to also
  report `CompanyIsAPartnerInAFirm`.
- **Fix:** emit `ct-comp:CompanyIsAPartnerInAFirm` = `false` (duration context).

### `xbrldie:PrimaryItemDimensionallyInvalidError … requires dimension '…BusinessTypeDimension' but it is not reported`
- **Cause:** **ct-comp 2024 is dimensional.** Every ct-comp primary item belongs
  to a hypercube that *requires* a dimension. Plain (undimensioned) facts are
  invalid.
- **Fix (see `ct600/computation.py`):**
  - Company-level items (identity, computation bridge, tax, losses) →
    `BusinessTypeDimension = ct-comp:Company`.
  - Trade-level `ProfitLossPerAccounts` → the full trade segment:
    `BusinessTypeDimension=Trade`, `TerritoryDimension=UK`,
    `LossReformDimension=Post-lossReform`, and a **typed** `BusinessNameDimension`
    wrapping `<ct-comp:BusinessNameDomain>` (the business name).
  - The FRC `uk-core` detailed-P&L lines are **non-dimensional** — do *not* add
    a dimension to them, or you'll get the inverse error.

### `Generic dimension member (bus:Director1) has no associated name or description`
- **Cause:** referencing an officer via `EntityOfficersDimension=Director1`
  obliges you to give that officer a name.
- **Fix:** emit `uk-bus:NameEntityOfficer` = the director's name on the *same*
  officer dimension/context.

### `Trading/non-trading indicator (bus:EntityTradingStatus) is missing`<br>`Dormant/non-dormant indicator (bus:EntityDormantTruefalse) is missing`
- **Cause:** required completeness indicators.
- **Fix:** emit `uk-bus:EntityTradingStatus` (empty, present = trading) and
  `uk-bus:EntityDormantTruefalse` = `false`.

### `cvc-complex-type.2.4.a: Invalid content … '…business}AccountsTypeFullOrAbbreviated'. One of '{xbrli:item, …}' is expected`
- **Cause:** `AccountsTypeFullOrAbbreviated` was **retired as a reportable item**
  in the FRC 2024+ suite (it's declared but not in the item substitution group).
  The 2014–2021 form (empty + `AccountsTypeDimension`) no longer validates.
- **Catch-22:** omit it and you get `bus:AccountsType is missing` instead.
- **Fix:** the 2024+ concept is **`uk-bus:AccountsType`** (empty, value via
  `AccountsTypeDimension = FullAccounts`). Found by generating a live FRS 105
  sample from microaccounts.uk. See `ct600/accounts.py`.

### Gateway returns only `acknowledgement` for a long time / no result
- **Cause:** HMRC's TIL service can back up (we saw 40+ min once, then ~30–70s
  when healthy). Not a code fault.
- **Fix:** keep polling (`pdm run poll`), or wait for the email. If a
  CorrelationID later returns the `enumeration '[request]'` error, it has aged
  out of the queue — that result is unrecoverable; resubmit.

## Taxonomy reference (what HMRC accepts for AP ending 30 Sep 2025)

- **FRC accounts:** unified entry point `https://xbrl.frc.org.uk/FRS-102/2024-01-01/FRS-102-2024-01-01.xsd`
  (FRC 2024 suite; valid to 31 Mar 2027). FRS 105 has no separate entry point
  post-2021. Namespaces: `fr/2024-01-01/core` (uk-core), `cd/2024-01-01/business`
  (uk-bus), `cd/2024-01-01/countries` (uk-geo), `reports/2024-01-01/direp`.
  URLs went **flat→nested** historically; 2024 uses the nested form above.
- **CT computation:** `http://www.hmrc.gov.uk/schemas/ct/comp/2024-01-01/ct-comp-2024.xsd`.
  The separate HMRC `dpl` (detailed P&L) taxonomy was removed; detailed P&L lines
  are tagged with FRC `uk-core` concepts instead.
- Authoritative list: HMRC "Taxonomies accepted by HMRC" on GOV.UK.

## Meta-lessons

- **One root cause often explains many errors.** 13 → 1; 36 → 1. Fix the
  deepest cause (schema resolution, currency ns, the dimensional model) before
  chasing individual lines.
- **A passing earlier round doesn't prove later stages.** TIL round 1 "passed"
  the taxonomy only because the `<meta>` error stopped ChRIS *before* it resolved
  the taxonomy. Don't conclude a stage is clean until ChRIS actually reaches it.
- **Verify tagging against a *current* sample**, not just the bundled 2021
  reference — concept names and modelling change between taxonomy years.
