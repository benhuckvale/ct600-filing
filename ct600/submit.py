import datetime
import json
import pathlib
import sys
import time

import requests
from lxml import etree

LTS_URL = "http://localhost:5665/LTS/LTSPostServlet"
HMRC_URL = "https://transaction-engine.tax.service.gov.uk/submission"

GT = "http://www.govtalk.gov.uk/CM/envelope"
_HEADERS = {"Content-Type": "application/x-binary"}

REPO = pathlib.Path(__file__).resolve().parent.parent
SUBMISSIONS = REPO / "submissions"


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


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


class _Recorder:
    """Persist a submission's request/responses to submissions/<stamp>-<target>/.

    Every gateway reply is written verbatim (response-NNN-<qualifier>.xml) and a
    rolling attempt.json captures the structured state, so an interrupted run
    still leaves a usable audit trail and a CorrelationID to re-poll.
    """

    def __init__(self, target: str) -> None:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        d = SUBMISSIONS / f"{ts}-{target}"
        i = 2
        while d.exists():
            d = SUBMISSIONS / f"{ts}-{target}-{i}"
            i += 1
        d.mkdir(parents=True)
        self.dir = d
        self.n = 0
        self.meta = {
            "target": target,
            "class": None,
            "correlationId": None,
            "started_at": _utcnow(),
            "ended_at": None,
            "outcome": "pending",
            "responses": [],
        }
        self._flush()
        print(f"[submit] recording to {self.dir.relative_to(REPO)}/", file=sys.stderr)

    def _flush(self) -> None:
        (self.dir / "attempt.json").write_text(json.dumps(self.meta, indent=2) + "\n")

    def write(self, name: str, data) -> None:
        (self.dir / name).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    def response(self, text: str) -> str:
        """Record one gateway reply; return its qualifier."""
        self.n += 1
        try:
            q, cls, cid, *_ = _details(text)
        except Exception:
            q, cls, cid = "unparsed", None, None
        name = f"response-{self.n:03d}-{q}.xml"
        self.write(name, text)
        self.meta["responses"].append(
            {"seq": self.n, "qualifier": q, "file": name, "at": _utcnow()}
        )
        if cid and not self.meta["correlationId"]:
            self.meta["correlationId"] = cid
        if cls and cls != "UndefinedClass" and not self.meta["class"]:
            self.meta["class"] = cls
        self._flush()
        return q

    def finalize(self, outcome: str) -> None:
        self.meta["outcome"] = outcome
        self.meta["ended_at"] = _utcnow()
        self._flush()


def submit(xml_bytes: bytes, target: str = "lts", poll: bool = True,
           max_wait: int = 240, record: bool | None = None) -> str:
    """POST the CT600 XML to the target endpoint and return the response body.

    HMRC (til/live) is asynchronous: the first POST returns an *acknowledgement*
    with a CorrelationID, and the real validation result is fetched by polling
    the response endpoint until it stops acknowledging. LTS responds inline.

    For til/live, every request/response is persisted under submissions/ (see
    that directory's README). Pass ``record=False`` to disable, or ``record=True``
    to also record an lts run.
    """
    if target == "lts":
        url = LTS_URL
    elif target in ("til", "live"):
        url = HMRC_URL
    else:
        raise ValueError(f"Unknown target: {target!r}")

    if record is None:
        record = target in ("til", "live")
    rec = _Recorder(target) if record else None
    if rec:
        rec.write("request.xml", xml_bytes)

    resp = requests.post(url, data=xml_bytes, headers=_HEADERS, timeout=30)
    text = resp.text
    if rec:
        rec.response(text)

    if target == "lts" or not poll:
        if rec:
            rec.finalize("submitted")
        return text

    qualifier, cls, cid, endpoint, interval = _details(text)
    if qualifier != "acknowledgement" or not endpoint:
        if rec:
            rec.finalize(qualifier)
        return text  # already a final response/error

    poll_msg = _poll_message(cls, cid)
    waited = 0
    while waited < max_wait:
        time.sleep(interval)
        waited += interval
        pr = requests.post(endpoint, data=poll_msg, headers=_HEADERS, timeout=30)
        q = rec.response(pr.text) if rec else _details(pr.text)[0]
        if q != "acknowledgement":
            if rec:
                rec.finalize(q)
            return pr.text  # response or error — the real result

    if rec:
        rec.finalize("timeout")
    return (
        f"Timed out after {max_wait}s still awaiting the HMRC result "
        f"(CorrelationID {cid}). The submission was accepted for processing; "
        f"poll again later or wait for the confirmation email.\n\n{text}"
    )
