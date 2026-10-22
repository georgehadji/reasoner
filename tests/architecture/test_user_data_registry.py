"""The user-data registry holds every store that keeps a user's data (DAT-11).

A store dropped from the registry stops being exported and erased by every
route at once, so the build fails when one goes missing.
"""

from __future__ import annotations

import pytest

from reasoner.api.user_data import ACCOUNT_STORE_NAMES, data_stores, user_data_stores

pytestmark = pytest.mark.unit

REQUIRED = {
    "profile", "subscriptions", "quota", "query_log", "credit_ledger",
    "events", "uploads", "vectors", "history", "valkey", "neuro", "identity",
}


def _names(stores) -> list[str]:
    return [s.name for s in stores]


def test_registry_holds_every_required_store():
    assert REQUIRED <= set(_names(user_data_stores()))


def test_store_names_are_unique():
    names = _names(user_data_stores())
    assert len(names) == len(set(names))


def test_identity_is_erased_last_and_the_profile_row_just_before_it():
    names = _names(user_data_stores())
    assert names[-1] == "identity"
    assert names.index("profile") == len(names) - 2


def test_vectors_run_before_uploads_because_they_need_the_upload_ids():
    names = _names(user_data_stores())
    assert names.index("vectors") < names.index("uploads")


def test_the_data_route_erases_everything_except_the_account_itself():
    assert set(_names(data_stores())) == set(_names(user_data_stores())) - ACCOUNT_STORE_NAMES
    assert ACCOUNT_STORE_NAMES == {"profile", "identity"}
