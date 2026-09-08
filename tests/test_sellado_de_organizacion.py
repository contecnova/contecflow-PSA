"""195 de 376 modelos nunca se construían con organización, y sus filas eran invisibles.

Auditoría 2026-08. El filtro de tenant es `organization_id == org`, así que una
fila guardada con NULL **no la ve su propia organización**: sólo un superadmin.
Al barrer el código por AST resultó que **195 de los 376 modelos que tienen esa
columna no se construyen nunca con ella**, en 611 sitios. No es un descuido
aislado: es que nadie la sellaba.

Comprobado de punta a punta con dos casos reales, con la sesión y el filtro de
producción:

    performance_service.create_cycle()  -> ciclo con organization_id NULL
      GET /performance/cycles           -> 0 ciclos a su propio creador

    activity_service.notify()           -> notificación con NULL
      GET /enterprise/notifications     -> 0 notificaciones al usuario

En los dos casos **sin un solo error en los registros**: sólo listas vacías, que
es exactamente lo que no se investiga.

Arreglar 611 construcciones una a una sería perseguir el síntoma. La causa es
que la organización del sujeto de la petición no llega a la fila, y el sitio
donde eso se arregla de una vez es el `flush`: `_sellar_organizacion` en
`app/db/session.py`.

## Por qué estos tests enganchan el escuchador a mano

Está registrado sobre `SessionLocal`, y `tests/conftest.py` usa otra factoría
(`TestSession`). **La suite no lo ejercita**, igual que no ejercita el filtro de
tenant. Sin engancharlo aquí, este comportamiento no lo probaría nada — que es
justo la razón por la que el defecto vivió sin verse.

Registrarlo en la factoría de los tests haría que la suite entera trabajara con
la semántica de producción. Es lo correcto a medio plazo y cambia lo que ven
tests que hoy crean filas sin organización, así que es una decisión aparte y
queda anotada en el traspaso.
"""
from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest
from sqlalchemy import event as sa_event

ORG = "org-sellado"
OTRA = "org-sellado-ajena"


@pytest.fixture()
def sesion_de_produccion(db):
    """La sesión de pruebas con el sellado y el filtro de producción activos."""
    from app.db.session import _enforce_tenant_isolation, _sellar_organizacion

    def sellar(sesion, contexto, instancias):
        _sellar_organizacion(sesion)

    sa_event.listen(db, "before_flush", sellar)
    sa_event.listen(db, "do_orm_execute", _enforce_tenant_isolation)
    db.info["is_superadmin"] = False
    db.info["organization_id"] = ORG
    try:
        yield db
    finally:
        sa_event.remove(db, "before_flush", sellar)
        sa_event.remove(db, "do_orm_execute", _enforce_tenant_isolation)
        db.info.pop("is_superadmin", None)
        db.info.pop("organization_id", None)


def _notificacion(**extra):
    from app.models.enterprise import Notification, NotificationType

    return Notification(
        user_id=extra.pop("user_id", "u-sellado"),
        type=list(NotificationType)[0],
        title="Te han asignado algo", body="cuerpo", **extra,
    )


# ── El caso que lo destapó ──────────────────────────────────────────────────

def test_EL_HALLAZGO_una_notificacion_la_ve_su_propio_usuario(db, sesion_de_produccion):
    """Antes del sellado esto devolvía cero: la notificación se creaba invisible."""
    from app.models.enterprise import Notification

    n = _notificacion()
    db.add(n)
    db.commit()

    assert n.organization_id == ORG, "la fila nueva no recibió la organización"
    vistas = db.query(Notification).filter(
        Notification.user_id == "u-sellado").all()
    assert len(vistas) == 1, "el usuario no ve su propia notificación"


def test_la_notificacion_no_la_ve_otra_organizacion(db, sesion_de_produccion):
    """Sellar no puede volverla visible para todos."""
    from app.models.enterprise import Notification

    db.add(_notificacion())
    db.commit()

    db.info["organization_id"] = OTRA
    assert db.query(Notification).filter(
        Notification.user_id == "u-sellado").all() == []


# ── Lo que el sellado NO debe hacer ─────────────────────────────────────────

def test_un_valor_explicito_no_se_sobreescribe(db, sesion_de_produccion):
    """Un superadmin que crea a propósito en otra organización sigue pudiendo.

    Se lee tras el `flush` y antes del `commit`: releer la fila después sería
    una lectura cruzada que el filtro impide, con razón.
    """
    from app.models.performance import ReviewCycle

    c = ReviewCycle(name="Ciclo", created_by="u1", organization_id=OTRA)
    db.add(c)
    db.flush()
    assert c.organization_id == OTRA
    db.rollback()


def test_un_ajuste_global_no_se_sella(db, sesion_de_produccion):
    """En `AppSetting` un NULL significa «valor global del despliegue».

    Sellarlo lo convertiría en un ajuste de un solo cliente, y los demás
    perderían el valor por defecto. Por eso los modelos con
    `_tenant_filter_include_global` quedan fuera.
    """
    from app.models.settings import AppSetting

    a = AppSetting(key="ajuste.global.de.prueba", value="1")
    db.add(a)
    db.flush()
    assert a.organization_id is None
    db.rollback()


def test_un_modelo_exento_no_se_sella(db, sesion_de_produccion):
    """`Organization` ES el tenant: no hay organización que sellarle."""
    from app.models.mfa import Organization

    assert getattr(Organization, "_tenant_exempt", False) is True


def test_sin_organizacion_en_la_sesion_no_se_sella(db):
    """Un job de fondo o un script no tiene contexto, y su comportamiento no
    cambia: sigue creando filas sin organización, como hasta ahora."""
    from app.db.session import _sellar_organizacion

    def sellar(sesion, contexto, instancias):
        _sellar_organizacion(sesion)

    sa_event.listen(db, "before_flush", sellar)
    try:
        n = _notificacion(user_id="u-de-fondo")
        db.add(n)
        db.flush()
        assert n.organization_id is None
        db.rollback()
    finally:
        sa_event.remove(db, "before_flush", sellar)


# ── La medición que justifica el cambio ─────────────────────────────────────

def test_EL_ESTRUCTURAL_cuantos_modelos_no_se_construyen_con_organizacion():
    """No falla: mide y deja el número a la vista.

    Con el sellado la cifra deja de ser un defecto —la organización llega en el
    `flush`— pero sigue siendo la razón por la que el sellado existe, y si
    alguien quita el escuchador esta medida explica lo que se pierde.

    Se comprueba sólo que la medición sigue funcionando y que los modelos
    exentos y globales quedan fuera del recuento, para que el número signifique
    lo que dice.
    """
    from app.db.base import Base
    from app import models  # noqa: F401

    con_columna = {}
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if (hasattr(cls, "organization_id")
                and not getattr(cls, "_tenant_exempt", False)
                and not getattr(cls, "_tenant_filter_include_global", False)):
            con_columna[cls.__name__] = cls

    assert len(con_columna) > 300, "la medición ya no encuentra los modelos"

    con_org, sin_org = set(), set()
    for ruta in sorted(Path("app").rglob("*.py")):
        try:
            arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.Call)
                    and isinstance(nodo.func, ast.Name)
                    and nodo.func.id in con_columna):
                continue
            claves = {k.arg for k in nodo.keywords if k.arg}
            if "organization_id" in claves or any(
                    k.arg is None for k in nodo.keywords):
                con_org.add(nodo.func.id)
            else:
                sin_org.add(nodo.func.id)

    nunca = sin_org - con_org
    print(f"\nmodelos con organization_id: {len(con_columna)}")
    print(f"que se construyen alguna vez con ella: {len(con_org)}")
    print(f"que NUNCA se construyen con ella: {len(nunca)}")
    # Los exentos y los globales no pueden estar en el recuento: si aparecen, la
    # medida esta mal y el numero no significa nada.
    from app.models.mfa import Organization
    from app.models.settings import AppSetting
    assert Organization.__name__ not in nunca
    assert AppSetting.__name__ not in nunca
