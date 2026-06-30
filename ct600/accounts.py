"""Generate FRS 105 micro-entity accounts as an iXBRL document.

A micro-entity set filed with HMRC is essentially a balance sheet (the lettered
CA2006 micro format) plus minimal notes and the director-approval / micro-entity
provisions statements. The detailed profit & loss goes in the *computation*
document (see computation.py), not here.

Tag names and context structure are taken from reference/ct600/accts.html.
"""
from ct600.ixbrl import IxbrlDocument, H, software_label
from lxml import etree

# --- taxonomy version -------------------------------------------------------
# FRC suite version HMRC accepts for periods ending in 2025 (FRC 2023/2024 both
# valid; using 2024). Confirm acceptance via Test-in-Live.
# https://www.gov.uk/government/publications/taxonomies-accepted-by-hm-revenue-and-customs
FRC_VERSION = "2024-01-01"

UK_CORE = f"http://xbrl.frc.org.uk/fr/{FRC_VERSION}/core"
UK_BUS = f"http://xbrl.frc.org.uk/cd/{FRC_VERSION}/business"
UK_DIREP = f"http://xbrl.frc.org.uk/reports/{FRC_VERSION}/direp"
UK_GEO = f"http://xbrl.frc.org.uk/cd/{FRC_VERSION}/countries"
# Micro-entity (FRS 105) accounts tag against the unified FRC entry point, which
# from the 2022 suite onward is the FRS-102 schema (it subsumes FRS 105, DPL and
# SECR). There is no separate FRS-105 entry point after 2021 — pointing at one
# yields ChRIS "schemaRef could not be obtained", which cascades into every FRC
# concept falling back to an anonymous fixed type. The fr/cd/reports namespaces
# above are shared across the suite and unchanged.
FRC_ACCOUNTS_SCHEMA = f"https://xbrl.frc.org.uk/FRS-102/{FRC_VERSION}/FRS-102-{FRC_VERSION}.xsd"
FRS105_SCHEMA = FRC_ACCOUNTS_SCHEMA  # backwards-compatible alias (imported by computation.py)

NSMAP = {
    "uk-core": UK_CORE,
    "uk-bus": UK_BUS,
    "uk-direp": UK_DIREP,
    "uk-geo": UK_GEO,
}

MATURITY_DIM = "uk-core:MaturitiesOrExpirationPeriodsDimension"

# A handful of descriptive concepts are NOT plain-text facts: ChRIS requires
# them to be empty, with the value carried by an explicit dimension member (the
# FRC "tag by dimension" pattern). Map our human-readable values to members.
LEGAL_FORM_MEMBERS = {
    "Private limited company": "uk-bus:PrivateLimitedCompanyLtd",
    "Public limited company": "uk-bus:PublicLimitedCompanyPlc",
    "Company limited by guarantee": "uk-bus:CompanyLimitedByGuaranteeWithoutShareCapital",
    "Limited liability partnership": "uk-bus:LimitedLiabilityPartnershipLLP",
}
COUNTRY_MEMBERS = {
    "England and Wales": "uk-geo:EnglandWales",
    "England": "uk-geo:England",
    "Wales": "uk-geo:Wales",
    "Scotland": "uk-geo:Scotland",
    "Northern Ireland": "uk-geo:NorthernIreland",
}

# yaml balance-sheet key -> (uk-core tag, maturity member or None)
BALANCE_SHEET_LINES = [
    ("fixed_assets", "uk-core:FixedAssets", None),
    ("current_assets", "uk-core:CurrentAssets", None),
    ("prepayments", "uk-core:PrepaymentsAccruedIncomeNotExpressedWithinCurrentAssetSubtotal", None),
    ("creditors_within_1y", "uk-core:Creditors", "uk-core:WithinOneYear"),
    ("net_current_assets", "uk-core:NetCurrentAssetsLiabilities", None),
    ("total_assets_less_current_liabilities", "uk-core:TotalAssetsLessCurrentLiabilities", None),
    ("creditors_after_1y", "uk-core:Creditors", "uk-core:AfterOneYear"),
    ("provisions", "uk-core:ProvisionsForLiabilitiesBalanceSheetSubtotal", None),
    ("accruals", "uk-core:AccruedLiabilitiesDeferredIncome", None),
    ("net_assets", "uk-core:NetAssetsLiabilities", None),
    ("equity", "uk-core:Equity", None),
]

BALANCE_SHEET_LABELS = {
    "fixed_assets": "Fixed assets",
    "current_assets": "Current assets",
    "prepayments": "Prepayments and accrued income",
    "creditors_within_1y": "Creditors: amounts falling due within one year",
    "net_current_assets": "Net current assets/(liabilities)",
    "total_assets_less_current_liabilities": "Total assets less current liabilities",
    "creditors_after_1y": "Creditors: amounts falling due after more than one year",
    "provisions": "Provisions for liabilities",
    "accruals": "Accruals and deferred income",
    "net_assets": "Net assets/(liabilities)",
    "equity": "Capital and reserves",
}

MICRO_PROVISIONS_STATEMENT = (
    "These financial statements have been prepared in accordance with the "
    "micro-entity provisions and the Financial Reporting Standard applicable to "
    "the Micro-entities Regime (FRS 105)."
)


def _h(parent, tag, text=None, **attrib):
    el = etree.SubElement(parent, f"{H}{tag}", **attrib)
    if text is not None:
        el.text = text
    return el


def build_accounts(data: dict) -> bytes:
    company = data["company"]
    period = data["period"]
    acc = data["accounts"]
    prior = acc["prior_period"]

    sw_name, sw_version = software_label(data)
    doc = IxbrlDocument(
        entity_number=company["registration_number"],
        schema_refs=[FRS105_SCHEMA],
        taxonomy_nsmap=NSMAP,
        title=f"{company['name']} — Micro-entity accounts",
        software=sw_name,
        software_version=sw_version,
    )

    # Contexts -------------------------------------------------------------
    cur_dur = doc.context(start=period["from"], end=period["to"])
    prior_dur = doc.context(start=prior["from"], end=prior["to"])
    cur_bs = doc.context(instant=period["to"])
    prior_bs = doc.context(instant=prior["to"])

    body = doc.body

    # --- Company information ---------------------------------------------
    _h(body, "h1", f"{company['name']}")
    _h(body, "p", "Unaudited micro-entity financial statements")
    _h(body, "p", f"For the year ended {period['to']}")

    info = _h(body, "table")
    def info_row(label, name, value, ctx=cur_dur):
        tr = _h(info, "tr")
        _h(tr, "td", label)
        td = _h(tr, "td")
        doc.text(td, name, value, ctx)

    def dim_row(label, display, name, dimension, member):
        """A descriptive concept tagged as an EMPTY fact whose value is the
        dimension member; ``member=None`` shows the text untagged (no fact)."""
        tr = _h(info, "tr")
        _h(tr, "td", label)
        td = _h(tr, "td", display)
        if member:
            ctx = doc.context(start=period["from"], end=period["to"],
                              dims={dimension: member})
            doc.text(td, name, "", ctx)

    info_row("Company name", "uk-bus:EntityCurrentLegalOrRegisteredName", company["name"])
    info_row("Company number", "uk-bus:UKCompaniesHouseRegisteredNumber", company["registration_number"])
    # Period-cover dates and the incorporation date are instant-typed.
    info_row("Period start", "uk-bus:StartDateForPeriodCoveredByReport", period["from"], ctx=cur_bs)
    info_row("Period end", "uk-bus:EndDateForPeriodCoveredByReport", period["to"], ctx=cur_bs)
    dim_row("Accounting standard", "Micro-entities", "uk-bus:AccountingStandardsApplied",
            "uk-bus:AccountingStandardsDimension", "uk-bus:Micro-entities")
    dim_row("Audit status", "Unaudited (audit exempt, no accountant's report)",
            "uk-bus:AccountsStatusAuditedOrUnaudited",
            "uk-bus:AccountsStatusDimension", "uk-bus:AuditExempt-NoAccountantsReport")
    # Completeness indicators ChRIS requires for a set of accounts.
    info_row("Trading status", "uk-bus:EntityTradingStatus", "")   # present (trading)
    info_row("Dormant", "uk-bus:EntityDormantTruefalse", "false")
    # Accounts type: the 2024+ concept is uk-bus:AccountsType (the old
    # AccountsTypeFullOrAbbreviated is no longer a reportable item — it errors
    # cvc-complex-type.2.4.a). Value carried by AccountsTypeDimension=FullAccounts.
    # Confirmed against a live FRS 105 sample (microaccounts.uk, FRC taxonomy).
    dim_row("Accounts type", "Full micro-entity accounts", "uk-bus:AccountsType",
            "uk-bus:AccountsTypeDimension", "uk-bus:FullAccounts")
    if acc.get("activities"):
        info_row("Principal activities", "uk-bus:DescriptionPrincipalActivities", acc["activities"])
    if acc.get("company_type"):
        dim_row("Legal form", acc["company_type"], "uk-bus:LegalFormEntity",
                "uk-bus:LegalFormEntityDimension", LEGAL_FORM_MEMBERS.get(acc["company_type"]))
    # SIC codes — uk-bus:SICCodeRecordedUKCompaniesHouse1..4 (Companies House allows up to 4)
    sic_codes = acc.get("sic_codes") or ([acc["sic_code"]] if acc.get("sic_code") else [])
    for i, code in enumerate(sic_codes[:4], start=1):
        info_row(f"SIC code {i}", f"uk-bus:SICCodeRecordedUKCompaniesHouse{i}", str(code))
    if acc.get("formation_date"):
        info_row("Date of incorporation", "uk-bus:DateFormationOrIncorporation", acc["formation_date"], ctx=cur_bs)
    if acc.get("jurisdiction"):
        dim_row("Jurisdiction of incorporation", acc["jurisdiction"],
                "uk-bus:CountryFormationOrIncorporation",
                "uk-geo:CountriesRegionsDimension", COUNTRY_MEMBERS.get(acc["jurisdiction"]))
    office = acc.get("registered_office", {})
    if office.get("line1"):
        info_row("Registered office", "uk-bus:AddressLine1", office["line1"])
    if office.get("line2"):
        info_row("Address line 2", "uk-bus:AddressLine2", office["line2"])
    if office.get("city"):
        info_row("Town/city", "uk-bus:PrincipalLocation-CityOrTown", office["city"])
    if office.get("county"):
        info_row("County/region", "uk-bus:CountyRegion", office["county"])
    if office.get("postcode"):
        info_row("Postcode", "uk-bus:PostalCodeZip", office["postcode"])
    info_row("Software", "uk-bus:NameProductionSoftware", doc.software)
    if doc.software_version:
        info_row("Software version", "uk-bus:VersionProductionSoftware", doc.software_version)
    # Balance sheet date (instant)
    info_row("Balance sheet date", "uk-bus:BalanceSheetDate", period["to"], ctx=cur_bs)

    # --- Balance sheet ----------------------------------------------------
    _h(body, "h2", "Statement of financial position")
    bs = acc["balance_sheet"]
    cur = bs["current"]
    pri = bs["prior"]

    table = _h(body, "table")
    hdr = _h(table, "tr")
    _h(hdr, "th", "")
    _h(hdr, "th", period["to"])
    _h(hdr, "th", prior["to"])

    for key, tag, member in BALANCE_SHEET_LINES:
        if key not in cur and key not in pri:
            continue
        tr = _h(table, "tr")
        _h(tr, "td", BALANCE_SHEET_LABELS[key])
        dims = {MATURITY_DIM: member} if member else None
        ctx_cur = doc.context(instant=period["to"], dims=dims) if member else cur_bs
        ctx_pri = doc.context(instant=prior["to"], dims=dims) if member else prior_bs
        td_c = _h(tr, "td")
        if cur.get(key) is not None:
            doc.num(td_c, tag, cur[key], ctx_cur, decimals=0)
        td_p = _h(tr, "td")
        if pri.get(key) is not None:
            doc.num(td_p, tag, pri[key], ctx_pri, decimals=0)

    # --- Micro-entity provisions statement + approval --------------------
    _h(body, "p", MICRO_PROVISIONS_STATEMENT)
    # TODO(pre-TIL): tag the micro-entity provisions statement with the exact
    # FRC uk-direp element once confirmed against the FRS 105 taxonomy.

    approved = _h(body, "p", "Approved by the board and signed on its behalf by: ")
    officer_ctx = doc.context(start=period["from"], end=period["to"],
                              dims={"uk-bus:EntityOfficersDimension": "uk-bus:Director1"})
    # Which director signed — empty fact; the officer is the dimension member.
    doc.text(approved, "uk-core:DirectorSigningFinancialStatements", "", officer_ctx)
    # The officer's name against the same dimension (also satisfies the ChRIS
    # rule that a referenced officer must have an associated name).
    doc.text(approved, "uk-bus:NameEntityOfficer", acc["director"], officer_ctx)
    if acc.get("approval_date"):
        dt = _h(body, "p", "Date approved: ")
        doc.text(dt, "uk-core:DateAuthorisationFinancialStatementsForIssue", acc["approval_date"], cur_bs)

    # --- Notes: average employees ----------------------------------------
    emp = acc.get("average_employees", {})
    if emp:
        _h(body, "h2", "Notes to the financial statements")
        note = _h(body, "p", "Average number of employees during the period: ")
        if emp.get("current") is not None:
            doc.num(note, "uk-core:AverageNumberEmployeesDuringPeriod", emp["current"], cur_dur, unit="pure", decimals=0)
        if emp.get("prior") is not None:
            sep = _h(body, "p", "Prior period average number of employees: ")
            doc.num(sep, "uk-core:AverageNumberEmployeesDuringPeriod", emp["prior"], prior_dur, unit="pure", decimals=0)

    return doc.tostring()
