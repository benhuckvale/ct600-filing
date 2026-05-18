import requests

LTS_URL = "http://localhost:5665/LTS/LTSPostServlet"
HMRC_URL = "https://transaction-engine.tax.service.gov.uk/submission"


def submit(xml_bytes: bytes, target: str = "lts") -> str:
    """POST the CT600 XML to the target endpoint and return the response body."""
    if target == "lts":
        url = LTS_URL
    elif target in ("til", "live"):
        url = HMRC_URL
    else:
        raise ValueError(f"Unknown target: {target!r}")

    resp = requests.post(
        url,
        data=xml_bytes,
        headers={"Content-Type": "application/x-binary"},
        timeout=30,
    )
    return resp.text
