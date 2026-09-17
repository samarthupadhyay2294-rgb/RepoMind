"""Import all ORM models so Base.metadata covers the full schema."""

from app.db.models.graph import CodeRelationship, CodeSymbol  # noqa: F401
from app.db.models.repository import Repository  # noqa: F401
