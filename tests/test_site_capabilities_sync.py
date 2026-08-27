"""Drift guard for ui-next/src/lib/capabilities.generated.ts.

The landing page's capability numbers (reasoning methods, routable models,
provider labs, ...) are generated from live code by
scripts/update_mindmap_meta.py so they cannot silently drift from what the
registry/preset/phase code actually contains — see docs/plans/
homepage-trust-remediation.md, Phase 1. This test regenerates the file's
content in memory and fails if the committed file disagrees, so an editor
who hand-tweaks a number (or forgets to rerun the generator after changing a
preset) finds out in CI, not in a support ticket from an enterprise buyer's
procurement team.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import update_mindmap_meta as mindmap  # noqa: E402

#: The mechanism sections (§1–§9) live here, not on the home page — they were
#: split off so the landing page could carry the claim and the exhibits alone.
CAPABILITIES_PAGE = Path("ui-next/src/components/landing/CapabilitiesPage.tsx")


def _strip_volatile(text: str) -> str:
    """Drop fields that legitimately differ between two runs of this test.

    ``generatedAt``/the header date differ same-day vs. next-day. ``testFiles``
    counts ``tests/*.py`` directly — in an actively-developed repo, a test file
    can be added or removed by other work between this generator running at
    commit time and this test running in CI minutes later. That is real,
    expected repo activity, not staleness, so it gets a separate loose sanity
    check below instead of exact-match — the same way you would not assert
    two ``datetime.now()`` calls are equal.
    """
    text = re.sub(r"on \d{4}-\d{2}-\d{2}|generatedAt: '[^']+'", "", text)
    return re.sub(r"testFiles: \d+", "testFiles: N", text)


def test_capabilities_generated_ts_matches_live_counts() -> None:
    committed = mindmap.CAPABILITIES_TS.read_text(encoding="utf-8")

    today = date.today().isoformat()
    fresh = mindmap._render_capabilities_ts(
        today,
        mindmap._count_presets(),
        mindmap._count_methods(),
    )

    assert _strip_volatile(committed) == _strip_volatile(fresh), (
        "ui-next/src/lib/capabilities.generated.ts is stale. Regenerate it with "
        "`python scripts/update_mindmap_meta.py` (or let the post-commit hook do it) "
        "and commit the result — do not hand-edit the numbers."
    )

    match = re.search(r"testFiles: (\d+)", committed)
    assert match, "capabilities.generated.ts is missing a testFiles field"
    live_tests = mindmap._count_test_files()
    assert abs(int(match.group(1)) - live_tests) < 20, (
        f"committed testFiles ({match.group(1)}) is wildly off from the live "
        f"count ({live_tests}) — regenerate if this reflects a real, settled change."
    )


def test_sycophancy_controls_match_code() -> None:
    """SYCOPHANCY_CONTROLS must match what the detectors find in the live tree.

    Same drift-guard contract as the capability counts above — a control is a
    claim about the code, and it must be regenerated, not hand-tweaked, when
    the code changes. See docs/plans/sycophancy-mitigation.md workstream W10.
    """
    committed = mindmap.CAPABILITIES_TS.read_text(encoding="utf-8")
    live = mindmap._detect_sycophancy_controls()

    for key, expected in live.items():
        pattern = rf"{key}: (true|false)"
        match = re.search(pattern, committed)
        assert match, f"capabilities.generated.ts is missing SYCOPHANCY_CONTROLS.{key}"
        committed_value = match.group(1) == "true"
        assert committed_value == expected, (
            f"SYCOPHANCY_CONTROLS.{key} is stale: committed={committed_value}, "
            f"live={expected}. Regenerate with `python scripts/update_mindmap_meta.py`."
        )


def test_no_control_claimed_without_mechanism() -> None:
    """Each detector that returns True must be backed by an artefact that actually exists.

    Guards against a detector regressing to "return True" — every currently-true
    control is paired with the file it inspects, independent of the detector's
    own internal logic.
    """
    checks = {
        "noApprovalGradient": (
            Path("src/reasoner/core/learning_guard.py").exists()
            and "check_reward_signal_purity("
            in Path("src/reasoner/infrastructure/learning/online_learner.py").read_text(encoding="utf-8")
        ),
        "mandatoryDissent": "destructive" in Path("src/reasoner/core/perspectives.py").read_text(encoding="utf-8"),
        "confidencePenalty": "confidence_vs_accuracy_penalty"
        in Path("src/reasoner/phases/multi_perspective.py").read_text(encoding="utf-8"),
        "revisionLicence": "_REVISION_LICENCE" in Path("src/reasoner/phases/_shared.py").read_text(encoding="utf-8"),
    }
    live = mindmap._detect_sycophancy_controls()
    for key, artefact_present in checks.items():
        if live[key]:
            assert artefact_present, (
                f"{key} detector returned True but its backing artefact is missing — "
                "the detector may have regressed to an unconditional pass."
            )


def test_capabilities_page_renders_no_ungated_sycophancy_claim() -> None:
    """Every §6 Sycophancy paragraph must sit behind a SYCOPHANCY_CONTROLS guard.

    This is the test that stops the next hand-written sentence — the exact
    failure mode observed once already on the rail's stage-03 `defence`
    string before it was corrected. A <Body> block with no preceding
    SYCOPHANCY_CONTROLS reference is an ungated claim.

    The section moved from LandingPage.tsx to CapabilitiesPage.tsx when the
    mechanism argument was split off the home page onto /capabilities; the
    guard contract did not move with it in spirit only, so this asserts
    against the new file.
    """
    page = CAPABILITIES_PAGE.read_text(encoding="utf-8")
    match = re.search(
        r'<Section id="sycophancy".*?</Section>', page, re.DOTALL,
    )
    assert match, "CapabilitiesPage.tsx has no §6 Sycophancy section"
    section = match.group(0)

    idx = 0
    body_positions = []
    while True:
        pos = section.find("<Body>", idx)
        if pos == -1:
            break
        body_positions.append(pos)
        idx = pos + 1

    prev_end = 0
    for pos in body_positions:
        preceding_block = section[prev_end:pos]
        assert "SYCOPHANCY_CONTROLS." in preceding_block, (
            "Found a <Body> in the §6 Sycophancy section with no "
            "SYCOPHANCY_CONTROLS.* guard immediately before it — every claim in "
            "that section must be gated, never hand-added past the generator."
        )
        prev_end = pos


def test_rail_and_section_agree() -> None:
    """The rail's stage-03 entry and the §6 Sycophancy section must point at each other.

    Before this test existed, stage 03 linked to /how-it-works#adjudication
    while the site had no #sycophancy section at all — a claim with nothing to
    click through to. The rail stayed on the home page when the mechanism
    sections moved to /capabilities, so the href is now cross-page; what the
    test guards is unchanged — the link must resolve to the section that
    exists.
    """
    rail = Path("ui-next/src/components/landing/MechanismDiagram.tsx").read_text(encoding="utf-8")
    page = CAPABILITIES_PAGE.read_text(encoding="utf-8")

    assert 'id="sycophancy"' in page, "CapabilitiesPage.tsx must define the #sycophancy anchor"
    assert "href: '/capabilities#sycophancy'" in rail, (
        "MechanismDiagram's sycophancy stage must link to '/capabilities#sycophancy' "
        "now that the section lives there — see docs/plans/sycophancy-mitigation.md W10c."
    )

    controls = mindmap._detect_sycophancy_controls()
    if controls["premiseAudit"]:
        assert "stage: 'Critique'" not in rail.split("failure: 'Sycophancy'")[1].split("},")[0], (
            "Once premiseAudit ships, the honest stage label is 'Premises', not "
            "'Critique' — the premise audit runs in Phase 1, before critique."
        )


def test_capabilities_excludes_image_generation_models() -> None:
    """directModels must count reasoning-eligible models only.

    _MODEL_WHITELIST also carries image-generation aliases; folding those
    into a number shown next to "reasoning methods" would misrepresent the
    capability, which is exactly the class of claim Phase 0 of the trust
    remediation removed. Guards against a future edit re-merging the counts.
    """
    committed = mindmap.CAPABILITIES_TS.read_text(encoding="utf-8")
    match = re.search(r"directModels: (\d+)", committed)
    assert match, "capabilities.generated.ts is missing a directModels field"

    reasoning_models = mindmap._count_reasoning_models()
    assert int(match.group(1)) == reasoning_models
    assert reasoning_models < mindmap._count_models(), (
        "directModels should be smaller than the raw whitelist size once "
        "image-generation aliases are excluded — if this fails, either the "
        "filter broke or the registry stopped carrying image models."
    )
