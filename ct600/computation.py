"""Generate the Corporation Tax computation as an iXBRL document.

This document does two jobs HMRC needs alongside the CT600:
  * a Detailed Profit & Loss (the ``dpl:`` / ``uk-core:`` P&L lines — this is
    where turnover, staff costs etc. actually reach HMRC), and
  * the computation bridge from accounting result to taxable profit and tax.

Tag names and structure are taken from reference/ct600/ct.html.
"""
from ct600.ixbrl import IxbrlDocument, H, software_label
from ct600.accounts import NSMAP as FRC_NSMAP
from lxml import etree

# --- taxonomy version -------------------------------------------------------
# TODO(pre-TIL): for an accounting period ending 30 Sep 2025 HMRC accepts the
# "Corporation Tax computational 2024" taxonomy. Bump CT_VERSION/CT_YEAR and the
# DPL version to the accepted set and confirm via Test-in-Live before filing.
# 2021-01-01 is the known-good version from the worked example.
CT_VERSION = "2021-01-01"
CT_YEAR = "2021"

CT_COMP = f"http://www.hmrc.gov.uk/schemas/ct/comp/{CT_VERSION}"
DPL = f"http://www.hmrc.gov.uk/schemas/ct/dpl/{CT_VERSION}"
CT_COMP_SCHEMA = f"{CT_COMP}/ct-comp-{CT_YEAR}.xsd"
DPL_SCHEMA = f"{DPL}/dpl-{CT_YEAR}.xsd"

NSMAP = {
    "ct-comp": CT_COMP,
    "dpl": DPL,
    **FRC_NSMAP,
}

# Default Detailed P&L mapping. Each line must use a DISTINCT tag (XBRL forbids
# two facts with the same concept + context). Staff costs map to uk-core:
# WagesSalaries; remaining costs lump into OtherOperationalAdministrationCosts.
# TODO: break "other costs" down by real expense nature into distinct dpl: tags.
DEFAULT_DPL_LABELS = {
    "uk-core:TurnoverRevenue": "Turnover",
    "uk-core:WagesSalaries": "Staff costs",
    "dpl:OtherOperationalAdministrationCosts": "Other operating costs",
    "dpl:TotalCosts": "Total costs",
    "uk-core:ProfitLoss": "Profit/(loss) for the period",
}


def _h(parent, tag, text=None, **attrib):
    el = etree.SubElement(parent, f"{H}{tag}", **attrib)
    if text is not None:
        el.text = text
    return el


def build_computation(data: dict) -> bytes:
    company = data["company"]
    period = data["period"]
    comp = data["computation"]
    ct = data["corporation_tax"]

    sw_name, sw_version = software_label(data)
    doc = IxbrlDocument(
        entity_number=company["registration_number"],
        schema_refs=[CT_COMP_SCHEMA, DPL_SCHEMA],
        taxonomy_nsmap=NSMAP,
        title=f"{company['name']} — Corporation tax computation",
        software=sw_name,
        software_version=sw_version,
    )

    dur = doc.context(start=period["from"], end=period["to"])
    body = doc.body

    _h(body, "h1", f"{company['name']} — Corporation tax computation")
    _h(body, "p", f"For the period {period['from']} to {period['to']}")

    # Identity / period facts ---------------------------------------------
    ident = _h(body, "table")
    def irow(label, name, value, numeric=False, **kw):
        tr = _h(ident, "tr")
        _h(tr, "td", label)
        td = _h(tr, "td")
        if numeric:
            doc.num(td, name, value, dur, **kw)
        else:
            doc.text(td, name, value, dur)

    irow("Company name", "ct-comp:CompanyName", company["name"])
    irow("Tax reference (UTR)", "ct-comp:TaxReference", company["utr"])
    irow("Period start", "ct-comp:StartOfPeriodCoveredByReturn", period["from"])
    irow("Period end", "ct-comp:EndOfPeriodCoveredByReturn", period["to"])
    irow("Accounts period start", "ct-comp:PeriodOfAccountStartDate", period["from"])
    irow("Accounts period end", "ct-comp:PeriodOfAccountEndDate", period["to"])
    irow("Software", "ct-comp:NameOfProductionSoftware", doc.software)
    if doc.software_version:
        irow("Software version", "ct-comp:VersionOfProductionSoftware", doc.software_version)

    # --- Detailed profit & loss ------------------------------------------
    _h(body, "h2", "Detailed profit and loss account")
    pl = _h(body, "table")
    for line in comp["detailed_pl"]:
        tag = line["tag"]
        label = line.get("label") or DEFAULT_DPL_LABELS.get(tag, tag)
        tr = _h(pl, "tr")
        _h(tr, "td", label)
        td = _h(tr, "td")
        doc.num(td, tag, line["amount"], dur, decimals=2)

    # --- Computation bridge ----------------------------------------------
    _h(body, "h2", "Adjustment of profit / tax computation")
    bridge = _h(body, "table")
    def brow(label, name, value, decimals=2):
        tr = _h(bridge, "tr")
        _h(tr, "td", label)
        td = _h(tr, "td")
        doc.num(td, name, value, dur, decimals=decimals)

    brow("Profit/(loss) per accounts", "ct-comp:ProfitLossPerAccounts", comp["profit_loss_per_accounts"])
    brow("Net trading profits", "ct-comp:NetTradingProfits", comp.get("net_trading_profits", 0.0))
    brow("Profits before other deductions and reliefs", "ct-comp:ProfitsBeforeOtherDeductionsAndReliefs", comp.get("profits_before_other_deductions", 0.0))
    brow("Profits before charges and group relief", "ct-comp:ProfitsBeforeChargesAndGroupRelief", comp.get("profits_before_charges", 0.0))
    brow("Total profits chargeable to corporation tax", "ct-comp:TotalProfitsChargeableToCorporationTax", comp.get("total_profits_chargeable", 0.0))

    # --- Financial year split & tax --------------------------------------
    _h(body, "h2", "Tax payable")
    tax = _h(body, "table")
    def trow(label, name, value, decimals=2, year=False):
        tr = _h(tax, "tr")
        _h(tr, "td", label)
        td = _h(tr, "td")
        if year:
            doc.text(td, name, str(value), dur)
        else:
            doc.num(td, name, value, dur, decimals=decimals)

    fy1 = ct["financial_year_1"]
    trow("Financial year 1", "ct-comp:FinancialYear1CoveredByTheReturn", fy1["year"], year=True)
    trow("FY1 profit chargeable at first rate", "ct-comp:FY1AmountOfProfitChargeableAtFirstRate", fy1["profit"])
    trow("FY1 first rate of tax", "ct-comp:FY1FirstRateOfTax", fy1["tax_rate"])
    trow("FY1 tax at first rate", "ct-comp:FY1TaxAtFirstRate", fy1["tax"])
    if "financial_year_2" in ct:
        fy2 = ct["financial_year_2"]
        trow("Financial year 2", "ct-comp:FinancialYear2CoveredByTheReturn", fy2["year"], year=True)
        trow("FY2 profit chargeable at first rate", "ct-comp:FY2AmountOfProfitChargeableAtFirstRate", fy2["profit"])
        trow("FY2 first rate of tax", "ct-comp:FY2FirstRateOfTax", fy2["tax_rate"])
        trow("FY2 tax at first rate", "ct-comp:FY2TaxAtFirstRate", fy2["tax"])

    trow("Corporation tax chargeable", "ct-comp:CorporationTaxChargeable", ct.get("total", 0.0))
    trow("Tax chargeable", "ct-comp:TaxChargeable", data["calculation"]["tax_chargeable"])
    trow("Tax payable", "ct-comp:TaxPayable", data["calculation"]["tax_payable"])
    trow("Net corporation tax payable", "ct-comp:NetCorporationTaxPayable", data["calculation"]["net_corporation_tax_liability"])

    # --- Trading losses memorandum ---------------------------------------
    # These are amounts of *losses*; positive figures represent losses available
    # to carry, so they're shown in their own section rather than mixed in with
    # the signed profit bridge above.
    _h(body, "h2", "Trading losses memorandum")
    _h(body, "p", "Positive figures are amounts of trading losses available to carry forward.")
    mem = _h(body, "table")

    def mem_row(label, value, tag=None):
        tr = _h(mem, "tr")
        _h(tr, "td", label)
        td = _h(tr, "td")
        if tag:
            doc.num(td, tag, value, dur, decimals=2)
        else:
            td.text = f"{float(value):,.2f}"

    mem_row("Brought forward from earlier periods",
            comp.get("trading_losses_brought_forward", 0.0),
            tag="ct-comp:TradingLossesBroughtForward")
    arising = data.get("losses_arising", {}).get("trading_uk", 0.0)
    mem_row("Arising in this period", arising)
    mem_row("Carried forward to later periods",
            comp.get("trading_losses_carried_forward", 0.0))

    # --- Notes -----------------------------------------------------------
    if comp.get("note"):
        _h(body, "h2", "Notes")
        note = _h(body, "p", "")
        doc.text(note, "ct-comp:TextNote", comp["note"], dur)

    return doc.tostring()
