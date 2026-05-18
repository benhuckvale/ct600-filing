from lxml import etree
from ct600.irmark import compute_irmark

CT_NS = "http://www.govtalk.gov.uk/taxation/CT/5"
C = f"{{{CT_NS}}}"


def _make_body(irmark_text=""):
    body = etree.Element("Body")
    env = etree.SubElement(body, f"{C}IRenvelope")
    hdr = etree.SubElement(env, f"{C}IRheader")
    irmark = etree.SubElement(hdr, f"{C}IRmark", Type="generic")
    irmark.text = irmark_text
    etree.SubElement(env, f"{C}Payload").text = "test"
    return body


def test_irmark_is_base64():
    import base64
    body = _make_body()
    result = compute_irmark(body)
    decoded = base64.b64decode(result)
    assert len(decoded) == 20  # SHA-1 digest is 20 bytes


def test_irmark_is_deterministic():
    body1 = _make_body()
    body2 = _make_body()
    assert compute_irmark(body1) == compute_irmark(body2)


def test_irmark_differs_with_different_content():
    body1 = _make_body()
    body2 = _make_body()
    body2.find(f".//{C}Payload").text = "different"
    assert compute_irmark(body1) != compute_irmark(body2)


def test_irmark_computation_does_not_mutate_element():
    body = _make_body(irmark_text="existing")
    compute_irmark(body)
    irmark_el = body.find(f".//{C}IRmark")
    assert irmark_el.text == "existing"
