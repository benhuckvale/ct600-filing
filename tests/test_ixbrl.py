import base64
import copy

from lxml import etree

from ct600.build import build_xml
from ct600.accounts import build_accounts
from ct600.computation import build_computation
from tests.test_build import SAMPLE

CT_NS = "http://www.govtalk.gov.uk/taxation/CT/5"
C = f"{{{CT_NS}}}"
IX_NS = "http://www.xbrl.org/2013/inlineXBRL"

# SAMPLE plus the accounts + computation sections that trigger iXBRL embedding.
FULL = copy.deepcopy(SAMPLE)
FULL["accounts"] = {
    "prior_period": {"from": "2023-04-01", "to": "2024-03-31"},
    "director": "Joe Bloggs",
    "approval_date": "2025-09-01",
    "average_employees": {"current": 2, "prior": 1},
    "balance_sheet": {
        "current": {"current_assets": 5000, "net_assets": 5000, "equity": 5000},
        "prior": {"current_assets": 3000, "net_assets": 3000, "equity": 3000},
    },
}
FULL["computation"] = {
    "profit_loss_per_accounts": 100000.00,
    "total_profits_chargeable": 100000.00,
    "trading_losses_brought_forward": 0.00,
    "detailed_pl": [
        {"label": "Turnover", "tag": "uk-core:TurnoverRevenue", "amount": 100000.00},
        {"label": "Staff costs", "tag": "uk-core:WagesSalaries", "amount": 40000.00},
        {"label": "Profit", "tag": "uk-core:ProfitLoss", "amount": 100000.00},
    ],
    "note": "Example note.",
}


def _facts(ixbrl_bytes):
    root = etree.fromstring(ixbrl_bytes)
    names = set()
    for el in root.iter(f"{{{IX_NS}}}nonFraction", f"{{{IX_NS}}}nonNumeric"):
        names.add(el.get("name"))
    return root, names


def test_accounts_is_wellformed_micro_balance_sheet():
    root, names = _facts(build_accounts(FULL))
    assert root.tag == "{http://www.w3.org/1999/xhtml}html"
    assert "uk-core:NetAssetsLiabilities" in names
    assert "uk-core:Equity" in names
    assert "uk-core:AverageNumberEmployeesDuringPeriod" in names


def test_accounts_has_prior_year_comparative():
    # Equity tagged for both current and prior instants (two contexts).
    root = etree.fromstring(build_accounts(FULL))
    equity = root.findall(f".//{{{IX_NS}}}nonFraction[@name='uk-core:Equity']")
    assert len(equity) == 2


def test_computation_has_dpl_and_bridge():
    _, names = _facts(build_computation(FULL))
    assert "uk-core:TurnoverRevenue" in names      # detailed P&L
    assert "uk-core:WagesSalaries" in names         # staff costs reach HMRC here
    assert "ct-comp:ProfitLossPerAccounts" in names  # the bridge
    assert "ct-comp:TotalProfitsChargeableToCorporationTax" in names


def test_negative_uses_sign_attribute():
    data = copy.deepcopy(FULL)
    data["computation"]["profit_loss_per_accounts"] = -1275.00
    root = etree.fromstring(build_computation(data))
    fact = root.find(f".//{{{IX_NS}}}nonFraction[@name='ct-comp:ProfitLossPerAccounts']")
    assert fact.get("sign") == "-"
    assert fact.text == "1,275.00"  # magnitude only


def test_build_xml_embeds_two_ixbrl_documents():
    root = etree.fromstring(build_xml(FULL))
    encoded = root.findall(f".//{C}EncodedInlineXBRLDocument")
    assert len(encoded) == 2
    # each base64 blob decodes to a well-formed iXBRL document
    for el in encoded:
        decoded = base64.b64decode(el.text)
        assert etree.fromstring(decoded).tag == "{http://www.w3.org/1999/xhtml}html"


def test_embedding_sets_this_period_flags():
    root = etree.fromstring(build_xml(FULL))
    assert root.findtext(f".//{C}Accounts/{C}ThisPeriodAccounts") == "yes"
    assert root.findtext(f".//{C}Computations/{C}ThisPeriodComputations") == "yes"
    assert root.find(f".//{C}NoAccountsReason") is None


def test_declaration_has_no_date_element():
    # The CT600 schema's Declaration has no Date child (LTS-confirmed).
    root = etree.fromstring(build_xml(SAMPLE))
    decl = root.find(f".//{C}Declaration")
    assert decl.find(f"{C}Date") is None
