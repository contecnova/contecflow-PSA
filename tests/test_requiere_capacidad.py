"""Guarda por capacidad `requiere_capacidad("x")` (19-11-2026).

`app.core.deps.requiere_capacidad` hace que la API decida con la misma matriz
de permisos que la pantalla (`app/core/capacidades.py`). Se comprueba:

- una capacidad que no está en el catálogo no se puede escribir (KeyError al
  construir la guarda, es decir, al importar el router);
- el superadmin pasa siempre, incluso con la capacidad que no tiene nadie;
- un rol base sin la capacidad recibe 403 con código `capacidad_requerida`;
- un rol personalizado que cierra el módulo de la capacidad también recibe
  403 (la capacidad desaparece, como en la pantalla);
- una instancia por capacidad, con la capacidad legible para los barridos.
"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.core.capacidades import CAPACIDADES
from app.core.deps import RequiereCapacidad, requiere_capacidad
from app.models.advanced_config import CustomRole
from app.models.user import User, UserRole, UserStatus
from tests.conftest import HASH_DE_PRUEBA, auth


def _usuario(db, username: str) -> User:
    return db.query(User).filter(User.username == username).first()


# ── Construcción ─────────────────────────────────────────────────────────────

def test_capacidad_desconocida_es_keyerror():
    with pytest.raises(KeyError):
        requiere_capacidad("no.existe")
    with pytest.raises(KeyError):
        RequiereCapacidad("org.administra")  # mal escrita


def test_una_instancia_por_capacidad_y_legible():
    guarda = requiere_capacidad("costes.config")
    assert guarda is requiere_capacidad("costes.config")
    assert isinstance(guarda, RequiereCapacidad)
    assert guarda.capacidad == "costes.config"
    assert guarda is not requiere_capacidad("personas.config")


# ── Decisión ─────────────────────────────────────────────────────────────────

def test_el_superadmin_pasa_siempre(db):
    sa = User(id="sa-requiere-capacidad", username="sa_requiere_capacidad", email="sa-rc@contecflow.test",
              full_name="Superadmin", role=UserRole.admin, status=UserStatus.active, is_active=True,
              is_superadmin=True, organization_id="1", hashed_password=HASH_DE_PRUEBA,
              weekly_capacity_hours=40.0, currency="EUR")
    db.add(sa)
    db.commit()
    # `plataforma.empresas` no la tiene ningún rol base.
    assert not CAPACIDADES["plataforma.empresas"].roles
    assert requiere_capacidad("plataforma.empresas")(current_user=sa, db=db) is sa
    assert requiere_capacidad("org.administrar")(current_user=sa, db=db) is sa


def test_rol_con_la_capacidad_pasa(db):
    admin = _usuario(db, "admin")
    assert requiere_capacidad("org.administrar")(current_user=admin, db=db) is admin
    hr = _usuario(db, "hr_test")
    assert requiere_capacidad("costes.config")(current_user=hr, db=db) is hr


def test_rol_sin_la_capacidad_recibe_403(db):
    dev = _usuario(db, "dev_test")
    assert "employee" not in CAPACIDADES["org.administrar"].roles
    with pytest.raises(HTTPException) as e:
        requiere_capacidad("org.administrar")(current_user=dev, db=db)
    assert e.value.status_code == 403
    assert e.value.code == "capacidad_requerida"
    assert e.value.params == {"capacidad": "org.administrar"}

    pm = _usuario(db, "pm_test")
    assert "pm" not in CAPACIDADES["costes.config"].roles
    with pytest.raises(HTTPException) as e:
        requiere_capacidad("costes.config")(current_user=pm, db=db)
    assert e.value.status_code == 403


def test_rol_personalizado_con_modulo_cerrado_recibe_403(db):
    """RRHH tiene `competencias.gestionar` (módulo `skills`) hasta que su rol lo cierra."""
    hr = _usuario(db, "hr_test")
    guarda = requiere_capacidad("competencias.gestionar")
    assert CAPACIDADES["competencias.gestionar"].modulo == "skills"
    assert guarda(current_user=hr, db=db) is hr

    rol = CustomRole(name="RRHH sin competencias", organization_id=hr.organization_id, is_system=False,
                     is_active=True, module_access=json.dumps({"skills": False}))
    db.add(rol)
    db.commit()
    hr.custom_role_id = rol.id
    db.commit()

    with pytest.raises(HTTPException) as e:
        guarda(current_user=hr, db=db)
    assert e.value.status_code == 403
    assert e.value.code == "capacidad_requerida"
    # Una capacidad sin módulo no la toca el rol personalizado.
    assert CAPACIDADES["costes.ver"].modulo is None
    assert requiere_capacidad("costes.ver")(current_user=hr, db=db) is hr


# ── Por HTTP, sobre una ruta migrada ─────────────────────────────────────────

def test_por_http_ruta_de_ajustes(client, admin_token, dev_token, superadmin_token):
    """`GET /settings/setup-checklist` lleva `requiere_capacidad("org.administrar")`."""
    ruta = "/api/v1/settings/setup-checklist"
    r = client.get(ruta, headers=auth(dev_token))
    assert r.status_code == 403
    assert r.json().get("code") == "capacidad_requerida"
    assert r.json().get("params") == {"capacidad": "org.administrar"}
    assert client.get(ruta, headers=auth(admin_token)).status_code != 403
    assert client.get(ruta, headers=auth(superadmin_token)).status_code != 403
