from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.feature_flag import FeatureFlag


def make_feature_flag_factory(session: Session):
    import factory
    from factory.alchemy import SQLAlchemyModelFactory

    class BoundFeatureFlagFactory(SQLAlchemyModelFactory):
        class Meta:
            model = FeatureFlag
            sqlalchemy_session = session
            sqlalchemy_session_persistence = 'flush'

        name = factory.Sequence(lambda number: f'feature_flag_{number}')
        enabled = False

    return BoundFeatureFlagFactory
