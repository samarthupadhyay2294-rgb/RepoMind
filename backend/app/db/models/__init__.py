"""Register ORM models on Base.metadata (package form wins over models.py)."""

from app.db.models.graph import CodeRelationship, CodeSymbol  # noqa: F401
from app.db.models.investigation import Investigation, InvestigationAction  # noqa: F401
from app.db.models.overview import ArchitectureOverview  # noqa: F401
from app.db.models.repository import Repository  # noqa: F401
from app.db.models.snapshot import RepositoryIndexSnapshot  # noqa: F401
