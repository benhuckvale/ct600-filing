from lxml import etree
from ct600.build import build_xml

GOVTALK_NS = "http://www.govtalk.gov.uk/CM/envelope"
CT_NS = "http://www.govtalk.gov.uk/taxation/CT/5"
G = f"{{{GOVTALK_NS}}}"
C = f"{{{CT_NS}}}"

SAMPLE = {
    "company": {
        "name": "Test Company Ltd",
        "registration_number": "12345678",
        "utr": "8596148860",
        "type": 6,
    },
    "period": {"from": "2024-04-01", "to": "2025-03-31"},
    "turnover": {"total": 100000.00},
    "income": {
        "trading": {
            "profits": 100000.00,
            "losses_brought_forward": 0.00,
            "net_profits": 100000.00,
        }
    },
    "profits_before_other_deductions": 100000.00,
    "profits_before_donations_and_group_relief": 100000.00,
    "chargeable_profits": 100000.00,
    "corporation_tax": {
        "financial_year_1": {"year": 2024, "profit": 100000.00, "tax_rate": 25.00, "tax": 25000.00},
        "total": 25000.00,
    },
    "net_corporation_tax_chargeable": 25000.00,
    "tax_reliefs_and_deductions": {"total": 0.00},
    "calculation": {
        "net_corporation_tax_liability": 25000.00,
        "tax_chargeable": 25000.00,
        "tax_payable": 25000.00,
    },
    "declaration": {"name": "Joe Bloggs", "status": "Director"},
    "credentials": {
        "sender_id": "dummy",
        "password": "dummy",
        "vendor_id": "0000",
        "product": "test",
        "version": "1.0",
    },
}


def _parse(data=None, **kwargs):
    return etree.fromstring(build_xml(data or SAMPLE, **kwargs))


def test_root_element():
    assert _parse().tag == f"{G}GovTalkMessage"


def test_message_class():
    root = _parse()
    assert root.findtext(f".//{G}Class") == "HMRC-CT-CT600"


def test_utr_in_govtalk_keys():
    root = _parse()
    key = root.find(f".//{G}Key[@Type='UTR']")
    assert key is not None and key.text == "8596148860"


def test_gateway_test_on_by_default():
    root = _parse()
    assert root.findtext(f".//{G}GatewayTest") == "1"


def test_gateway_test_off_for_live():
    root = _parse(gateway_test=False)
    assert root.findtext(f".//{G}GatewayTest") == "0"


def test_irmark_is_populated():
    root = _parse()
    irmark = root.find(f".//{C}IRmark")
    assert irmark is not None
    assert irmark.text and len(irmark.text) > 0


def test_irmark_is_stable():
    """Same data always produces the same IRmark."""
    xml1 = build_xml(SAMPLE)
    xml2 = build_xml(SAMPLE)
    root1 = etree.fromstring(xml1)
    root2 = etree.fromstring(xml2)
    irmark1 = root1.findtext(f".//{C}IRmark")
    irmark2 = root2.findtext(f".//{C}IRmark")
    assert irmark1 == irmark2


def test_company_info():
    root = _parse()
    assert root.findtext(f".//{C}CompanyName") == "Test Company Ltd"
    assert root.findtext(f".//{C}RegistrationNumber") == "12345678"
    assert root.findtext(f".//{C}CompanyType") == "6"


def test_period():
    root = _parse()
    assert root.findtext(f".//{C}PeriodEnd") == "2025-03-31"
    assert root.findtext(f".//{C}From") == "2024-04-01"
    assert root.findtext(f".//{C}To") == "2025-03-31"


def test_turnover():
    root = _parse()
    assert root.findtext(f".//{C}Total") == "100000.00"


def test_trading_profits():
    root = _parse()
    trading = root.find(f".//{C}Trading")
    assert trading.findtext(f"{C}Profits") == "100000.00"
    assert trading.findtext(f"{C}NetProfits") == "100000.00"


def test_corporation_tax_rate():
    root = _parse()
    assert root.findtext(f".//{C}TaxRate") == "25.00"


def test_declaration():
    root = _parse()
    decl = root.find(f".//{C}Declaration")
    assert decl.findtext(f"{C}AcceptDeclaration") == "yes"
    assert decl.findtext(f"{C}Name") == "Joe Bloggs"
    assert decl.findtext(f"{C}Status") == "Director"


def test_no_accounts_reason_when_set():
    data = {**SAMPLE, "no_accounts_reason": "Filed separately with Companies House."}
    root = _parse(data)
    assert root.findtext(f".//{C}NoAccountsReason") == "Filed separately with Companies House."
    assert root.findtext(f".//{C}NoComputationsReason") == "Filed separately with Companies House."


def test_accounts_attached_when_no_reason():
    data = {k: v for k, v in SAMPLE.items() if k != "no_accounts_reason"}
    root = _parse(data)
    assert root.findtext(f".//{C}AccountsAttached") == "yes"
    assert root.findtext(f".//{C}ComputationsAttached") == "yes"


def test_two_financial_years():
    data = {**SAMPLE, "corporation_tax": {
        "financial_year_1": {"year": 2024, "profit": 50000.00, "tax_rate": 25.00, "tax": 12500.00},
        "financial_year_2": {"year": 2025, "profit": 50000.00, "tax_rate": 25.00, "tax": 12500.00},
        "total": 25000.00,
    }}
    root = _parse(data)
    assert root.find(f".//{C}FinancialYearTwo") is not None
