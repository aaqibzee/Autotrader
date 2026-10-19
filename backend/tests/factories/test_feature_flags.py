from __future__ import annotations

from app.db.session import SyncSessionLocal
from app.models.feature_flag import FeatureFlag
from tests.factories.feature_flags import make_feature_flag_factory


def test_feature_flag_factory_uses_explicit_session_and_flushes() -> None:
    # Real PostgreSQL, not SQLite: factories must satisfy the same constraints (here the
    # normalised-name CHECK) that production writes do.
    with SyncSessionLocal() as session:
        factory = make_feature_flag_factory(session)
        flag = factory(name='value_my_car', enabled=True)
        generated = factory()
        assert isinstance(flag, FeatureFlag)
        assert flag.id is not None
        assert session.get(FeatureFlag, flag.id) is flag
        assert generated.name.startswith('feature_flag_')
        session.rollback()
