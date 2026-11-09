"""Puerta de las operaciones que borran datos (revisión 2026-11).

Medido antes: `setup.sh clean`, `setup.bat start clean`, `scripts/start.sh` y
el sembrado borraban o reescribían la base sin mirar `ENVIRONMENT`; sólo la
sincronización de contraseñas de demo tenía puerta. Todos esos caminos acaban
en `scripts/reset_to_admin_only.py` o en `python -m app.db.seed`, así que la
puerta está aquí, una vez, y vale para todos.

Cierra por defecto, como `is_safe_for_destructive_ops` de `setup.sh`: lo que no
sea un entorno de desarrollo o de pruebas declarado se trata como producción.
"""
from __future__ import annotations

import sys

ENTORNOS_SEGUROS = frozenset({"development", "dev", "local", "test", "testing", "demo"})


def exigir_entorno_no_productivo(operacion: str) -> None:
    """Sale con código 2 si `ENVIRONMENT` no es de desarrollo o pruebas."""
    from app.core.config import settings

    entorno = (settings.ENVIRONMENT or "").strip().lower()
    if entorno not in ENTORNOS_SEGUROS:
        print(f"ERROR: {operacion} borra datos y ENVIRONMENT={entorno or '(vacío)'}. "
              f"Sólo se permite en: {', '.join(sorted(ENTORNOS_SEGUROS))}.", file=sys.stderr)
        raise SystemExit(2)
