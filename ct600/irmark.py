import hashlib
import base64
from lxml import etree

CT_NS = "http://www.govtalk.gov.uk/taxation/CT/5"


def compute_irmark(body_elem: etree._Element) -> str:
    """Compute IRmark as base64(SHA-1(C14N(body))) with IRmark element emptied."""
    irmark_el = body_elem.find(f".//{{{CT_NS}}}IRmark")
    saved_text = None
    if irmark_el is not None:
        saved_text = irmark_el.text
        irmark_el.text = ""

    c14n_bytes = etree.tostring(body_elem, method="c14n")
    digest = hashlib.sha1(c14n_bytes).digest()
    result = base64.b64encode(digest).decode("ascii")

    if irmark_el is not None:
        irmark_el.text = saved_text

    return result
