"""Pure business logic: value objects, rules, and calculations.

ADR-0003 makes this the only layer with no I/O. Nothing here may import SQLAlchemy,
FastAPI, or anything from the other packages — ruff's TID251 rule enforces that, and
it is what lets the interesting logic be tested exhaustively in milliseconds.
"""
