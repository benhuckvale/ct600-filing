"""Integration tests — require the LTS running on localhost:5665.

Start it with:
    pdm run lts start

Then run:
    pdm run test-lts

These tests verify that the LTS actually accepts our submissions (Qualifier=response,
not error). They are reality checks: if they fail it means our XML or IRmark is wrong
in a way that HMRC's validator would also reject.
"""
import re
import socket
import pytest
from lxml import etree
from ct600.build import build_xml
from ct600.submit import submit

GOVTALK_NS = "http://www.govtalk.gov.uk/CM/envelope"
G = f"{{{GOVTALK_NS}}}"


def _lts_running() -> bool:
    try:
        with socket.create_connection(("localhost", 5665), timeout=2):
            return True
    except OSError:
        return False


lts_required = pytest.mark.skipif(
    not _lts_running(),
    reason="LTS not running — start it with: pdm run lts start",
)

# Minimal valid return with no_accounts_reason — the path all real submissions use.
SAMPLE_WITH_REASON = {
    "company": {
        "name": "Test Company Ltd",
        "registration_number": "12345678",
        "utr": "8596148860",
        "type": 6,
    },
    "period": {"from": "2024-04-01", "to": "2025-03-31"},
    "no_accounts_reason": "Other - PDF attached with explanation",
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

# Zero-tax return — mirrors the typical micro-entity filing pattern.
# Uses company type 0 (standard UK company) with 25% rate and zero profits.
SAMPLE_ZERO_TAX = {
    **SAMPLE_WITH_REASON,
    "company": {**SAMPLE_WITH_REASON["company"], "type": 0},
    "turnover": {"total": 30000.00},
    "income": {
        "trading": {
            "profits": 0.00,
            "net_profits": 0.00,
        }
    },
    "profits_before_other_deductions": 0.00,
    "profits_before_donations_and_group_relief": 0.00,
    "chargeable_profits": 0.00,
    "corporation_tax": {
        "financial_year_1": {"year": 2024, "profit": 0.00, "tax_rate": 25.00, "tax": 0.00},
        "total": 0.00,
    },
    "net_corporation_tax_chargeable": 0.00,
    "calculation": {
        "net_corporation_tax_liability": 0.00,
        "tax_chargeable": 0.00,
        "tax_payable": 0.00,
    },
}


def _submit_and_parse(data: dict) -> etree._Element:
    xml = build_xml(data, gateway_test=True)
    response = submit(xml, target="lts")
    return etree.fromstring(response.encode())


def _qualifier(root: etree._Element) -> str:
    return root.findtext(f".//{G}Qualifier") or ""


def _errors(root: etree._Element) -> list[str]:
    # Errors appear in both the GovTalk envelope and the body ErrorResponse namespace
    return [e.text or "" for e in root.findall(".//{*}Text")]


@pytest.mark.integration
@lts_required
def test_lts_accepts_return_with_no_accounts_reason():
    """LTS accepts a valid return that uses no_accounts_reason instead of iXBRL."""
    root = _submit_and_parse(SAMPLE_WITH_REASON)
    assert _qualifier(root) == "response", f"LTS rejected submission: {_errors(root)}"


@pytest.mark.integration
@lts_required
def test_lts_accepts_zero_tax_return():
    """LTS accepts a zero-profit, zero-tax return (micro-entity pattern)."""
    root = _submit_and_parse(SAMPLE_ZERO_TAX)
    assert _qualifier(root) == "response", f"LTS rejected submission: {_errors(root)}"


@pytest.mark.integration
@lts_required
def test_lts_rejects_bad_irmark():
    """LTS rejects a submission with a tampered IRmark (error 2021)."""
    xml = build_xml(SAMPLE_WITH_REASON, gateway_test=True)
    # Replace the IRmark value with an obviously wrong one
    corrupted = re.sub(rb"(<IRmark[^>]*>)[^<]+(</IRmark>)", rb"\1AAAAAAAAAAAAAAAAAAAAAAAAAAAA=\2", xml)
    root = etree.fromstring(submit(corrupted, target="lts").encode())
    assert _qualifier(root) == "error"
    errors = _errors(root)
    assert any("IRmark" in e for e in errors), f"Expected IRmark error, got: {errors}"
