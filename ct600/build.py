from lxml import etree
from ct600.irmark import compute_irmark

GOVTALK_NS = "http://www.govtalk.gov.uk/CM/envelope"
CT_NS = "http://www.govtalk.gov.uk/taxation/CT/5"
G = f"{{{GOVTALK_NS}}}"
C = f"{{{CT_NS}}}"


def _el(parent: etree._Element, tag: str, text: object = None, **attrib) -> etree._Element:
    e = etree.SubElement(parent, tag, **attrib)
    if text is not None:
        e.text = str(text)
    return e


def _fmt(n: object) -> str:
    return f"{float(n):.2f}"


def build_xml(data: dict, gateway_test: bool = True) -> bytes:
    """Build a GovTalkMessage XML document from a CT600 return data dict."""
    company = data["company"]
    period = data["period"]
    creds = data.get("credentials", {})

    root = etree.Element(
        f"{G}GovTalkMessage",
        nsmap={None: GOVTALK_NS, "xsi": "http://www.w3.org/2001/XMLSchema-instance"},
    )
    _el(root, f"{G}EnvelopeVersion", "2.0")

    # --- Header ---
    header = _el(root, f"{G}Header")
    msg = _el(header, f"{G}MessageDetails")
    _el(msg, f"{G}Class", "HMRC-CT-CT600")
    _el(msg, f"{G}Qualifier", "request")
    _el(msg, f"{G}Function", "submit")
    _el(msg, f"{G}CorrelationID")
    _el(msg, f"{G}Transformation", "XML")
    _el(msg, f"{G}GatewayTest", "1" if gateway_test else "0")

    sender = _el(header, f"{G}SenderDetails")
    id_auth = _el(sender, f"{G}IDAuthentication")
    _el(id_auth, f"{G}SenderID", creds.get("sender_id", "dummy"))
    auth = _el(id_auth, f"{G}Authentication")
    _el(auth, f"{G}Method", "clear")
    _el(auth, f"{G}Role", "Principal")
    _el(auth, f"{G}Value", creds.get("password", "dummy"))

    # --- GovTalkDetails ---
    gtd = _el(root, f"{G}GovTalkDetails")
    keys = _el(gtd, f"{G}Keys")
    _el(keys, f"{G}Key", company["utr"], Type="UTR")
    target = _el(gtd, f"{G}TargetDetails")
    _el(target, f"{G}Organisation", "HMRC")
    routing = _el(gtd, f"{G}ChannelRouting")
    channel = _el(routing, f"{G}Channel")
    _el(channel, f"{G}URI", creds.get("vendor_id", "0000"))
    _el(channel, f"{G}Product", creds.get("product", "ct600-filing"))
    _el(channel, f"{G}Version", creds.get("version", "1.0"))

    # --- Body ---
    body = _el(root, f"{G}Body")
    ir_env = etree.SubElement(body, f"{C}IRenvelope", nsmap={None: CT_NS})

    ir_hdr = _el(ir_env, f"{C}IRheader")
    ir_keys = _el(ir_hdr, f"{C}Keys")
    _el(ir_keys, f"{C}Key", company["utr"], Type="UTR")
    _el(ir_hdr, f"{C}PeriodEnd", period["to"])
    _el(ir_hdr, f"{C}DefaultCurrency", "GBP")
    manifest = _el(ir_hdr, f"{C}Manifest")
    contains = _el(manifest, f"{C}Contains")
    ref = _el(contains, f"{C}Reference")
    _el(ref, f"{C}Namespace", CT_NS)
    _el(ref, f"{C}SchemaVersion", "2022-v1.99")
    _el(ref, f"{C}TopElementName", "CompanyTaxReturn")
    # Placeholder — will be replaced after computing hash over the body
    irmark_el = _el(ir_hdr, f"{C}IRmark", "", Type="generic")
    _el(ir_hdr, f"{C}Sender", "Company")

    # --- CompanyTaxReturn ---
    ctr = _el(ir_env, f"{C}CompanyTaxReturn", ReturnType="new")

    ci = _el(ctr, f"{C}CompanyInformation")
    _el(ci, f"{C}CompanyName", company["name"])
    _el(ci, f"{C}RegistrationNumber", company["registration_number"])
    _el(ci, f"{C}Reference", company["utr"])
    _el(ci, f"{C}CompanyType", str(company.get("type", 6)))
    pc = _el(ci, f"{C}PeriodCovered")
    _el(pc, f"{C}From", period["from"])
    _el(pc, f"{C}To", period["to"])

    ris = _el(ctr, f"{C}ReturnInfoSummary")
    accts_el = _el(ris, f"{C}Accounts")
    comps_el = _el(ris, f"{C}Computations")
    no_accounts_reason = data.get("no_accounts_reason")
    if no_accounts_reason:
        _el(accts_el, f"{C}NoAccountsReason", no_accounts_reason)
        _el(comps_el, f"{C}NoComputationsReason", no_accounts_reason)
    else:
        _el(accts_el, f"{C}ThisPeriodAccounts", "yes")
        _el(comps_el, f"{C}ThisPeriodComputations", "yes")

    turnover = _el(ctr, f"{C}Turnover")
    _el(turnover, f"{C}Total", _fmt(data["turnover"]["total"]))

    ctc = _el(ctr, f"{C}CompanyTaxCalculation")
    income_el = _el(ctc, f"{C}Income")
    trading_el = _el(income_el, f"{C}Trading")
    td = data["income"]["trading"]
    _el(trading_el, f"{C}Profits", _fmt(td["profits"]))
    lbf = float(td.get("losses_brought_forward", 0))
    if lbf:
        _el(trading_el, f"{C}LossesBroughtForward", _fmt(lbf))
    _el(trading_el, f"{C}NetProfits", _fmt(td["net_profits"]))

    _el(ctc, f"{C}ProfitsBeforeOtherDeductions", _fmt(data["profits_before_other_deductions"]))
    charges = _el(ctc, f"{C}ChargesAndReliefs")
    _el(charges, f"{C}ProfitsBeforeDonationsAndGroupRelief", _fmt(data["profits_before_donations_and_group_relief"]))
    _el(ctc, f"{C}ChargeableProfits", _fmt(data["chargeable_profits"]))

    ct_data = data["corporation_tax"]
    ct_chargeable = _el(ctc, f"{C}CorporationTaxChargeable")
    fy1 = _el(ct_chargeable, f"{C}FinancialYearOne")
    _el(fy1, f"{C}Year", str(ct_data["financial_year_1"]["year"]))
    d1 = _el(fy1, f"{C}Details")
    _el(d1, f"{C}Profit", _fmt(ct_data["financial_year_1"]["profit"]))
    _el(d1, f"{C}TaxRate", _fmt(ct_data["financial_year_1"]["tax_rate"]))
    _el(d1, f"{C}Tax", _fmt(ct_data["financial_year_1"]["tax"]))
    if "financial_year_2" in ct_data:
        fy2 = _el(ct_chargeable, f"{C}FinancialYearTwo")
        _el(fy2, f"{C}Year", str(ct_data["financial_year_2"]["year"]))
        d2 = _el(fy2, f"{C}Details")
        _el(d2, f"{C}Profit", _fmt(ct_data["financial_year_2"]["profit"]))
        _el(d2, f"{C}TaxRate", _fmt(ct_data["financial_year_2"]["tax_rate"]))
        _el(d2, f"{C}Tax", _fmt(ct_data["financial_year_2"]["tax"]))

    _el(ctc, f"{C}CorporationTax", _fmt(ct_data["total"]))
    _el(ctc, f"{C}NetCorporationTaxChargeable", _fmt(data["net_corporation_tax_chargeable"]))
    reliefs = _el(ctc, f"{C}TaxReliefsAndDeductions")
    _el(reliefs, f"{C}TotalReliefsAndDeductions", _fmt(data["tax_reliefs_and_deductions"]["total"]))

    calc = _el(ctr, f"{C}CalculationOfTaxOutstandingOrOverpaid")
    _el(calc, f"{C}NetCorporationTaxLiability", _fmt(data["calculation"]["net_corporation_tax_liability"]))
    _el(calc, f"{C}TaxChargeable", _fmt(data["calculation"]["tax_chargeable"]))
    _el(calc, f"{C}TaxPayable", _fmt(data["calculation"]["tax_payable"]))

    decl = _el(ctr, f"{C}Declaration")
    _el(decl, f"{C}AcceptDeclaration", "yes")
    _el(decl, f"{C}Name", data["declaration"]["name"])
    _el(decl, f"{C}Status", data["declaration"]["status"])

    # Compute IRmark over the body element and insert it
    irmark_el.text = compute_irmark(body)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")
