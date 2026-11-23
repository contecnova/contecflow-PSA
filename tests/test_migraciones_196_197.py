"""Migraciones 196 (auditoría 22-11-2026) y 197 (dinero en Numeric), 23-11-2026.

- Las listas de las migraciones cuadran con los modelos: `ondelete` de las
  claves a `users.id`, tipos de las columnas de dinero y tablas retiradas.
- El borrado definitivo de un usuario con historial protegido (RESTRICT) lo
  anonimiza con la supresión RGPD en vez de borrarlo; sin historial, lo borra.

La migración en sí (subida, bajada y conteo de filas) se ejecuta de principio a
fin en `test_alembic_schema_parity.py` (base vacía) y se midió sobre una copia
de la base local (docs/DESPLIEGUE.md, B.2).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _migracion(nombre: str):
    ruta = REPO / "alembic" / "versions" / f"{nombre}.py"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _metadata():
    import app.models  # noqa: F401
    from app.db.base import Base
    return Base.metadata


def test_196_ondelete_de_los_modelos_coincide_con_la_migracion():
    md = _metadata()
    mig = _migracion("196_auditoria_2026_11_22")
    assert len(mig.CLAVES_A_USERS) == 171
    for tabla, columna, borrar in mig.CLAVES_A_USERS:
        fks = [f for f in md.tables[tabla].c[columna].foreign_keys if f.column.table.name == "users"]
        assert fks and fks[0].ondelete == borrar, (tabla, columna, fks and fks[0].ondelete)
        if borrar == "SET NULL":
            assert md.tables[tabla].c[columna].nullable, (tabla, columna)


def test_196_ninguna_clave_a_users_se_queda_sin_ondelete():
    md = _metadata()
    sin = [(t.name, c.name) for t in md.sorted_tables for c in t.columns
           for f in c.foreign_keys if f.column.table.name == "users" and not f.ondelete]
    assert not sin, sin


def test_196_tablas_retiradas_sin_modelo():
    md = _metadata()
    mig = _migracion("196_auditoria_2026_11_22")
    assert not set(mig.TABLAS_RETIRADAS) & set(md.tables)


def test_196_columnas_nuevas_en_los_modelos():
    md = _metadata()
    assert md.tables["collaboration_audit_events"].c["hash_version"].server_default.arg == "v1"
    assert "signed_pdf_sha256" in md.tables["client_documents"].c
    assert "secret_token_hash" in md.tables["collaboration_webhooks"].c
    idx = {i.name: i for i in md.tables["automation_events"].indexes}
    assert idx["uq_automation_events_org_idempotency"].unique


def test_197_tipos_de_dinero_de_los_modelos_coinciden_con_la_migracion():
    import sqlalchemy as sa

    md = _metadata()
    mig = _migracion("197_dinero_numeric")
    assert len(mig.COLUMNAS) == 79
    for tabla, columna, escala, nula in mig.COLUMNAS:
        tipo = md.tables[tabla].c[columna].type
        assert isinstance(tipo, sa.Numeric) and not isinstance(tipo, sa.Float), (tabla, columna, tipo)
        assert (tipo.precision, tipo.scale) == (18, escala), (tabla, columna, tipo)
        assert md.tables[tabla].c[columna].nullable == nula, (tabla, columna)
        # Python sigue en float: sin TypeError float*Decimal en el código existente.
        assert tipo.asdecimal is False, (tabla, columna)


def test_borrar_usuario_con_historial_lo_anonimiza(db):
    from app.models.performance import DevelopmentPlan
    from app.models.user import User
    from app.services.user_service import delete_user_record, historial_que_retiene

    persona = db.query(User).filter(User.id == "dev-test-id").one()
    db.add(DevelopmentPlan(subject_id=persona.id, title="Plan"))
    db.commit()
    assert historial_que_retiene(db, persona) == {"development_plans.subject_id": 1}

    resultado = delete_user_record(persona, db)

    assert resultado["modo"] == "anonimizado"
    db.expire_all()
    fila = db.query(User).filter(User.id == "dev-test-id").one()
    assert fila.is_active is False and fila.full_name == "[ERASED]"
    assert fila.email.endswith("@erased.invalid") and "dev@" not in fila.email
    assert db.query(DevelopmentPlan).filter(DevelopmentPlan.subject_id == "dev-test-id").count() == 1


def test_borrar_usuario_sin_historial_lo_borra(db):
    from app.models.user import User
    from app.services.user_service import delete_user_record

    persona = db.query(User).filter(User.id == "dev-test-id").one()
    assert delete_user_record(persona, db)["modo"] == "borrado"
    assert db.query(User).filter(User.id == "dev-test-id").first() is None

