#!/usr/bin/env python3
"""Render a CT600 GovTalk XML file as a human-readable HTML page.

Renders the complete submission: the GovTalk envelope summary, the CT600 form
boxes, and — decoded from their base64 ``EncodedInlineXBRLDocument`` blobs — the
embedded iXBRL accounts and corporation tax computation.
"""

import sys
import html as _htmlmod
import base64
import webbrowser
import tempfile
import os
from lxml import etree

CT = "http://www.govtalk.gov.uk/taxation/CT/5"
GT = "http://www.govtalk.gov.uk/CM/envelope"
XHTML = "http://www.w3.org/1999/xhtml"
IX = "http://www.xbrl.org/2013/inlineXBRL"


def _text(el, *path):
    """Walk a sequence of tag names under el; return text or ''."""
    cur = el
    for tag in path:
        if cur is None:
            return ""
        cur = cur.find(f"{{{CT}}}{tag}")
    return (cur.text or "").strip() if cur is not None else ""


def _money(s):
    if not s:
        return ""
    try:
        v = float(s)
        if v == 0:
            return "0"
        return f"£{v:,.2f}"
    except ValueError:
        return s


def _row(box, label, value, highlight=False):
    cls = ' class="highlight"' if highlight else ""
    return f"<tr{cls}><td class='box'>{box}</td><td>{label}</td><td class='val'>{value}</td></tr>\n"


def _cell(td):
    """Visible text of a table cell, applying the iXBRL sign convention."""
    txt = "".join(td.itertext()).strip()
    fact = td.find(f"{{{IX}}}nonFraction")
    if fact is not None and fact.get("sign") == "-" and txt:
        txt = "-" + txt
    return _htmlmod.escape(txt)


def _render_embedded(b64_text):
    """Decode a base64 EncodedInlineXBRLDocument and rebuild it as clean,
    namespace-free HTML (headings, paragraphs, and the visible fact tables)."""
    raw = base64.b64decode(b64_text)
    doc = etree.fromstring(raw)
    body = doc.find(f"{{{XHTML}}}body")
    if body is None:
        return "<p><em>(could not parse embedded document)</em></p>"

    out = []
    for el in body.iterchildren():
        tag = etree.QName(el).localname
        if tag == "header":  # ix:header — declarations, not display
            continue
        if tag in ("h1", "h2", "h3"):
            out.append(f"<h3>{_htmlmod.escape(''.join(el.itertext()).strip())}</h3>")
        elif tag == "p":
            text = "".join(el.itertext()).strip()
            if text:
                out.append(f"<p>{_htmlmod.escape(text)}</p>")
        elif tag == "table":
            out.append("<table class='ixbrl'>")
            for tr in el.iter(f"{{{XHTML}}}tr"):
                tds = tr.findall(f"{{{XHTML}}}td") + tr.findall(f"{{{XHTML}}}th")
                if not tds:
                    continue
                out.append("<tr>")
                for td in tds:
                    # right-align cells that carry a numeric (or date) fact
                    is_val = td.find(f"{{{IX}}}nonFraction") is not None or (
                        td.find(f"{{{IX}}}nonNumeric") is not None
                        and "".join(td.itertext()).strip()[:2].isdigit()
                    )
                    cls = " class='val'" if is_val else ""
                    out.append(f"<td{cls}>{_cell(td)}</td>")
                out.append("</tr>")
            out.append("</table>")
    return "".join(out)


def _embedded_sections(ctr):
    """Find and render the embedded accounts + computation iXBRL, if present."""
    sections = []
    labels = {"Accounts": "Accounts (FRS 105 micro-entity, iXBRL)",
              "Computation": "Corporation tax computation (iXBRL)"}
    for kind, title in labels.items():
        enc = ctr.find(
            f".//{{{CT}}}{kind}/{{{CT}}}Instance/{{{CT}}}EncodedInlineXBRLDocument"
        )
        if enc is not None and enc.text:
            sections.append(
                f"<h2 class='doc'>{title}</h2>"
                f"<div class='ixbrl-doc'>{_render_embedded(enc.text)}</div>"
            )
    return "".join(sections)


def build_html(xml_path):
    tree = etree.parse(xml_path)
    root = tree.getroot()

    ctr = root.find(f".//{{{CT}}}CompanyTaxReturn")
    ci   = ctr.find(f"{{{CT}}}CompanyInformation")
    ris  = ctr.find(f"{{{CT}}}ReturnInfoSummary")
    tv   = ctr.find(f"{{{CT}}}Turnover")
    ctc  = ctr.find(f"{{{CT}}}CompanyTaxCalculation")
    calc = ctr.find(f"{{{CT}}}CalculationOfTaxOutstandingOrOverpaid")
    ld   = ctr.find(f"{{{CT}}}LossesDeficitsAndExcess")
    decl = ctr.find(f"{{{CT}}}Declaration")

    trading = ctc.find(f"{{{CT}}}Income/{{{CT}}}Trading") if ctc is not None else None
    ded_el  = ctc.find(f"{{{CT}}}DeductionsAndReliefs") if ctc is not None else None
    chg     = ctc.find(f"{{{CT}}}ChargesAndReliefs") if ctc is not None else None
    fy1     = ctc.find(f".//{{{CT}}}FinancialYearOne") if ctc is not None else None
    fy2     = ctc.find(f".//{{{CT}}}FinancialYearTwo") if ctc is not None else None
    assoc   = ctc.find(f".//{{{CT}}}AssociatedCompanies") if ctc is not None else None
    rel     = ctc.find(f"{{{CT}}}TaxReliefsAndDeductions") if ctc is not None else None

    pc = ci.find(f"{{{CT}}}PeriodCovered") if ci is not None else None

    # Accounts reason
    accts_reason = _text(ris, "Accounts", "NoAccountsReason") if ris is not None else ""
    comps_reason = _text(ris, "Computations", "NoComputationsReason") if ris is not None else ""

    # ── Envelope ─────────────────────────────────────────────────────────────
    msg_class = root.findtext(f".//{{{GT}}}MessageDetails/{{{GT}}}Class") or ""
    gw_test = root.findtext(f".//{{{GT}}}MessageDetails/{{{GT}}}GatewayTest") or ""
    irmark = root.findtext(f".//{{{CT}}}IRmark") or ""
    schema_ver = root.findtext(f".//{{{CT}}}Manifest//{{{CT}}}SchemaVersion") or ""
    env_target = {"1": "test (LTS / GatewayTest=1)", "0": "live (GatewayTest=0)"}.get(gw_test, gw_test)

    rows = []

    # ── Submission envelope ──────────────────────────────────────────────────
    rows.append("<tr class='section'><td colspan='3'>Submission Envelope</td></tr>")
    rows.append(_row("", "Message class",  msg_class))
    rows.append(_row("", "Mode",           env_target))
    rows.append(_row("", "Schema version", schema_ver))
    rows.append(_row("", "IRmark",         f"<span style='font-family:monospace'>{irmark}</span>"))

    # ── Company ──────────────────────────────────────────────────────────────
    rows.append("<tr class='section'><td colspan='3'>Company Information</td></tr>")
    rows.append(_row(1,  "Company name",           _text(ci, "CompanyName")))
    rows.append(_row(2,  "Registration number",    _text(ci, "RegistrationNumber")))
    rows.append(_row(3,  "UTR",                    _text(ci, "Reference")))
    rows.append(_row(4,  "Company type",           _text(ci, "CompanyType")))
    rows.append(_row(30, "Period from",            _text(pc, "From") if pc is not None else ""))
    rows.append(_row(35, "Period to",              _text(pc, "To")   if pc is not None else ""))

    # ── Accounts ─────────────────────────────────────────────────────────────
    this_accts = _text(ris, "Accounts", "ThisPeriodAccounts") if ris is not None else ""
    this_comps = _text(ris, "Computations", "ThisPeriodComputations") if ris is not None else ""
    rows.append("<tr class='section'><td colspan='3'>Return Info</td></tr>")
    if accts_reason or comps_reason:
        rows.append(_row(90, "No accounts reason",     accts_reason))
        rows.append(_row(90, "No computations reason", comps_reason))
    else:
        rows.append(_row(80, "Accounts this period",     "yes — iXBRL embedded (see below)" if this_accts == "yes" else this_accts))
        rows.append(_row(80, "Computations this period", "yes — iXBRL embedded (see below)" if this_comps == "yes" else this_comps))

    # ── Turnover ─────────────────────────────────────────────────────────────
    rows.append("<tr class='section'><td colspan='3'>Turnover</td></tr>")
    rows.append(_row(145, "Total turnover from trade", _money(_text(tv, "Total"))))

    # ── Income ───────────────────────────────────────────────────────────────
    rows.append("<tr class='section'><td colspan='3'>Income</td></tr>")
    rows.append(_row(155, "Trading profits",                  _money(_text(trading, "Profits"))))
    rows.append(_row(160, "Trading losses b/f against profits",_money(_text(trading, "LossesBroughtForward"))))
    rows.append(_row(165, "Net trading profits",              _money(_text(trading, "NetProfits"))))
    rows.append(_row(235, "Profits before other deductions",  _money(_text(ctc, "ProfitsBeforeOtherDeductions"))))

    # ── Deductions ───────────────────────────────────────────────────────────
    if ded_el is not None:
        rows.append("<tr class='section'><td colspan='3'>Deductions and Reliefs</td></tr>")
        rows.append(_row(285, "Trading losses c/f claimed against profits", _money(_text(ded_el, "TradingLossesCarriedForward"))))
        rows.append(_row(295, "Total deductions and reliefs",                _money(_text(ded_el, "Total"))))

    # ── Charges ──────────────────────────────────────────────────────────────
    rows.append("<tr class='section'><td colspan='3'>Charges and Reliefs</td></tr>")
    rows.append(_row(300, "Profits before donations and group relief", _money(_text(chg, "ProfitsBeforeDonationsAndGroupRelief"))))
    rows.append(_row(315, "Chargeable profits",                        _money(_text(ctc, "ChargeableProfits")), highlight=True))

    # ── CT rates ─────────────────────────────────────────────────────────────
    rows.append("<tr class='section'><td colspan='3'>Corporation Tax Calculation</td></tr>")
    spr = _text(assoc, "StartingOrSmallCompaniesRate") if assoc is not None else ""
    rows.append(_row(329, "Small profits rate",       spr))
    fy1_ac = _text(assoc, "AssociatedCompaniesFinancialYears", "FirstYear")  if assoc is not None else ""
    fy2_ac = _text(assoc, "AssociatedCompaniesFinancialYears", "SecondYear") if assoc is not None else ""
    rows.append(_row(327, "Associated companies FY1", fy1_ac))
    rows.append(_row(328, "Associated companies FY2", fy2_ac))

    if fy1 is not None:
        d1 = fy1.find(f"{{{CT}}}Details")
        rows.append(_row(330, f"FY1 year",    _text(fy1, "Year")))
        rows.append(_row(335, "FY1 profit",   _money(_text(d1, "Profit"))))
        rows.append(_row(340, "FY1 tax rate", _text(d1, "TaxRate") + "%"))
        rows.append(_row(345, "FY1 tax",      _money(_text(d1, "Tax"))))
    if fy2 is not None:
        d2 = fy2.find(f"{{{CT}}}Details")
        rows.append(_row(380, "FY2 year",    _text(fy2, "Year")))
        rows.append(_row(385, "FY2 profit",  _money(_text(d2, "Profit"))))
        rows.append(_row(390, "FY2 tax rate",_text(d2, "TaxRate") + "%"))
        rows.append(_row(395, "FY2 tax",     _money(_text(d2, "Tax"))))

    rows.append(_row(430, "Corporation tax",              _money(_text(ctc, "CorporationTax"))))
    rows.append(_row(440, "Net corporation tax chargeable",_money(_text(ctc, "NetCorporationTaxChargeable"))))
    rows.append(_row(470, "Total reliefs and deductions", _money(_text(rel, "TotalReliefsAndDeductions"))))

    # ── Outstanding / Overpaid ───────────────────────────────────────────────
    rows.append("<tr class='section'><td colspan='3'>Tax Outstanding or Overpaid</td></tr>")
    rows.append(_row(475, "Net corporation tax liability", _money(_text(calc, "NetCorporationTaxLiability"))))
    rows.append(_row(510, "Tax chargeable",                _money(_text(calc, "TaxChargeable"))))
    rows.append(_row(528, "Tax payable",                   _money(_text(calc, "TaxPayable")), highlight=True))

    # ── Losses ───────────────────────────────────────────────────────────────
    if ld is not None:
        arising_uk = _text(ld, "AmountArising", "LossesOfTradesUK", "Arising")
        if arising_uk:
            rows.append("<tr class='section'><td colspan='3'>Losses, Deficits and Excess Amounts</td></tr>")
            rows.append(_row(780, "Trading losses arising this period (UK)", _money(arising_uk), highlight=True))

    # ── Declaration ──────────────────────────────────────────────────────────
    rows.append("<tr class='section'><td colspan='3'>Declaration</td></tr>")
    rows.append(_row(975, "Name",   _text(decl, "Name")))
    rows.append(_row(985, "Status", _text(decl, "Status")))
    rows.append(_row(980, "Date",   _text(decl, "Date")))

    company_name = _text(ci, "CompanyName")
    period_to    = _text(pc, "To") if pc is not None else ""
    embedded = _embedded_sections(ctr)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CT600 Preview — {company_name}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 2em; color: #222; }}
  h1 {{ font-size: 1.4em; margin-bottom: 0.2em; }}
  p.subtitle {{ color: #666; margin-top: 0; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 800px; }}
  td {{ padding: 5px 10px; vertical-align: top; }}
  td.box {{ width: 4em; color: #888; font-size: 0.85em; text-align: right; padding-right: 1em; }}
  td.val {{ text-align: right; width: 10em; font-family: monospace; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  tr.section td {{ background: #2c5f8a; color: white; font-weight: bold;
                   padding: 6px 10px; font-size: 0.9em; letter-spacing: 0.05em; }}
  tr.highlight td {{ background: #fffbe6; font-weight: bold; }}
  tr.highlight td.box {{ color: #555; }}
  h2.doc {{ font-size: 1.15em; margin: 1.6em 0 0.4em; padding-bottom: 0.2em;
            border-bottom: 2px solid #2c5f8a; color: #2c5f8a; max-width: 800px; }}
  .ixbrl-doc {{ max-width: 800px; }}
  .ixbrl-doc h3 {{ font-size: 0.95em; margin: 1em 0 0.3em; color: #444; }}
  table.ixbrl {{ border-collapse: collapse; width: 100%; margin-bottom: 0.5em; }}
  table.ixbrl td {{ padding: 4px 10px; border-bottom: 1px solid #eee; }}
  table.ixbrl td.val {{ text-align: right; font-family: monospace; width: 12em; }}
</style>
</head>
<body>
<h1>CT600 — {company_name}</h1>
<p class="subtitle">Period ending {period_to} &nbsp;·&nbsp; Source: {os.path.basename(xml_path)}</p>
<table>
<colgroup><col style="width:4em"><col><col style="width:10em"></colgroup>
<thead><tr><th style="text-align:right;color:#888;font-size:.85em">Box</th>
<th style="text-align:left">Field</th>
<th style="text-align:right">Value</th></tr></thead>
<tbody>
{"".join(rows)}</tbody>
</table>
{embedded}
</body>
</html>"""
    return html


def main():
    xml_path = sys.argv[1] if len(sys.argv) > 1 else "2025-dry-run.xml"
    html = build_html(xml_path)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as f:
        f.write(html)
        tmp = f.name

    print(f"Opening {tmp}")
    webbrowser.open(f"file://{tmp}")


if __name__ == "__main__":
    main()
