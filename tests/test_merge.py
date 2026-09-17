"""Tests for the field-level merge -- the part of the pipeline with real logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crm.schema import Contact, SOURCE_APOLLO, SOURCE_EXPLORIUM, SOURCE_MANUAL, Provenance
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
