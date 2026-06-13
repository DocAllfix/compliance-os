"""Amisys QHSE — router modulari (Fase B/C).

Ogni router è un APIRouter registrato su app via include_router in api_server.
Condividono auth/ownership da api_deps per evitare import circolari.
"""
