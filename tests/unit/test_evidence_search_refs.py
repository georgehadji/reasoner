"""source="search" keeps VERIFIED only when a ref is a URL the run retrieved."""

from reasoner.application.services.evidence_service import apply_promotion_rules
from reasoner.domain.core_types import EvidenceBundle


def _b(refs):
    return {"c": EvidenceBundle(label="VERIFIED", source="search", evidence_refs=refs)}


def test_search_with_retrieved_url_stays_verified():
    out = apply_promotion_rules(_b(["https://x.org/a/"]), {"https://x.org/a"})
    assert out["c"].label == "VERIFIED"


def test_search_with_invented_url_downgraded():
    out = apply_promotion_rules(_b(["https://fake.example/z"]), {"https://x.org/a"})
    assert out["c"].label == "HYPOTHESIS"


def test_search_with_no_refs_downgraded():
    assert apply_promotion_rules(_b([]), {"https://x.org/a"})["c"].label == "HYPOTHESIS"


def test_allowed_refs_none_skips_check():
    assert apply_promotion_rules(_b([]))["c"].label == "VERIFIED"


def test_sensor_unaffected_by_refs():
    b = {"c": EvidenceBundle(label="VERIFIED", source="sensor")}
    assert apply_promotion_rules(b, set())["c"].label == "VERIFIED"
