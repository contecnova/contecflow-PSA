"""Exact-precision column types for monetary values.

Money was modelled as ``Column(Float)`` across the schema, which stores and
aggregates amounts in IEEE-754 binary floats — unacceptable for invoicing, tax,
revenue recognition and FX. These ``Numeric`` aliases store and aggregate money
exactly in PostgreSQL.

``asdecimal=False`` keeps the Python-side value a ``float`` so existing
arithmetic and API serialisation are unchanged (no Decimal/float TypeErrors,
no response-shape change) — the integrity win is exact storage + exact SUM in
the database. Tightening the Python layer to ``Decimal`` end-to-end can follow
without another DB migration.
"""
from sqlalchemy import Numeric

# Currency amounts: up to 9,999,999,999,999,999.99
Money = Numeric(18, 2, asdecimal=False)

# Rates / unit prices that need sub-cent precision (FX rates, hourly cost rates)
Rate = Numeric(18, 6, asdecimal=False)
