"""Shared helpers for building inline XBRL (iXBRL) documents.

An iXBRL document is XHTML with embedded ``ix:`` tags. Numeric facts are
``ix:nonFraction``; text facts are ``ix:nonNumeric``. Every fact points at a
``contextRef`` (entity + period, optionally dimensions) declared once in
``ix:resources``. This module hides that bookkeeping behind a small builder so
the accounts and computation generators can just emit facts.

Modelled on the worked examples in ``reference/ct600`` (accts.html / ct.html).
"""
import os
import subprocess

from lxml import etree

# --- namespaces ---
XHTML = "http://www.w3.org/1999/xhtml"
IX = "http://www.xbrl.org/2013/inlineXBRL"
LINK = "http://www.xbrl.org/2003/linkbase"
XLINK = "http://www.w3.org/1999/xlink"
XBRLI = "http://www.xbrl.org/2003/instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"
IXT2 = "http://www.xbrl.org/inlineXBRL/transformation/2011-07-31"
ISO4217 = "http://www.iso.org/iso/iso4217"
CH_SCHEME = "http://www.companieshouse.gov.uk/"

BASE_NSMAP = {
    "ix": IX,
    "link": LINK,
    "xlink": XLINK,
    "xbrli": XBRLI,
    "xbrldi": XBRLDI,
    "ixt2": IXT2,
    "iso4217": ISO4217,
}

H = f"{{{XHTML}}}"
IXq = f"{{{IX}}}"
XBRLIq = f"{{{XBRLI}}}"
XBRLDIq = f"{{{XBRLDI}}}"
LINKq = f"{{{LINK}}}"
XLINKq = f"{{{XLINK}}}"


def _git_version() -> str | None:
    """``git describe`` of this repo at build time, e.g. ``8ce345c`` or
    ``v1.2-3-gabcdef-dirty``. Returns None outside a git checkout."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        out = subprocess.run(
            ["git", "-C", repo, "describe", "--tags", "--always", "--dirty"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def software_label(data: dict) -> tuple[str, str | None]:
    """Software (name, version) for the production-software facts.

    Configurable via a top-level ``software:`` block; defaults to this tool. The
    repo URL is appended to the name for provenance (there is no dedicated
    software-URL tag in the taxonomy). Version resolution: explicit ``version:``
    in the YAML wins; otherwise it's derived from ``git describe`` at build time;
    otherwise the version fact is omitted (rather than invented).
    """
    sw = data.get("software", {})
    name = sw.get("name", "ct600-filing")
    url = sw.get("url")
    version = sw.get("version") or _git_version()
    return (f"{name} ({url})" if url else name), version


def _fmt_amount(value: float, decimals: int) -> tuple[str, bool]:
    """Return (display text with thousands separators, is_negative).

    iXBRL represents negatives as a positive display value plus ``sign="-"``.
    """
    neg = float(value) < 0
    a = abs(round(float(value), decimals))
    return f"{a:,.{decimals}f}", neg


class IxbrlDocument:
    def __init__(
        self,
        *,
        entity_number: str,
        schema_refs: list[str],
        taxonomy_nsmap: dict[str, str],
        title: str,
        software: str = "ct600-filing",
        software_version: str | None = None,
    ) -> None:
        self.entity_number = entity_number
        self.software = software
        self.software_version = software_version

        nsmap = {None: XHTML, **BASE_NSMAP, **taxonomy_nsmap}
        self.root = etree.Element(f"{H}html", nsmap=nsmap)
        head = etree.SubElement(self.root, f"{H}head")
        # XHTML (which HMRC validates against) requires the http-equiv/content
        # form — the HTML5 `<meta charset>` is rejected (cvc-complex-type.3.2.2/4).
        etree.SubElement(head, f"{H}meta", attrib={
            "http-equiv": "Content-Type",
            "content": "text/html; charset=UTF-8",
        })
        etree.SubElement(head, f"{H}title").text = title
        self.body = etree.SubElement(self.root, f"{H}body")

        # ix:header carries the references (schema) and resources (contexts/units).
        header = etree.SubElement(self.body, f"{IXq}header")
        refs = etree.SubElement(header, f"{IXq}references")
        for href in schema_refs:
            sr = etree.SubElement(refs, f"{LINKq}schemaRef")
            sr.set(f"{XLINKq}type", "simple")
            sr.set(f"{XLINKq}href", href)
        self.resources = etree.SubElement(header, f"{IXq}resources")

        self._add_unit("GBP", "iso4217:GBP")
        self._add_unit("pure", "xbrli:pure")
        self._contexts: dict[tuple, str] = {}
        self._ctx_count = 0

    def _add_unit(self, uid: str, measure: str) -> None:
        u = etree.SubElement(self.resources, f"{XBRLIq}unit", id=uid)
        etree.SubElement(u, f"{XBRLIq}measure").text = measure

    def context(
        self,
        *,
        instant: str | None = None,
        start: str | None = None,
        end: str | None = None,
        dims: dict[str, str] | None = None,
    ) -> str:
        """Declare (or reuse) a context and return its id."""
        dims = dims or {}
        sig = (instant, start, end, tuple(sorted(dims.items())))
        if sig in self._contexts:
            return self._contexts[sig]
        cid = f"ctxt-{self._ctx_count}"
        self._ctx_count += 1

        c = etree.SubElement(self.resources, f"{XBRLIq}context", id=cid)
        ent = etree.SubElement(c, f"{XBRLIq}entity")
        etree.SubElement(
            ent, f"{XBRLIq}identifier", scheme=CH_SCHEME
        ).text = self.entity_number
        if dims:
            seg = etree.SubElement(ent, f"{XBRLIq}segment")
            for dim, member in sorted(dims.items()):
                em = etree.SubElement(seg, f"{XBRLDIq}explicitMember", dimension=dim)
                em.text = member
        per = etree.SubElement(c, f"{XBRLIq}period")
        if instant:
            etree.SubElement(per, f"{XBRLIq}instant").text = instant
        else:
            etree.SubElement(per, f"{XBRLIq}startDate").text = start
            etree.SubElement(per, f"{XBRLIq}endDate").text = end
        self._contexts[sig] = cid
        return cid

    def num(
        self,
        parent: etree._Element,
        name: str,
        value: float,
        ctx: str,
        *,
        unit: str = "GBP",
        decimals: int = 2,
    ) -> etree._Element:
        """Emit a numeric (``ix:nonFraction``) fact into ``parent``."""
        el = etree.SubElement(parent, f"{IXq}nonFraction")
        el.set("name", name)
        el.set("contextRef", ctx)
        el.set("unitRef", unit)
        if unit == "pure":
            # counts (e.g. employees) are plain integers, no transform/scale
            el.set("decimals", str(decimals))
            el.text = f"{int(round(float(value)))}"
            return el
        el.set("format", "ixt2:numdotdecimal")
        el.set("decimals", str(decimals))
        el.set("scale", "0")
        text, neg = _fmt_amount(value, decimals)
        if neg:
            el.set("sign", "-")
        el.text = text
        return el

    def text(
        self, parent: etree._Element, name: str, value: str, ctx: str
    ) -> etree._Element:
        """Emit a text (``ix:nonNumeric``) fact into ``parent``."""
        el = etree.SubElement(parent, f"{IXq}nonNumeric")
        el.set("name", name)
        el.set("contextRef", ctx)
        el.text = str(value)
        return el

    def tostring(self) -> bytes:
        return etree.tostring(self.root, xml_declaration=True, encoding="UTF-8")
