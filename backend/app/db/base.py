"""Single shared SQLAlchemy 2.x declarative base for all RepoMind models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
