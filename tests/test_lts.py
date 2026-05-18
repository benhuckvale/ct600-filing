"""Integration tests — require the LTS running on localhost:5665.

Start it with:
    pdm run lts start

Then run:
    pdm run test-lts
"""
import socket
import pytest
from ct600.build import build_xml
from ct600.submit import submit


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


@pytest.mark.integration
@lts_required
def test_lts_returns_response():
    xml = build_xml(SAMPLE, gateway_test=True)
    response = submit(xml, target="lts")
    assert response, "LTS returned an empty response"


@pytest.mark.integration
@lts_required
def test_lts_response_is_xml():
    xml = build_xml(SAMPLE, gateway_test=True)
    response = submit(xml, target="lts")
    assert "GovTalkMessage" in response, f"Unexpected response:\n{response}"
