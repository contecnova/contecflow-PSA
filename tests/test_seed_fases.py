"""La siembra de datos de demostración, fase a fase.

Auditoría 2026-08 (P3-18). `seed()` era complejidad **67** en 528 líneas: la
función más compleja del proyecto y, con 57 de exceso, el 12 % de todo lo que
quedaba del hallazgo. Ya venía dividida en 24 secciones marcadas con
comentarios, así que la partición no se inventó: se leyó.

Son datos de demostración, así que el riesgo de tocarlo es bajo — y por eso
mismo llevaba tanto tiempo sin partir, siendo la más grande. Estos tests son lo
que permitió partirla sin adivinar:

  · el **orden de las fases es el contrato**. Las tareas necesitan proyectos,
    los proyectos necesitan clientes y la organización, las habilidades de
    usuario necesitan el catálogo y los usuarios. Reordenar dos llamadas del
    orquestador dejaría la siembra a medias sin que nada lanzara: las secciones
    que crean datos van dentro de un `if db.query(X).count() == 0`, así que una
    dependencia ausente produce cero filas, no un error;
  · que cada fase sea **idempotente**: `seed()` se ejecuta sobre bases que ya
    pueden tener datos, y ninguna fase debe duplicar;
  · que las fases que devuelven datos los devuelvan de verdad — `org`, `users`,
    `skills` y `clients` fluyen entre fases y un `return` olvidado las dejaría
    en `None`.
"""
from __future__ import annotations

import inspect

import pytest

from app.db.seed_parts import core


# ── El orden de las fases, que es el contrato ─────────────────────────────────

ORDEN_ESPERADO = [
    "_sembrar_ajustes",
    "_sembrar_departamentos",
    "_sembrar_festivos",
    "_sembrar_organizacion",
    "_sembrar_usuarios",
    "_sembrar_catalogo_de_habilidades",
    "_sembrar_habilidades_de_usuario",
    "_sembrar_secuencias_de_numeracion",
    "_sembrar_tipos_de_tarea",
    "_sembrar_configuracion_de_alertas",
    "_sembrar_politica_de_vacaciones",
    "_sembrar_clientes",
    "_sembrar_proyectos",
    "_sembrar_tareas",
    "_sembrar_imputaciones",
    "_sembrar_ausencias",
    "_sembrar_oportunidades",
    "_sembrar_contratos",
    "_sembrar_riesgos",
    "_sembrar_peticiones_de_cambio",
    "_sembrar_entregables",
    "_sembrar_hitos",
]


def test_las_fases_se_llaman_en_el_orden_declarado():
    """Reordenar dos llamadas no lanzaría nada: dejaría filas a cero.

    Las secciones que crean datos van dentro de un
    `if db.query(X).count() == 0`, así que si los proyectos se sembraran antes
    que los clientes, la lista de clientes llegaría vacía, no habría proyectos, y
    la siembra terminaría «bien» con la base medio vacía. Este test lo impide.
    """
    fuente = inspect.getsource(core.seed)
    posiciones = []
    for nombre in ORDEN_ESPERADO:
        i = fuente.find(nombre + "(")
        assert i >= 0, f"{nombre} ya no se llama desde seed()"
        posiciones.append((i, nombre))
    assert posiciones == sorted(posiciones), (
        "el orden de las fases ha cambiado; esperado:\n  "
        + "\n  ".join(ORDEN_ESPERADO)
    )


def test_todas_las_fases_existen_y_son_funciones():
    for nombre in ORDEN_ESPERADO:
        f = getattr(core, nombre, None)
        assert callable(f), f"{nombre} no existe o no es invocable"


def test_ninguna_fase_se_ha_quedado_sin_llamar():
    """El revés del test de orden: una fase extraída y nunca invocada sería
    código muerto, y su parte de la demostración desaparecería en silencio."""
    fuente = inspect.getsource(core.seed)
    definidas = [
        n for n in dir(core)
        if n.startswith("_sembrar_") and callable(getattr(core, n))
    ]
    sin_llamar = [n for n in definidas if (n + "(") not in fuente]
    assert not sin_llamar, f"fases definidas pero nunca llamadas: {sin_llamar}"


# ── Las fases que devuelven datos ─────────────────────────────────────────────

def test_la_organizacion_se_devuelve(db):
    org = core._sembrar_organizacion(db)
    assert org is not None
    assert org.id


def test_los_usuarios_y_la_contrasena_se_devuelven(db):
    """`seed_pwd` se devuelve porque la última sección la vuelve a imprimir al
    terminar: calcularla dos veces daría dos contraseñas distintas y el mensaje
    final no serviría para entrar."""
    org = core._sembrar_organizacion(db)
    users, seed_pwd = core._sembrar_usuarios(db, org)
    assert users, "sin usuarios no hay demostración"
    assert isinstance(seed_pwd, str) and seed_pwd


def test_el_catalogo_de_habilidades_se_devuelve_indexado(db):
    skills = core._sembrar_catalogo_de_habilidades(db)
    assert skills, "el catálogo no puede volver vacío"
    assert all(isinstance(k, str) for k in skills)


def test_los_clientes_se_devuelven(db):
    org = core._sembrar_organizacion(db)
    users, _ = core._sembrar_usuarios(db, org)
    clients = core._sembrar_clientes(db, users)
    assert clients, "sin clientes no hay proyectos"


# ── Idempotencia: `seed()` corre sobre bases que ya tienen datos ──────────────

@pytest.mark.parametrize("fase", [
    "_sembrar_ajustes",
    "_sembrar_departamentos",
    "_sembrar_festivos",
    "_sembrar_secuencias_de_numeracion",
    "_sembrar_tipos_de_tarea",
    "_sembrar_configuracion_de_alertas",
])
def test_las_fases_de_catalogo_son_idempotentes(db, fase):
    """Las de catálogo se ejecutan dos veces y no duplican.

    Importa porque `seed()` no es de un solo uso: se lanza sobre entornos que ya
    tienen datos. Una fase que duplicara dejaría dos departamentos «Backend» o
    dos secuencias de numeración para la misma entidad — y lo segundo rompería
    los números de factura.
    """
    from sqlalchemy import func, select
    from app.db.base import Base

    f = getattr(core, fase)
    f(db)
    db.commit()

    antes = {
        nombre: db.execute(select(func.count()).select_from(t)).scalar()
        for nombre, t in Base.metadata.tables.items()
    }
    f(db)
    db.commit()
    despues = {
        nombre: db.execute(select(func.count()).select_from(t)).scalar()
        for nombre, t in Base.metadata.tables.items()
    }
    crecieron = {k: (antes[k], despues[k]) for k in antes if despues[k] != antes[k]}
    assert not crecieron, f"{fase} duplicó filas: {crecieron}"


def test_la_organizacion_no_se_duplica(db):
    a = core._sembrar_organizacion(db)
    db.commit()
    b = core._sembrar_organizacion(db)
    db.commit()
    assert a.id == b.id, "la segunda pasada creó otra organización"


def test_los_usuarios_no_se_duplican(db):
    from app.models.user import User

    org = core._sembrar_organizacion(db)
    core._sembrar_usuarios(db, org)
    db.commit()
    n1 = db.query(User).count()
    core._sembrar_usuarios(db, org)
    db.commit()
    assert db.query(User).count() == n1


# ── La siembra completa ───────────────────────────────────────────────────────

def test_seed_completo_puebla_las_tablas_esperadas(db, monkeypatch):
    """La red real del refactor: la siembra entera, comparada por tablas.

    No se fijan los recuentos exactos —cambiar un cliente de la demostración es
    legítimo y no debe romper un test— sino que **las tablas que deben quedar
    con filas quedan con filas**. Una fase que dejara de ejecutarse por un
    `return` olvidado o una dependencia mal pasada vaciaría su tabla, y eso sí
    es una regresión.
    """
    from sqlalchemy import func, select
    from app.db.base import Base
    from app.db import session as _session

    # `seed()` abre su propia sesión con `SessionLocal`; se apunta a la del test
    # para que escriba en la base en memoria de este proceso.
    monkeypatch.setattr(_session, "SessionLocal", lambda: db)
    monkeypatch.setattr(core, "SessionLocal", lambda: db, raising=False)

    core.seed()

    TABLAS_CON_DATOS = [
        "users", "clients", "projects", "tasks", "imputations",
        "app_settings", "departments", "holidays", "organizations",
        "skills", "user_skills", "numbering_sequences", "task_types",
    ]
    vacias = []
    for nombre in TABLAS_CON_DATOS:
        t = Base.metadata.tables.get(nombre)
        if t is None:
            continue   # la tabla puede haberse renombrado; eso lo cubre otro test
        if not db.execute(select(func.count()).select_from(t)).scalar():
            vacias.append(nombre)
    assert not vacias, f"la siembra dejó estas tablas vacías: {vacias}"


def test_seed_es_idempotente_de_punta_a_punta(db, monkeypatch):
    """Dos siembras seguidas no deben multiplicar los datos.

    No se exige igualdad exacta —las secciones con `count() == 0` sí son
    estrictamente idempotentes, pero alguna de catálogo podría añadir un valor
    nuevo—: se exige que no se DUPLIQUE, que es el fallo que importa.
    """
    from sqlalchemy import func, select
    from app.db.base import Base
    from app.db import session as _session

    monkeypatch.setattr(_session, "SessionLocal", lambda: db)
    monkeypatch.setattr(core, "SessionLocal", lambda: db, raising=False)

    core.seed()
    primera = {
        n: db.execute(select(func.count()).select_from(t)).scalar()
        for n, t in Base.metadata.tables.items()
    }
    core.seed()
    segunda = {
        n: db.execute(select(func.count()).select_from(t)).scalar()
        for n, t in Base.metadata.tables.items()
    }

    duplicadas = {
        n: (primera[n], segunda[n])
        for n in primera
        if primera[n] and segunda[n] >= primera[n] * 2
    }
    assert not duplicadas, f"la segunda siembra duplicó: {duplicadas}"
