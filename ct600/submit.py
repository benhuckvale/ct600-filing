import time

import requests
from lxml import etree

LTS_URL = "http://localhost:5665/LTS/LTSPostServlet"
HMRC_URL = "https://transaction-engine.tax.service.gov.uk/submission"

GT = "http://www.govtalk.gov.uk/CM/envelope"
_HEADERS = {"Content-Type": "application/x-binary"}


def _details(resp_text: str):
    """Pull (qualifier, class, correlation_id, response_endpoint, poll_interval)
    out of a GovTalk response."""
    root = etree.fromstring(resp_text.encode("utf-8"))
    md = root.find(f".//{{{GT}}}MessageDetails")
    qualifier = md.findtext(f"{{{GT}}}Qualifier")
    cls = md.findtext(f"{{{GT}}}Class")
    cid = md.findtext(f"{{{GT}}}CorrelationID")
    rep = md.find(f"{{{GT}}}ResponseEndPoint")
    endpoint = rep.text if rep is not None else None
    interval = int(rep.get("PollInterval", "10")) if rep is not None else 10
    return qualifier, cls, cid, endpoint, interval


def _poll_message(cls: str, correlation_id: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<GovTalkMessage xmlns="{GT}">'
        "<EnvelopeVersion>2.0</EnvelopeVersion>"
        "<Header><MessageDetails>"
        f"<Class>{cls}</Class><Qualifier>poll</Qualifier><Function>submit</Function>"
        f"<TransactionID></TransactionID><CorrelationID>{correlation_id}</CorrelationID>"
        "<Transformation>XML</Transformation><GatewayTest>0</GatewayTest>"
        "</MessageDetails></Header>"
        "<GovTalkDetails><Keys/></GovTalkDetails><Body/>"
        "</GovTalkMessage>"
    ).encode("utf-8")


def submit(xml_bytes: bytes, target: str = "lts", poll: bool = True,
           max_wait: int = 240) -> str:
    """POST the CT600 XML to the target endpoint and return the response body.

    HMRC (til/live) is asynchronous: the first POST returns an *acknowledgement*
    with a CorrelationID, and the real validation result is fetched by polling
    the response endpoint until it stops acknowledging. LTS responds inline.
    """
    if target == "lts":
        url = LTS_URL
    elif target in ("til", "live"):
        url = HMRC_URL
    else:
        raise ValueError(f"Unknown target: {target!r}")

    resp = requests.post(url, data=xml_bytes, headers=_HEADERS, timeout=30)
    text = resp.text

    if target == "lts" or not poll:
        return text

    qualifier, cls, cid, endpoint, interval = _details(text)
    if qualifier != "acknowledgement" or not endpoint:
        return text  # already a final response/error

    poll_msg = _poll_message(cls, cid)
    waited = 0
    while waited < max_wait:
        time.sleep(interval)
        waited += interval
        pr = requests.post(endpoint, data=poll_msg, headers=_HEADERS, timeout=30)
        q, *_ = _details(pr.text)
        if q != "acknowledgement":
            return pr.text  # response or error — the real result

    return (
        f"Timed out after {max_wait}s still awaiting the HMRC result "
        f"(CorrelationID {cid}). The submission was accepted for processing; "
        f"poll again later or wait for the confirmation email.\n\n{text}"
    )
