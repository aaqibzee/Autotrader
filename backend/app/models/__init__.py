# Every module's models are imported here so Alembic and the mapper registry see them
# (Feature 02 A7). Modules never import each other's models.
from app.models.feature_flag import FeatureFlag
from app.modules.taxonomy.models import Make, MakeAlias, ModelAlias, VehicleModel

__all__ = ['FeatureFlag', 'Make', 'MakeAlias', 'ModelAlias', 'VehicleModel']
