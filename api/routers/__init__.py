"""HTTP layer: parse, authorise, delegate to a service, serialise the result.

A router function is at most ~15 lines (AGENTS.md §3). Authorisation is applied with the
shared dependencies from core/dependencies.py, never with an inline role check.
"""
