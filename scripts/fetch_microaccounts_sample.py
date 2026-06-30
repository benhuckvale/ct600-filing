#!/usr/bin/env python3
"""Materialise a known-good FRS 105 micro-entity iXBRL sample from microaccounts.uk.

microaccounts.uk generates the iXBRL *server-side* (POST /api/accounts/generate),
so its downloadable page/JS don't contain the tagging — the useful reference is a
generated sample. This sends DUMMY data (never real figures) and saves the result
to reference/microaccounts-sample.html.

Courtesy notes: microaccounts.uk is a free third-party service with no open
licence, so the sample is gitignored (not committed/redistributed) and this hits
their API once per run — only run it when you actually need a fresh reference
sample. Run: `pdm run fetch-microaccounts-sample`.
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://microaccounts.uk/api/accounts/generate"
DEST = Path(__file__).resolve().parent.parent / "reference" / "microaccounts-sample.html"

# A dummy micro-entity — NOT real data; only to elicit the tagging structure.
DATA = {
    "company_info": {"company_name": "Example Micro Ltd", "company_number": "12345678",
                     "period_end_date": "2025-09-30", "prior_period_end_date": "2024-09-30",
                     "approval_date": "2026-06-30", "average_employees": "2",
                     "directors": ["A Director"]},
    "balance_sheet": {
        "fixed_assets": {"intangible_assets": {"current_year": 0, "prior_year": 0},
                         "tangible_assets": {"current_year": 100, "prior_year": 100}},
        "current_assets": {"stocks": {"current_year": 0, "prior_year": 0},
                           "debtors": {"current_year": 0, "prior_year": 0},
                           "cash": {"current_year": 0, "prior_year": 0}},
        "creditors_within_one_year": {"trade_creditors": {"current_year": 0, "prior_year": 0},
                                      "other_creditors": {"current_year": 0, "prior_year": 0}},
        "creditors_after_one_year": {"long_term_creditors": {"current_year": 0, "prior_year": 0}},
        "provisions": {"provisions": {"current_year": 0, "prior_year": 0}},
        "capital_and_reserves": {"share_capital": {"current_year": 100, "prior_year": 100},
                                 "pl_account_opening": {"current_year": 0, "prior_year": 0},
                                 "pl_account_closing": {"current_year": 0, "prior_year": 0},
                                 "dividends_paid": {"current_year": 0, "prior_year": 0}}},
    "profit_and_loss": {"include_in_filing": True,
                        "turnover": {"current_year": 1000, "prior_year": 900},
                        "raw_materials_consumables": {"current_year": 200, "prior_year": 150},
                        "staff_costs": {"current_year": 700, "prior_year": 650},
                        "other_external_charges": {"current_year": 100, "prior_year": 100},
                        "other_income": {"current_year": 0, "prior_year": 0},
                        "interest_receivable": {"current_year": 0, "prior_year": 0},
                        "interest_payable": {"current_year": 0, "prior_year": 0},
                        "depreciation_amortisation": {"current_year": 0, "prior_year": 0},
                        "tax": {"current_year": 0, "prior_year": 0}}}


def main() -> None:
    req = urllib.request.Request(
        API, data=json.dumps(DATA).encode(),
        headers={"Content-Type": "application/json",
                 # the API rejects requests without a same-origin Origin/Referer
                 "Origin": "https://microaccounts.uk",
                 "Referer": "https://microaccounts.uk/",
                 "User-Agent": "Mozilla/5.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=40)
    except urllib.error.HTTPError as e:
        sys.exit(f"microaccounts API error {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    DEST.write_bytes(resp.read())
    print(f"wrote reference/{DEST.name} ({DEST.stat().st_size} bytes) — dummy-data FRS 105 sample")
    print("A tagging reference to diff against ct600/accounts.py output. Not committed.")


if __name__ == "__main__":
    main()
