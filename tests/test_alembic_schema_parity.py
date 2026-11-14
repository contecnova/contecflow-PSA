"""Alembic construye el esquema COMPLETO desde cero (auditoría 2026-08, P2-11).

El hallazgo: el esquema se construía por dos caminos y sólo uno estaba completo.

  · BD nueva      → `Base.metadata.create_all()` + `alembic stamp head`
  · BD existente  → `alembic upgrade head`

`stamp head` marca las revisiones como aplicadas SIN ejecutarlas, así que la
cadena de Alembic no se ejercitó nunca de principio a fin. Al probarla sobre una
base vacía producía 374 tablas frente a las 392 de los modelos: faltaban 19,
entre ellas expenses, email_templates, automation_rules,
revenue_recognition_entries, gdpr_requests y webhook_triggers. Un despliegue que
hubiese pasado por Alembic se quedaba sin esas funcionalidades.

Este test es el que faltaba: levanta una base vacía, corre `alembic upgrade head`
de verdad y compara el resultado con los modelos. Es lento (crea el esquema
entero), así que va marcado como `slow`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

REPO = Path(__file__).resolve().parents[1]


# Modelos que existen SOLO para tests. Se registran en `Base.metadata` al
# importarse su módulo, así que aparecen aquí aunque ninguna revisión de Alembic
# deba crearlos — y no debe: no son parte del producto.
#
# Detectado al correr la suite con `-n auto`: cada worker de xdist importa todos
# los módulos de test, así que `tests/test_tenant_filter_fail_closed.py` metía sus
# dos dobles en el metadata y este test los reclamaba como tablas que faltan. En
# serie, con un subconjunto de ficheros, no se veía. El prefijo es la convención
# que los identifica.
PREFIJO_MODELOS_DE_TEST = "_test_"


def _modelos() -> set[str]:
    from app.db.base import Base
    import app.models  # noqa: F401 — registra todos los modelos

    return {
        nombre
        for nombre in Base.metadata.tables
        if not nombre.startswith(PREFIJO_MODELOS_DE_TEST)
    }


@pytest.mark.slow
def test_alembic_upgrade_head_crea_todas_las_tablas_de_los_modelos():
    """El test que nadie había escrito, y por eso el hueco duró 88 revisiones."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "parity.db"
        url = f"sqlite:///{db_path.as_posix()}"

        env = dict(os.environ)
        env["DATABASE_URL"] = url
        # La configuración valida SECRET_KEY por longitud y entropía al importar.
        env.setdefault("SECRET_KEY", "parity-test-secret-2f9c41ab7de6035849bc12ef")
        env.setdefault("CLIENT_PORTAL_SECRET", "parity-test-portal-8a13cd52be97640f2e1b")
        env["TESTING"] = "1"

        proc = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO, env=env, capture_output=True, text=True, timeout=900,
        )
        assert proc.returncode == 0, (
            "`alembic upgrade head` falló sobre una base vacía.\n"
            f"stdout:\n{proc.stdout[-3000:]}\nstderr:\n{proc.stderr[-3000:]}"
        )

        # dispose() antes de salir del contexto: en Windows el engine mantiene
        # el fichero abierto y el borrado del directorio temporal falla con
        # PermissionError.
        eng = create_engine(url)
        try:
            creadas = set(inspect(eng).get_table_names())
        finally:
            eng.dispose()

    esperadas = _modelos()
    faltan = sorted(esperadas - creadas)
    assert not faltan, (
        f"`alembic upgrade head` no crea {len(faltan)} tablas que los modelos "
        f"esperan: {faltan}\n\n"
        "Cada modelo nuevo necesita su revisión. Si esto falla tras añadir "
        "modelos, genera la revisión correspondiente — no lo resuelvas con "
        "create_all, que es lo que ocultó este hueco durante 88 revisiones."
    )


def test_hay_una_sola_cabeza_de_migracion():
    """Dos cabezas significan que dos ramas divergieron sin fusionarse.

    `alembic upgrade head` fallaría con "Multiple head revisions are present".
    """
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=REPO, capture_output=True, text=True, timeout=180,
        env={**os.environ, "TESTING": "1"},
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    cabezas = [l for l in proc.stdout.splitlines() if "(head)" in l]
    assert len(cabezas) == 1, f"se esperaba una sola cabeza, hay {len(cabezas)}: {cabezas}"


def test_la_revision_del_hueco_declara_las_19_tablas():
    """Fija el inventario del hallazgo.

    Si alguien retira una de las 19 del dominio, la revisión lo detecta al
    ejecutarse; este test lo detecta antes.
    """
    import importlib.util

    ruta = REPO / "alembic" / "versions" / "089_schema_gap_missing_tables.py"
    assert ruta.exists(), "la revisión que cierra el hueco de esquema ha desaparecido"

    spec = importlib.util.spec_from_file_location("rev089", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert len(mod.MISSING_TABLES) == 19, (
        f"la revisión declara {len(mod.MISSING_TABLES)} tablas, se esperaban 19"
    )
    # Todas deben seguir existiendo como modelo.
    modelos = _modelos()
    # Retiradas del dominio por la revision 156 (un solo motor de ingresos); la
    # 089 las omite si ya no son modelo (auditoria 2026-11).
    retiradas = {"revenue_recognition_entries", "revenue_recognition_rules"}
    huerfanas = [n for n in mod.MISSING_TABLES if n not in modelos and n not in retiradas]
    assert not huerfanas, (
        f"estas tablas de la revisión ya no tienen modelo: {huerfanas}"
    )


def test_no_queda_create_all_en_el_arranque_de_produccion():
    """`create_all` es lo que ocultó el hueco. No debe volver al camino normal.

    Se permite en los seeds y en los tests (donde el esquema es desechable), pero
    no en el arranque de la aplicación ni en el flujo de despliegue.
    """
    prohibidos = [
        REPO / "app" / "main.py",
    ]
    for f in prohibidos:
        if not f.exists():
            continue
        assert "create_all" not in f.read_text(encoding="utf-8"), (
            f"{f.relative_to(REPO)} llama a create_all: el esquema debe venir de "
            "Alembic para que las revisiones se ejerciten de verdad"
        )


def test_la_exclusion_de_modelos_de_test_no_tapa_modelos_reales():
    """La exclusión por prefijo no puede convertirse en una vía de escape.

    `_modelos()` descarta las tablas que empiezan por `_test_` porque son dobles
    definidos en los propios tests. Si alguien nombrase así un modelo del
    producto, quedaría fuera del test de paridad y su revisión de Alembic podría
    faltar sin que nada avisase — que es exactamente el fallo que este módulo
    existe para impedir.
    """
    from app.db.base import Base
    import app.models  # noqa: F401

    del Base  # sólo se necesitaba para poblar el metadata

    import importlib
    import pkgutil

    reales = set()
    for info in pkgutil.walk_packages(app.models.__path__, "app.models."):
        modulo = importlib.import_module(info.name)
        for obj in vars(modulo).values():
            tabla = getattr(obj, "__tablename__", None)
            if isinstance(tabla, str):
                reales.add(tabla)

    culpables = sorted(t for t in reales if t.startswith(PREFIJO_MODELOS_DE_TEST))
    assert not culpables, (
        f"hay modelos del producto con el prefijo reservado "
        f"{PREFIJO_MODELOS_DE_TEST!r}, así que el test de paridad los ignora: "
        f"{culpables}"
    )


# ── La misma cadena sobre PostgreSQL ─────────────────────────────────────────
# El test de arriba corre sobre SQLite, que no valida claves ajenas al crear
# tablas, no limita la longitud de VARCHAR, acepta 1/0 como booleanos y no
# tiene tipos enum. Por eso la cadena estuvo rota en Postgres sin que nadie lo
# viera: el setup se paraba en la 001 sobre una base vacía (2026-11).
#
# Segunda auditoría 2026-11 (#5): la comparación vive en
# `scripts/paridad_postgres.py`, que también se ejecuta a mano contra una base ya
# migrada (~35 s, sin volver a migrar). Antes se admitía CUALQUIER `remove_index`
# y no se comparaban los `server_default`; ahora el ruido se admite uno a uno y
# con su motivo (ver el docstring del script). Coste medido: ~2 min de
# `alembic upgrade head` + ~35 s de comparación sobre PostgreSQL 16 local.


def _servidor_postgres() -> str | None:
    url = os.environ.get("PARITY_POSTGRES_URL")
    if not url:
        env = REPO / ".env"
        if env.exists():
            for linea in env.read_text(encoding="utf-8").splitlines():
                if linea.startswith("DATABASE_URL="):
                    url = linea.split("=", 1)[1].strip()
    if not url or not url.startswith("postgresql"):
        return None
    return url


def _paridad():
    import importlib.util

    spec = importlib.util.spec_from_file_location("paridad_postgres", REPO / "scripts" / "paridad_postgres.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.slow
def test_alembic_upgrade_head_sobre_postgres_coincide_con_los_modelos():
    servidor = _servidor_postgres()
    if servidor is None:
        pytest.skip("sin Postgres: ni PARITY_POSTGRES_URL ni un DATABASE_URL postgresql en .env")

    paridad = _paridad()
    try:
        url, borrar = paridad.migrar_base_nueva(servidor)
    except RuntimeError as exc:
        pytest.fail(str(exc))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres configurado pero no responde: {exc.__class__.__name__}")
    try:
        resultado = paridad.comparar(url)
    finally:
        borrar()

    assert not resultado["reales"] and not resultado["enums"], paridad.informe(resultado)


def test_el_ruido_de_paridad_no_admite_un_default_distinto():
    """El `server_default` de relleno solo es ruido si vale lo mismo que el
    `default=` del modelo. Sin base: se construye la diferencia a mano."""
    from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, text
    from sqlalchemy.schema import DefaultClause

    paridad = _paridad()
    md = MetaData()
    Table("t", md, Column("id", Integer, primary_key=True),
          Column("activo", Boolean, default=True), Column("estado", String(10), default="pending"))

    def diff(col, en_bd):
        return [("modify_default", None, "t", col, {}, DefaultClause(text(en_bd)), None)]

    assert paridad._es_ruido(diff("activo", "true"), md)
    assert paridad._es_ruido(diff("estado", "'pending'::character varying"), md)
    assert paridad._es_ruido(diff("activo", "false"), md) is None
    assert paridad._es_ruido(diff("estado", "'done'::character varying"), md) is None
