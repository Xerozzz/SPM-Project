"""Business orchestration and transaction boundaries.

Services call repositories and the domain layer. They never import SQLAlchemy for queries.
"""
