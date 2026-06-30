"""Shared helpers for the submission audit-trail scripts (show / poll).

Operates on the per-attempt directories under submissions/ that ct600.submit
writes (request.xml, response-NNN-*.xml, attempt.json). See submissions/README.md.
"""
import json
from pathlib import Path

from lxml import etree

REPO = Path(__file__).resolve().parent.parent
SUBMISSIONS = REPO / "submissions"

GT = "http://www.govtalk.gov.uk/CM/envelope"
ER = "http://www.govtalk.gov.uk/CM/errorresponse"


def latest_dir() -> Path | None:
    dirs = sorted(p for p in SUBMISSIONS.glob("*-*") if p.is_dir())
    return dirs[-1] if dirs else None


def resolve_dir(arg: str | None) -> Path:
    if arg:
        p = Path(arg)
        return p if p.is_absolute() or p.exists() else (SUBMISSIONS / arg)
    d = latest_dir()
    if d is None:
        raise SystemExit("no attempt directories under submissions/")
    return d


def load_meta(d: Path) -> dict:
    return json.loads((d / "attempt.json").read_text())


def save_meta(d: Path, meta: dict) -> None:
    (d / "attempt.json").write_text(json.dumps(meta, indent=2) + "\n")


def response_files(d: Path) -> list[Path]:
    return sorted(d.glob("response-*.xml"))


def errors_of(resp_path: Path) -> tuple[str, list[tuple[str, str, str]]]:
    """Return (qualifier, [(location, type, text), ...]) for a response file."""
    root = etree.parse(str(resp_path)).getroot()
    q = root.findtext(f".//{{{GT}}}Qualifier") or "?"
    out = []
    for e in root.findall(f".//{{{ER}}}Error"):
        out.append((
            (e.findtext(f"{{{ER}}}Location") or "").strip(),
            (e.findtext(f"{{{ER}}}Type") or "").strip(),
            (e.findtext(f"{{{ER}}}Text") or "").strip(),
        ))
    return q, out


def summarize(d: Path) -> None:
    meta = load_meta(d)
    print(f"# {d.name}")
    print(f"target={meta['target']}  outcome={meta['outcome']}  "
          f"class={meta['class']}  cid={meta['correlationId']}")
    print(f"started={meta['started_at']}  ended={meta['ended_at']}  "
          f"polls={len(meta['responses'])}")
    resp = response_files(d)
    if not resp:
        print("(no responses recorded yet)")
        return
    last = resp[-1]
    q, errs = errors_of(last)
    print(f"\nfinal reply: {last.name}  (qualifier={q})")
    if not errs:
        print("no business errors" + (" — ACCEPTED" if q == "response" else ""))
        return
    print(f"{len(errs)} error(s):")
    for i, (loc, typ, txt) in enumerate(errs, 1):
        tail = typ.split(".")[-1] if typ else ""
        print(f"[{i:>2}] ({loc}) {tail}\n     {txt}")
