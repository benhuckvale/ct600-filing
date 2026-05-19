import hashlib
import base64
from lxml import etree

CT_NS = "http://www.govtalk.gov.uk/taxation/CT/5"


def compute_irmark(body_elem: etree._Element) -> str:
    """Compute IRmark as base64(SHA-1(C14N(body))) with IRmark element removed.

    Per the HMRC Generic IRmark Specification v1.2: the IRmark element is excluded
    entirely from the C14N input (not merely emptied).
    """
    irmark_el = body_elem.find(f".//{{{CT_NS}}}IRmark")
    if irmark_el is not None:
        parent = irmark_el.getparent()
        index = list(parent).index(irmark_el)
        parent.remove(irmark_el)

    c14n_bytes = etree.tostring(body_elem, method="c14n")
    digest = hashlib.sha1(c14n_bytes).digest()
    result = base64.b64encode(digest).decode("ascii")

    if irmark_el is not None:
        parent.insert(index, irmark_el)

    return result
