"""Tests for the field-level merge -- the part of the pipeline with real logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm.schema import (
    Contact,
    SOURCE_APOLLO,
    SOURCE_EXPLORIUM,
    SOURCE_LINKEDIN,
    SOURCE_MANUAL,
    Provenance,
    FIELD_TRUST,
    DEFAULT_TRUST,
    KNOWN_SOURCES,
    trust_for,
)
from crm.master import merge_all, resolve_field, build_index


def test_new_record_is_created():
    master, report = merge_all([], [Contact(first_name="Ada", email="ada@example.com")],
                               SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    assert len(master) == 1
    assert len(report.created) == 1
    assert master[0].sources == [SOURCE_APOLLO]
    assert master[0].provenance["email"]["source"] == SOURCE_APOLLO


def test_same_person_matches_on_email_not_duplicated():
    base, _ = merge_all([], [Contact(first_name="Ada", email="ada@example.com")],
                        SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, report = merge_all(base, [Contact(first_name="Ada", email="ADA@example.com",
                                              title="CTO")],
                               SOURCE_EXPLORIUM, "2026-09-08T00:00:00+00:00")
    assert len(merged) == 1, "case-different email must not create a second record"
    assert merged[0].title == "CTO"
    assert set(merged[0].sources) == {SOURCE_APOLLO, SOURCE_EXPLORIUM}


def test_empty_incoming_never_clobbers_a_populated_field():
    base, _ = merge_all([], [Contact(email="ada@example.com", title="CTO")],
                        SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, _ = merge_all(base, [Contact(email="ada@example.com", title=None)],
                          SOURCE_EXPLORIUM, "2026-09-08T00:00:00+00:00")
    assert merged[0].title == "CTO"


def test_higher_trust_source_wins_on_disagreement():
    # Explorium outranks Apollo on `title` per FIELD_TRUST.
    base, _ = merge_all([], [Contact(email="ada@example.com", title="Engineer")],
                        SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, report = merge_all(base, [Contact(email="ada@example.com", title="CTO")],
                               SOURCE_EXPLORIUM, "2026-09-02T00:00:00+00:00")
    assert merged[0].title == "CTO"
    assert any(c["reason"] == "higher_trust" for c in report.field_changes)


def test_lower_trust_source_does_not_win():
    # Apollo outranks Explorium on `email`.
    base, _ = merge_all([], [Contact(linkedin_url="linkedin.com/in/ada",
                                     email="ada@corp.com")],
                        SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, report = merge_all(base, [Contact(linkedin_url="linkedin.com/in/ada",
                                              email="ada@other.com")],
                               SOURCE_EXPLORIUM, "2026-09-02T00:00:00+00:00")
    assert merged[0].email == "ada@corp.com"
    assert report.conflicts_held == [] or all(
        c["field"] != "email" for c in report.conflicts_held
    ), "a lower-trust rejection is a held value, not a conflict"


def test_manual_edit_survives_the_next_sync():
    """The whole point of provenance: a human correction is not overwritten."""
    base, _ = merge_all([], [Contact(email="ada@example.com", title="Corrected By Hand")],
                        SOURCE_MANUAL, "2026-09-05T00:00:00+00:00")
    merged, _ = merge_all(base, [Contact(email="ada@example.com", title="Stale Title")],
                          SOURCE_EXPLORIUM, "2026-09-12T00:00:00+00:00")
    assert merged[0].title == "Corrected By Hand"


def test_equal_trust_conflict_is_held_and_reported():
    # phone is trust 15 for both sources; observations 1 day apart.
    base, _ = merge_all([], [Contact(email="ada@example.com", phone="+1-111")],
                        SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, report = merge_all(base, [Contact(email="ada@example.com", phone="+1-222")],
                               SOURCE_EXPLORIUM, "2026-09-02T00:00:00+00:00")
    assert merged[0].phone == "+1-111"
    assert any(c["field"] == "phone" for c in report.conflicts_held)


def test_equal_trust_materially_fresher_observation_wins():
    base, _ = merge_all([], [Contact(email="ada@example.com", phone="+1-111")],
                        SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, report = merge_all(base, [Contact(email="ada@example.com", phone="+1-222")],
                               SOURCE_EXPLORIUM, "2026-10-01T00:00:00+00:00")
    assert merged[0].phone == "+1-222"
    assert any(c["reason"] == "fresher" for c in report.field_changes)


def test_technologies_union_rather_than_replace():
    base, _ = merge_all([], [Contact(email="ada@example.com", technologies=["salesforce"])],
                        SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, _ = merge_all(base, [Contact(email="ada@example.com", technologies=["snowflake"])],
                          SOURCE_EXPLORIUM, "2026-09-08T00:00:00+00:00")
    assert merged[0].technologies == ["salesforce", "snowflake"]


def test_foreign_keys_are_additive():
    base, _ = merge_all([], [Contact(email="ada@example.com", apollo_contact_id="a1")],
                        SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, _ = merge_all(base, [Contact(email="ada@example.com", explorium_prospect_id="e1")],
                          SOURCE_EXPLORIUM, "2026-09-08T00:00:00+00:00")
    assert merged[0].apollo_contact_id == "a1"
    assert merged[0].explorium_prospect_id == "e1"


def test_merge_is_idempotent():
    """Re-running the same week's data must not churn the master file."""
    incoming = [Contact(email="ada@example.com", title="CTO", phone="+1-111")]
    base, _ = merge_all([], incoming, SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    again, report = merge_all(base, incoming, SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    assert len(again) == 1
    assert report.created == []
    assert report.field_changes == []
    assert report.updated == [], "a repeat run should report no updates"


def test_derived_id_is_stable_across_rebuilds():
    a, _ = merge_all([], [Contact(email="ada@example.com")], SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    b, _ = merge_all([], [Contact(email="ada@example.com")], SOURCE_APOLLO, "2026-10-01T00:00:00+00:00")
    assert a[0].contact_id == b[0].contact_id


def test_ambiguous_match_is_reported_not_silently_fused():
    """One incoming record pointing at two master records must be flagged."""
    master, _ = merge_all(
        [],
        [Contact(email="ada@example.com"), Contact(linkedin_url="linkedin.com/in/ada")],
        SOURCE_APOLLO,
        "2026-09-01T00:00:00+00:00",
    )
    assert len(master) == 2
    merged, report = merge_all(
        master,
        [Contact(email="ada@example.com", linkedin_url="linkedin.com/in/ada")],
        SOURCE_EXPLORIUM,
        "2026-09-08T00:00:00+00:00",
    )
    assert report.ambiguous_matches, "collision must be surfaced for a human"
    assert len(merged) == 2, "records must not be silently fused"


def test_domain_normalization_matches_url_variants():
    base, _ = merge_all([], [Contact(first_name="Ada", last_name="Lovelace",
                                     company_domain="https://www.example.com/about")],
                        SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, _ = merge_all(base, [Contact(first_name="Ada", last_name="Lovelace",
                                         company_domain="example.com", title="CTO")],
                          SOURCE_EXPLORIUM, "2026-09-08T00:00:00+00:00")
    assert len(merged) == 1
    assert merged[0].title == "CTO"


def test_index_covers_every_identity_key():
    c = Contact(email="ada@example.com", linkedin_url="linkedin.com/in/ada",
                first_name="Ada", last_name="Lovelace", company_domain="example.com")
    c.ensure_id()
    index = build_index([c])
    assert len(index) == 3


def test_reaffirmation_keeps_original_source():
    """An identical value from a second source refreshes the timestamp only.

    Otherwise an identity field carried along for matching (email, domain)
    gets re-credited to the later source, and push_apollo.py would then try
    to teach Apollo a value Apollo supplied in the first place.
    """
    base, _ = merge_all([], [Contact(email="ada@example.com", company_domain="example.com")],
                        SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, _ = merge_all(base, [Contact(email="ada@example.com", company_domain="example.com",
                                         title="Fixed")],
                          SOURCE_MANUAL, "2026-09-10T00:00:00+00:00")
    prov = merged[0].provenance
    assert prov["company_domain"]["source"] == SOURCE_APOLLO
    assert prov["company_domain"]["observed_at"] == "2026-09-10T00:00:00+00:00"
    assert prov["title"]["source"] == SOURCE_MANUAL


# --------------------------------------------------------------------------
# LinkedIn as a source. The weights, not the constant, are the feature: a
# source with no weight resolves to trust 0, which loses every conflict AND
# gets silently overwritten. These tests exist so that trap cannot reopen.
# --------------------------------------------------------------------------


def test_every_known_source_is_weighted_everywhere():
    """A source without a weight is a data-loss bug, not a neutral default.

    trust_for() falls back to 0 for an unrecognised source. A field sitting at
    0 is beaten by every other source and can never hold a conflict, so a
    source added to KNOWN_SOURCES but omitted from a FIELD_TRUST row would
    quietly discard data. Fail here instead.
    """
    for source in KNOWN_SOURCES:
        assert source in DEFAULT_TRUST, f"{source} missing from DEFAULT_TRUST"
        for field_name, weights in FIELD_TRUST.items():
            assert source in weights, f"{source} missing from FIELD_TRUST[{field_name!r}]"
            assert trust_for(field_name, source) > 0


def test_manual_still_outranks_every_feed_on_every_field():
    """The one invariant the whole merge rests on: a human edit is final."""
    feeds = [s for s in KNOWN_SOURCES if s != SOURCE_MANUAL]
    for field_name in FIELD_TRUST:
        for feed in feeds:
            assert trust_for(field_name, SOURCE_MANUAL) > trust_for(field_name, feed), (
                f"{feed} would beat a manual edit on {field_name}"
            )


def test_linkedin_wins_title_over_apollo():
    """Someone's own profile describes their job better than a data vendor."""
    master, _ = merge_all([], [Contact(email="ada@example.com", title="Engineer")],
                          SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, _ = merge_all(master, [Contact(email="ada@example.com", title="Head of Platform")],
                          SOURCE_LINKEDIN, "2026-09-02T00:00:00+00:00")
    assert merged[0].title == "Head of Platform"
    assert merged[0].provenance["title"]["source"] == SOURCE_LINKEDIN


def test_linkedin_never_displaces_a_verified_email():
    """A profile rarely exposes an address; Apollo's verified one must hold."""
    master, _ = merge_all([], [Contact(email="ada@example.com", company_domain="example.com")],
                          SOURCE_APOLLO, "2026-09-01T00:00:00+00:00")
    merged, _ = merge_all(master, [Contact(email="ada@personal.example",
                                           company_domain="example.com")],
                          SOURCE_LINKEDIN, "2026-09-02T00:00:00+00:00")
    # Matching is by email, so LinkedIn's differing address creates a second
    # record rather than overwriting the first. What matters is that Apollo's
    # value is still intact and still credited to Apollo.
    apollo_rec = [c for c in merged if c.email == "ada@example.com"][0]
    assert apollo_rec.provenance["email"]["source"] == SOURCE_APOLLO
    assert trust_for("email", SOURCE_LINKEDIN) < trust_for("email", SOURCE_APOLLO)


def test_linkedin_loses_phone_conflict_head_to_head():
    """The field-level rule, isolated from record matching."""
    value, prov, reason = resolve_field(
        "phone",
        "+1 555 0100",
        {"source": SOURCE_APOLLO, "observed_at": "2026-09-01T00:00:00+00:00"},
        "+1 555 9999",
        Provenance(source=SOURCE_LINKEDIN, observed_at="2026-09-02T00:00:00+00:00"),
    )
    assert value == "+1 555 0100"
    assert reason == "lower_trust_held"
    assert prov["source"] == SOURCE_APOLLO


# --------------------------------------------------------------------------
# Vendor ids as identity. The 2026-09-21 run duplicated 15 Apollo contacts
# that had no email: with nothing but name+domain to match on, they became
# new records. A vendor's own id must be the strongest key.
# --------------------------------------------------------------------------

from crm.master import dedupe_by_vendor_id  # noqa: E402


def test_apollo_id_matches_a_contact_with_no_email():
    base, _ = merge_all([], [Contact(first_name="Benjamin", last_name="Lowe",
                                     apollo_contact_id="ap_1")],
                        SOURCE_APOLLO, "2026-09-17T00:00:00+00:00")
    merged, report = merge_all(base, [Contact(first_name="Benjamin", last_name="Lowe",
                                              apollo_contact_id="ap_1", title="Owner")],
                               SOURCE_APOLLO, "2026-09-21T00:00:00+00:00")
    assert len(merged) == 1, "same Apollo id must never create a second record"
    assert merged[0].title == "Owner"
    assert report.created == []


def test_vendor_ids_come_first_in_identity_keys():
    c = Contact(email="ada@example.com", apollo_contact_id="ap_1", explorium_prospect_id="ex_1")
    assert c.identity_keys()[:2] == ["apollo:ap_1", "explorium:ex_1"]


def test_dedupe_folds_duplicates_keeping_the_older_record():
    older = Contact(contact_id="c_old", first_name="Karen", last_name="Desousa",
                    apollo_contact_id="ap_2", first_seen="2026-09-17T00:00:00+00:00",
                    last_updated="2026-09-17T00:00:00+00:00", sources=[SOURCE_APOLLO],
                    provenance={"first_name": {"source": SOURCE_APOLLO, "observed_at": "2026-09-17T00:00:00+00:00"}})
    newer = Contact(contact_id="c_new", first_name="Karen", last_name="Desousa", title="CFO",
                    apollo_contact_id="ap_2", first_seen="2026-09-21T00:00:00+00:00",
                    last_updated="2026-09-21T00:00:00+00:00", sources=[SOURCE_APOLLO],
                    provenance={"title": {"source": SOURCE_APOLLO, "observed_at": "2026-09-21T00:00:00+00:00"}})
    clean, folded = dedupe_by_vendor_id([older, newer, Contact(contact_id="c_x", email="x@example.com")])
    ids = sorted(c.contact_id for c in clean)
    assert ids == ["c_old", "c_x"]
    assert folded == [("c_old", "c_new")]
    kept = next(c for c in clean if c.contact_id == "c_old")
    assert kept.title == "CFO"                                   # the newer record's field survived
    assert kept.provenance["title"]["source"] == SOURCE_APOLLO
    assert kept.first_seen == "2026-09-17T00:00:00+00:00"


def test_dedupe_is_a_no_op_on_a_clean_master():
    master = [Contact(contact_id="a", apollo_contact_id="ap_a"), Contact(contact_id="b", apollo_contact_id="ap_b")]
    clean, folded = dedupe_by_vendor_id(master)
    assert folded == [] and sorted(c.contact_id for c in clean) == ["a", "b"]
