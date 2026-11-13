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

import os
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


def en_pruebas() -> bool:
    """`TESTING=1`: lo pone `tests/conftest.py` antes de importar la app.

    Segunda auditoría 2026-11 (hallazgo 16): es la única lectura de `TESTING` en
    `app/` y se queda en el entorno a propósito. No es un ajuste del operador
    sino una señal del arnés, y las pruebas la cambian en caliente con
    `monkeypatch.setenv` después de construir `Settings`; por eso se lee en cada
    llamada.
    """
    return os.getenv("TESTING") == "1"


def ejecutando_pytest() -> bool:
    """`PYTEST_CURRENT_TEST` lo pone pytest en cada prueba; no lo controla nadie más."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))
