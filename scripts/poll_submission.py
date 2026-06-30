#!/usr/bin/env python3
"""Re-poll a recorded submission's CorrelationID and append the reply to its
audit-trail directory.

Usage:
    python scripts/poll_submission.py [attempt-dir]   # default: latest

HMRC is asynchronous: a submission is acknowledged first and the real result is
fetched by polling. This reads the attempt's class + CorrelationID from
attempt.json, polls the ResponseEndPoint, writes response-NNN-<qualifier>.xml,
and updates attempt.json (outcome flips to response/error once final).

Note: HMRC clears a CorrelationID from the poll queue once its result has been
retrieved (or after it ages out); polling a cleared one returns an enumeration
error rather than the result.
"""
import sys

import requests
from lxml import etree

from ct600.submit import HMRC_URL, _HEADERS, _details, _poll_message, _utcnow
from submission_lib import (GT, load_meta, resolve_dir, response_files,
                            save_meta, summarize)


def poll(d) -> str:
    meta = load_meta(d)
    if meta["target"] not in ("til", "live"):
        raise SystemExit(f"{d.name}: target {meta['target']!r} is not pollable")
    cid, cls = meta["correlationId"], meta["class"]
    if not cid or not cls:
        raise SystemExit(f"{d.name}: no CorrelationID/class recorded")

    # prefer the ResponseEndPoint from the most recent reply; fall back to /submission
    endpoint = HMRC_URL
    resp = response_files(d)
    if resp:
        rep = etree.parse(str(resp[-1])).getroot().find(f".//{{{GT}}}ResponseEndPoint")
        if rep is not None and rep.text:
            endpoint = rep.text

    r = requests.post(endpoint, data=_poll_message(cls, cid), headers=_HEADERS, timeout=30)
    q = _details(r.text)[0]

    n = len(meta["responses"]) + 1
    fn = f"response-{n:03d}-{q}.xml"
    (d / fn).write_text(r.text)
    meta["responses"].append({"seq": n, "qualifier": q, "file": fn, "at": _utcnow()})
    if q != "acknowledgement":
        meta["outcome"] = q
        meta["ended_at"] = _utcnow()
    save_meta(d, meta)
    return q


def main() -> None:
    d = resolve_dir(sys.argv[1] if len(sys.argv) > 1 else None)
    q = poll(d)
    if q == "acknowledgement":
        print(f"{d.name}: still processing (acknowledgement) — poll again shortly")
    else:
        print()
        summarize(d)


if __name__ == "__main__":
    main()
