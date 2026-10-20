"""Visibility, `listed_at`, `system_update` and the invariant checker (Feature 02 slice 2.6).

Lock-token tests commit between steps: `now()` is fixed for a whole Postgres transaction,
so an "updated_at unchanged" check inside one transaction would pass even if `onupdate`
fired.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import datetime
from itertools import product
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.concurrency import StaleUpdateError, ensure_not_stale
from app.db.session import SyncSessionLocal, sync_engine
from app.models import Dealer, Listing
from app.modules.listings.enums import ListingStatus, ModerationStatus
from app.modules.listings.services import (
    SYSTEM_COLUMNS,
    SystemColumnError,
    system_update,
    verify_listing_invariants,
)
from app.modules.listings.visibility import is_publicly_visible, on_change, publicly_visible
from tests.factories.dealers import create_dealer
from tests.factories.listings import Vehicle, create_listing, create_vehicle


@pytest.fixture
def session() -> Generator[Session, None, None]:
    """A session whose work is rolled back at the end of the test."""
    with Session(sync_engine) as session:
        try:
            yield session
        finally:
            session.rollback()


@pytest.fixture
def committed() -> Generator[Callable[[], tuple[Dealer, Vehicle]], None, None]:
    """Committed dealer + vehicle, for tests that need several transactions; cleaned up after."""
    dealer_ids: list[UUID] = []
    vehicles: list[Vehicle] = []

    def make() -> tuple[Dealer, Vehicle]:
        with SyncSessionLocal.begin() as session:
            dealer = create_dealer(session)
            vehicle = create_vehicle(session)
            session.expunge(dealer)
        dealer_ids.append(dealer.id)
        vehicles.append(vehicle)
        return dealer, vehicle

    yield make
    with sync_engine.begin() as connection:
        for dealer_id in dealer_ids:  # cascades to their listings
            connection.execute(text('DELETE FROM dealers WHERE id = :id'), {'id': dealer_id})
        for vehicle in vehicles:
            connection.execute(
                text('DELETE FROM vehicle_models WHERE id = :id'), {'id': vehicle.model_id}
            )
            connection.execute(text('DELETE FROM makes WHERE id = :id'), {'id': vehicle.make_id})


def _token(listing_id: UUID) -> datetime:
    with SyncSessionLocal() as session:
        return session.execute(
            select(Listing.updated_at).where(Listing.id == listing_id)
        ).scalar_one()


def _new_committed_listing(make: Callable[[], tuple[Dealer, Vehicle]], **kwargs: Any) -> UUID:
    dealer, vehicle = make()
    with SyncSessionLocal.begin() as session:
        return create_listing(session, session.merge(dealer), vehicle, **kwargs).id


# --- publicly_visible over every state -------------------------------------------------


def test_publicly_visible_over_every_status_and_moderation_state(session: Session) -> None:
    dealer, vehicle = create_dealer(session), create_vehicle(session)
    expected_visible: set[UUID] = set()
    created: list[Listing] = []
    for status, moderation in product(ListingStatus, ModerationStatus):
        # Archived rows carry archived_at (the schema ties the two), so the archived
        # dimension is covered by status = archived.
        listing = create_listing(
            session, dealer, vehicle, status=status, moderation_status=moderation
        )
        created.append(listing)
        if (
            status in (ListingStatus.ACTIVE, ListingStatus.RESERVED)
            and moderation == ModerationStatus.CLEAR
        ):
            expected_visible.add(listing.id)

    ids = [listing.id for listing in created]
    visible_in_sql = set(
        session.scalars(select(Listing.id).where(Listing.id.in_(ids), publicly_visible()))
    )
    visible_in_python = {listing.id for listing in created if is_publicly_visible(listing)}

    assert len(created) == 20
    assert len(expected_visible) == 2
    assert visible_in_sql == expected_visible
    assert visible_in_python == expected_visible


# --- system_update leaves the lock token alone ---------------------------------------


def test_system_update_leaves_updated_at_and_a_dealers_token_valid(committed: Any) -> None:
    listing_id = _new_committed_listing(committed)
    token = _token(listing_id)

    with SyncSessionLocal.begin() as session:
        assert system_update(session, listing_id, moderation_status=ModerationStatus.HIDDEN)
    with SyncSessionLocal.begin() as session:
        assert system_update(session, listing_id, photo_count=7, latitude=51.5, longitude=-0.12)

    with SyncSessionLocal() as session:
        listing = session.get_one(Listing, listing_id)
        assert (listing.moderation_status, listing.photo_count) == ('hidden', 7)
        assert listing.updated_at == token
        # The dealer's PATCH, carrying the pre-change token, still passes the lock check.
        ensure_not_stale(listing.updated_at, token, {})


def test_a_dealer_edit_does_change_the_token(committed: Any) -> None:
    # Negative proof: the test above would catch onupdate firing, because it does fire here.
    listing_id = _new_committed_listing(committed)
    token = _token(listing_id)

    with SyncSessionLocal.begin() as session:
        session.get_one(Listing, listing_id).price_pence = 999_500

    assert _token(listing_id) != token
    with pytest.raises(StaleUpdateError):
        ensure_not_stale(_token(listing_id), token, {})


def test_on_change_leaves_updated_at_alone(committed: Any) -> None:
    listing_id = _new_committed_listing(committed, moderation_status=ModerationStatus.HELD)
    token = _token(listing_id)
    with SyncSessionLocal.begin() as session:
        listing = session.get_one(Listing, listing_id)
        assert system_update(session, listing_id, moderation_status=ModerationStatus.CLEAR)
        assert on_change(session, listing)
    assert _token(listing_id) == token


@pytest.mark.parametrize(
    'columns',
    [{'price_pence': 1}, {'status': 'sold'}, {'updated_at': None}, {'title': 'x'}, {}],
)
def test_system_update_refuses_columns_it_does_not_own(
    session: Session, columns: dict[str, Any]
) -> None:
    listing = create_listing(session, create_dealer(session), create_vehicle(session))
    with pytest.raises(SystemColumnError):
        system_update(session, listing.id, **columns)


def test_system_update_allow_list_is_the_designs() -> None:
    assert SYSTEM_COLUMNS == {
        'moderation_status',
        'listed_at',
        'photo_count',
        'latitude',
        'longitude',
    }


def test_system_update_reports_a_missing_row(session: Session) -> None:
    assert system_update(session, UUID(int=1), photo_count=1) is False


# --- listed_at ---------------------------------------------------------------------


def _listed_at(listing_id: UUID) -> datetime | None:
    with SyncSessionLocal() as session:
        return session.execute(
            select(Listing.listed_at).where(Listing.id == listing_id)
        ).scalar_one()


def test_listed_at_lifecycle(committed: Any) -> None:
    # Published while held (Feature 14): not visible, so not listed yet.
    listing_id = _new_committed_listing(committed, moderation_status=ModerationStatus.HELD)
    assert _listed_at(listing_id) is None

    # Hold released: visible for the first time, so listed now.
    with SyncSessionLocal.begin() as session:
        listing = session.get_one(Listing, listing_id)
        system_update(session, listing_id, moderation_status=ModerationStatus.CLEAR)
        assert on_change(session, listing) is True
    first = _listed_at(listing_id)
    assert first is not None

    # Unpublish, then republish in later transactions (a later now()): never reset.
    for status in (ListingStatus.DRAFT, ListingStatus.ACTIVE):
        with SyncSessionLocal.begin() as session:
            listing = session.get_one(Listing, listing_id)
            listing.status = status
            assert on_change(session, listing) is False
        assert _listed_at(listing_id) == first


def test_on_change_does_not_list_an_invisible_listing(session: Session) -> None:
    dealer, vehicle = create_dealer(session), create_vehicle(session)
    for status in (ListingStatus.DRAFT, ListingStatus.SOLD, ListingStatus.ARCHIVED):
        listing = create_listing(session, dealer, vehicle, status=status)
        assert listing.listed_at is None
        assert on_change(session, listing) is False


def test_on_change_reads_the_row_not_a_stale_object(session: Session) -> None:
    listing = create_listing(
        session,
        create_dealer(session),
        create_vehicle(session),
        moderation_status=ModerationStatus.HELD,
    )
    # Another writer clears the hold behind this object's back; the object still says held.
    session.execute(
        update(Listing)
        .where(Listing.id == listing.id)
        .values(moderation_status='clear')
        .execution_options(synchronize_session=False)
    )
    assert listing.moderation_status == ModerationStatus.HELD
    assert on_change(session, listing) is True
    assert listing.listed_at is not None


# --- verify_listing_invariants -------------------------------------------------------


def _mismatches_for(session: Session, ids: set[UUID], **kwargs: Any) -> list[tuple[UUID, str]]:
    return sorted(
        (mismatch.listing_id, mismatch.column)
        for mismatch in verify_listing_invariants(session, **kwargs)
        if mismatch.listing_id in ids
    )


def test_invariants_hold_for_factory_rows_across_batches(session: Session) -> None:
    dealer, vehicle = create_dealer(session), create_vehicle(session)
    ids = {create_listing(session, dealer, vehicle, status=status).id for status in ListingStatus}
    ids.add(
        create_listing(
            session,
            dealer,
            vehicle,
            status=ListingStatus.DRAFT,
            fuel_type=None,
            year=None,
            vrm=None,
        ).id
    )
    assert _mismatches_for(session, ids, batch_size=2) == []


@pytest.mark.parametrize(
    ('corruption', 'column'),
    [
        ("title = 'A different title'", 'title'),
        ('ulez_compliant = NOT ulez_compliant', 'ulez_compliant'),
        ("variant = 'Titanium'", 'title'),  # the title no longer matches its inputs
        ("registration_date = DATE '2004-06-01'", 'ulez_compliant'),
        ('listed_at = NULL', 'listed_at'),
    ],
)
def test_invariant_checker_catches_a_corrupted_row(
    session: Session, corruption: str, column: str
) -> None:
    dealer, vehicle = create_dealer(session), create_vehicle(session)
    good = create_listing(session, dealer, vehicle)
    bad = create_listing(session, dealer, vehicle)
    session.execute(text(f'UPDATE listings SET {corruption} WHERE id = :id'), {'id': bad.id})

    assert _mismatches_for(session, {good.id, bad.id}) == [(bad.id, column)]


def test_invariant_checker_reads_renamed_and_inactive_taxonomy(session: Session) -> None:
    # The title must be recomputed from the names as they are now (a rename changes it).
    dealer, vehicle = create_dealer(session), create_vehicle(session)
    listing = create_listing(session, dealer, vehicle)
    session.execute(
        text("UPDATE vehicle_models SET name = 'Fiesta Mk8', is_active = false WHERE id = :id"),
        {'id': vehicle.model_id},
    )
    assert _mismatches_for(session, {listing.id}) == [(listing.id, 'title')]
