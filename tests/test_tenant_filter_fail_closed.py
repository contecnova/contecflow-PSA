"""El filtro de tenant falla cerrado (auditoría 2026-08, P1-7).

Antes de este cambio había dos fail-open silenciosos en app/db/session.py:

1. `_tenant_filter_for_model` devolvía la consulta SIN FILTRAR cuando el modelo
   no tenía ninguna columna de tenant. El comentario decía "safer than
   crashing", pero convertía cada modelo nuevo sin columna de tenant en una fuga
   entre clientes que ninguna prueba detectaba.

2. Las llamadas a ese filtro estaban envueltas en
   `except Exception: logger.debug(...)`, así que si el filtrado fallaba para un
   modelo la consulta se ejecutaba sin filtro y solo quedaba rastro en un log de
   nivel debug.

Ahora ambos casos lanzan `TenantIsolationError`. Un 500 es un incidente que se
investiga; una consulta sin filtro de tenant no se ve.
"""
from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, String, select

from app.db.base import Base
from app.db.session import (
    TenantIsolationError,
    _is_tenant_exempt,
    _tenant_filter_for_model,
    _tenant_where_for_model,
)


# Modelo de prueba SIN columna de tenant y SIN exención declarada: es exactamente
# la forma que antes pasaba sin filtrar. No se crea la tabla: solo se necesita el
# mapeo para construir la consulta.
class _ModeloSinTenant(Base):
    __tablename__ = "_test_modelo_sin_tenant"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(50))


class _ModeloExento(Base):
    __tablename__ = "_test_modelo_exento"
    id = Column(Integer, primary_key=True)
    _tenant_exempt = True
    _tenant_exempt_reason = "fixture de prueba"


def test_modelo_sin_columna_de_tenant_lanza_en_query(db):
    """La ruta SA 1.x (db.query) no puede devolver una consulta sin filtrar."""
    q = db.query(_ModeloSinTenant)
    with pytest.raises(TenantIsolationError) as exc:
        _tenant_filter_for_model(q, _ModeloSinTenant, "org-1")
    assert "_ModeloSinTenant" in str(exc.value)
    assert "_tenant_exempt" in str(exc.value), "el error debe decir cómo declarar la exención"


def test_modelo_sin_columna_de_tenant_lanza_en_execute():
    """La ruta SA 2.0 (db.execute(select(...))) tiene la misma política."""
    stmt = select(_ModeloSinTenant)
    with pytest.raises(TenantIsolationError):
        _tenant_where_for_model(stmt, _ModeloSinTenant, "org-1")


def test_exencion_declarada_pasa_sin_filtrar(db):
    """Un modelo que declara la exención sí pasa: es una decisión explícita."""
    assert _is_tenant_exempt(_ModeloExento) is True
    q = db.query(_ModeloExento)
    assert _tenant_filter_for_model(q, _ModeloExento, "org-1") is q
    stmt = select(_ModeloExento)
    assert _tenant_where_for_model(stmt, _ModeloExento, "org-1") is stmt


def test_la_exencion_debe_ser_explicita_no_por_ausencia_de_columna():
    """Que falte la columna NO exime. Sólo exime declararlo."""
    assert _is_tenant_exempt(_ModeloSinTenant) is False


def test_organization_es_el_unico_modelo_exento():
    """Inventario cerrado de exenciones.

    Cada exención es un punto donde el aislamiento pasa a ser responsabilidad
    manual del endpoint. Si aparece una nueva hay que justificarla aquí y
    guardar sus rutas (ver tests/test_organization_tenant_isolation.py).
    """
    import app.models  # noqa: F401 — registra los mappers

    exentos = {
        m.class_.__name__
        for m in Base.registry.mappers
        if getattr(m.class_, "_tenant_exempt", False) is True
        and not m.class_.__name__.startswith("_")  # excluye los fixtures de este fichero
    }
    assert exentos == {"Organization"}, (
        f"cambió el conjunto de modelos exentos del filtro de tenant: {sorted(exentos)}"
    )


def test_org_id_none_sigue_pasando_sin_filtrar(db):
    """org_id=None significa superadmin (sin restricción), no "modelo sin tenant".

    Es la vía por la que el superadmin ve entre tenants; no debe verse afectada.
    """
    q = db.query(_ModeloSinTenant)
    assert _tenant_filter_for_model(q, _ModeloSinTenant, None) is q


# ── tenancy.py::_can_access ───────────────────────────────────────────────────

class _Usuario:
    def __init__(self, org_id, superadmin=False):
        self.organization_id = org_id
        self.is_superadmin = superadmin


def test_usuario_sin_organizacion_no_accede_a_nada():
    """Antes devolvía True: un usuario sin organización veía TODOS los tenants.

    Contradecía a TenantSession (que para ese caso devuelve conjunto vacío) y al
    propio comentario de app/core/deps.py.
    """
    from app.core.tenancy import _can_access

    assert _can_access(_Usuario(None), "org-a") is False
    assert _can_access(_Usuario(None), None) is False


def test_filas_globales_siguen_accesibles():
    """row_org_id=None es dato legacy/global: concepto real del esquema."""
    from app.core.tenancy import _can_access

    assert _can_access(_Usuario("org-a"), None) is True


def test_aislamiento_entre_organizaciones():
    from app.core.tenancy import _can_access

    assert _can_access(_Usuario("org-a"), "org-a") is True
    assert _can_access(_Usuario("org-a"), "org-b") is False


def test_superadmin_accede_a_todo():
    from app.core.tenancy import _can_access

    assert _can_access(_Usuario(None, superadmin=True), "org-b") is True
    assert _can_access(_Usuario("org-a", superadmin=True), "org-b") is True
