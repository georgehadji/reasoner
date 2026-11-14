"""High-stakes epistemic policy, authority registry, and the health memory guard."""

from datetime import date

from reasoner.application.services.evidence_service import (
    HighStakesPolicy,
    apply_promotion_rules,
)
from reasoner.application.services.stakes_service import keep_out_of_memory
from reasoner.domain.authority_sources import (
    AuthorityEntry,
    AuthorityTier,
    authority_tier,
    rank_by_authority,
)
from reasoner.domain.core_types import EvidenceBundle
from reasoner.domain.stakes import Jurisdiction, StakesDomain, StakesProfile

H, L = StakesDomain.HEALTH, StakesDomain.LEGAL
REVIEWED = date(2026, 11, 14)
REG = (
    AuthorityEntry("who.int", H, ("*",), AuthorityTier.PRIMARY, REVIEWED),
    AuthorityEntry("eof.gr", H, ("GR",), AuthorityTier.PRIMARY, REVIEWED),
    AuthorityEntry("nih.gov", H, ("*",), AuthorityTier.SECONDARY, REVIEWED),
    AuthorityEntry("candidate.example", H, ("*",), AuthorityTier.PRIMARY),  # unreviewed
)


def test_subdomain_matches_and_unreviewed_never_counts():
    assert authority_tier("https://www.who.int/x", H, None, REG) is AuthorityTier.PRIMARY
    assert authority_tier("https://candidate.example/x", H, None, REG) is AuthorityTier.NONE
    assert authority_tier("https://notwho.int/x", H, None, REG) is AuthorityTier.NONE


def test_country_scoping():
    assert authority_tier("https://eof.gr/a", H, "GR", REG) is AuthorityTier.PRIMARY
    assert authority_tier("https://eof.gr/a", H, "US", REG) is AuthorityTier.NONE
    assert authority_tier("https://eof.gr/a", H, None, REG) is AuthorityTier.NONE


def test_wrong_domain_is_none():
    assert authority_tier("https://who.int/x", L, None, REG) is AuthorityTier.NONE


def test_seed_registry_is_unreviewed_so_everything_is_none():
    assert authority_tier("https://who.int/x", H, None) is AuthorityTier.NONE


def test_rank_puts_primary_first_and_is_stable():
    rs = [
        {"url": "https://blog.example/a"},
        {"url": "https://who.int/a"},
        {"url": "https://blog.example/b"},
    ]
    out = rank_by_authority(rs, H, None, REG)
    assert [r["url"] for r in out] == [
        "https://who.int/a",
        "https://blog.example/a",
        "https://blog.example/b",
    ]


def _verified(refs, source="search"):
    return {"c": EvidenceBundle(label="VERIFIED", source=source, evidence_refs=refs)}


def _policy(country=None):
    return HighStakesPolicy(StakesProfile(domain=H, jurisdiction=Jurisdiction(country=country)))


def _use_test_registry(monkeypatch):
    import reasoner.application.services.evidence_service as es

    monkeypatch.setattr(es, "authority_tier", lambda u, d, c: authority_tier(u, d, c, REG))


def test_high_stakes_blog_only_drops(monkeypatch):
    _use_test_registry(monkeypatch)
    allowed = {"https://blog.example/a"}
    out = apply_promotion_rules(_verified(list(allowed)), allowed, _policy())
    assert out["c"].label == "HYPOTHESIS"


def test_high_stakes_primary_keeps_verified(monkeypatch):
    _use_test_registry(monkeypatch)
    allowed = {"https://who.int/a"}
    out = apply_promotion_rules(_verified(list(allowed)), allowed, _policy())
    assert out["c"].label == "VERIFIED"


def test_high_stakes_wrong_country_drops(monkeypatch):
    _use_test_registry(monkeypatch)
    allowed = {"https://eof.gr/a"}
    out = apply_promotion_rules(_verified(list(allowed)), allowed, _policy("US"))
    assert out["c"].label == "HYPOTHESIS"


def test_health_runs_are_kept_out_of_memory():
    assert keep_out_of_memory("What is the max dosage of ibuprofen?")
    assert keep_out_of_memory("Ποια είναι η δοσολογία της παρακεταμόλης;")
    assert not keep_out_of_memory("Should I pay off my mortgage?")
    assert not keep_out_of_memory("Explain quicksort")
