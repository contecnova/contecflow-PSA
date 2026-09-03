"""SCIM: qué campos aplica un PUT y qué campos aplica un PATCH.

Auditoría 2026-08 (P3-18). `update_scim_user` era complejidad 16: dos bloques
—PUT y PATCH— con sus propias cadenas de `if` sobre los campos.

## La asimetría que apareció al ponerlos en tabla

**PUT y PATCH no cubren los mismos campos.** PUT aplica correo, nombre, roles y
`externalId`; PATCH sólo `active`, `displayName` y `userName`. Un proveedor de
identidad que mande un PATCH cambiando el correo o el rol de alguien recibe
**200 y no pasa nada**.

No es un fallo del refactor —era así— y el RFC 7644 permite ignorar rutas no
soportadas, así que no se ha cambiado el comportamiento. Lo que no se podía era
no saberlo: estos tests lo fijan en las dos direcciones, así que el día que
alguien añada una ruta a PATCH tendrá que actualizarlos y verá la tabla completa.

Y fijan una cosa que sí importa de verdad: que `is_active` y `status` se muevan
**siempre juntos**. `is_active` es lo que mira la autenticación y `status` lo que
se muestra; desalineados producen un usuario que no puede entrar pero aparece
como activo — o al revés, que es peor.
"""
from __future__ import annotations

import pytest

from app.models.user import UserStatus
from app.services.scim_service import (
    RUTAS_SOPORTADAS_EN_PATCH,
    update_scim_user,
)


class _Usuario:
    """Un usuario mínimo: `update_scim_user` sólo asigna atributos."""

    def __init__(self, **kw):
        self.username = "original"
        self.email = "original@x.com"
        self.full_name = "Nombre Original"
        self.first_name = "Nombre"
        self.last_name = "Original"
        self.role = "employee"
        self.is_active = True
        self.status = UserStatus.active
        self.scim_external_id = "ext-original"
        self.scim_last_synced_at = None
        self.__dict__.update(kw)


# ── PUT: reemplazo, campo a campo ────────────────────────────────────────────

def test_put_aplica_el_nombre_de_usuario():
    u = _Usuario()
    update_scim_user(u, {"userName": "nuevo"}, "PUT")
    assert u.username == "nuevo"


def test_put_aplica_el_primer_correo_de_la_lista():
    """SCIM manda los correos como lista de objetos. Se toma el primero."""
    u = _Usuario()
    update_scim_user(u, {"emails": [{"value": "a@x.com"}, {"value": "b@x.com"}]}, "PUT")
    assert u.email == "a@x.com"


@pytest.mark.parametrize("emails", [[], [{}], [{"value": ""}], "no soy lista", None])
def test_un_correo_mal_formado_no_borra_el_que_habia(emails):
    """El proveedor de identidad manda lo que le parece. Un correo ausente o
    malformado deja el que ya estaba en vez de vaciarlo."""
    u = _Usuario()
    update_scim_user(u, {"emails": emails}, "PUT")
    assert u.email == "original@x.com"


def test_put_aplica_los_tres_campos_de_nombre():
    u = _Usuario()
    update_scim_user(u, {"name": {
        "formatted": "Ana Torres", "givenName": "Ana", "familyName": "Torres",
    }}, "PUT")
    assert u.full_name == "Ana Torres"
    assert u.first_name == "Ana"
    assert u.last_name == "Torres"


def test_un_apellido_vacio_si_se_puede_borrar():
    """`is not None` y no una comprobación de verdad: un apellido vacío es un
    borrado legítimo, y con `if valor:` no se podría vaciar nunca."""
    u = _Usuario()
    update_scim_user(u, {"name": {"givenName": "", "familyName": ""}}, "PUT")
    assert u.first_name == ""
    assert u.last_name == ""


def test_un_nombre_ausente_no_toca_nada():
    u = _Usuario()
    update_scim_user(u, {"name": {}}, "PUT")
    assert u.full_name == "Nombre Original"
    assert u.first_name == "Nombre"


def test_put_aplica_el_primer_rol():
    u = _Usuario()
    update_scim_user(u, {"roles": [{"value": "admin"}]}, "PUT")
    assert str(u.role).endswith("admin")


def test_put_conserva_el_external_id_si_no_viene():
    """El `externalId` es la clave con la que el proveedor identifica al usuario:
    perderlo rompe la sincronización siguiente."""
    u = _Usuario()
    update_scim_user(u, {"userName": "x"}, "PUT")
    assert u.scim_external_id == "ext-original"

    update_scim_user(u, {"externalId": "ext-nuevo"}, "PUT")
    assert u.scim_external_id == "ext-nuevo"


def test_un_put_parcial_no_borra_lo_que_no_menciona():
    """Más laxo que el RFC a propósito: un PUT debería reemplazar el recurso
    entero, pero los proveedores mandan PUT incompletos con frecuencia y vaciar
    el nombre de alguien porque su IdP no lo envió sería peor que ignorarlo."""
    u = _Usuario()
    update_scim_user(u, {"userName": "solo-esto"}, "PUT")
    assert u.username == "solo-esto"
    assert u.email == "original@x.com"
    assert u.full_name == "Nombre Original"
    assert u.role == "employee"


# ── El estado: los dos campos van siempre juntos ─────────────────────────────

@pytest.mark.parametrize("activo", [True, False])
def test_put_mueve_is_active_y_status_a_la_vez(activo):
    """`is_active` es lo que mira la autenticación y `status` lo que se muestra.
    Desalineados producen un usuario que no puede entrar pero aparece activo."""
    u = _Usuario()
    update_scim_user(u, {"active": activo}, "PUT")
    assert u.is_active is activo
    assert u.status == (UserStatus.active if activo else UserStatus.inactive)


def test_patch_replace_de_active_mueve_los_dos():
    u = _Usuario()
    update_scim_user(u, {"Operations": [
        {"op": "replace", "path": "active", "value": False},
    ]}, "PATCH")
    assert u.is_active is False
    assert u.status == UserStatus.inactive


def test_patch_remove_de_active_desactiva():
    """`remove` sobre `active` es lo que mandan algunos proveedores al dar de
    baja a alguien, en vez de un `replace` a false."""
    u = _Usuario()
    update_scim_user(u, {"Operations": [
        {"op": "remove", "path": "active"},
    ]}, "PATCH")
    assert u.is_active is False
    assert u.status == UserStatus.inactive


def test_active_a_false_no_se_confunde_con_ausente():
    """El valor `false` es falso pero significativo: si se comprobara con `if
    value:` una desactivación se ignoraría y la persona seguiría entrando."""
    u = _Usuario()
    update_scim_user(u, {"Operations": [
        {"op": "replace", "path": "active", "value": False},
    ]}, "PATCH")
    assert u.is_active is False


# ── PATCH: rutas, y las que no cubre ─────────────────────────────────────────

@pytest.mark.parametrize("ruta,valor,campo,esperado", [
    ("displayName", "Ana Torres", "full_name", "Ana Torres"),
    ("userName", "atorres", "username", "atorres"),
])
def test_las_rutas_que_patch_si_aplica(ruta, valor, campo, esperado):
    u = _Usuario()
    update_scim_user(u, {"Operations": [
        {"op": "replace", "path": ruta, "value": valor},
    ]}, "PATCH")
    assert getattr(u, campo) == esperado


def test_la_ruta_no_distingue_mayusculas():
    """El proveedor manda `displayName`, `DisplayName` o `displayname` según le
    parece, y las tres significan lo mismo."""
    for ruta in ("displayName", "DISPLAYNAME", "displayname"):
        u = _Usuario()
        update_scim_user(u, {"Operations": [
            {"op": "replace", "path": ruta, "value": "X"},
        ]}, "PATCH")
        assert u.full_name == "X", ruta


def test_add_se_trata_igual_que_replace():
    """SCIM permite las dos para un atributo simple y los proveedores usan las
    dos indistintamente."""
    u = _Usuario()
    update_scim_user(u, {"Operations": [
        {"op": "add", "path": "userName", "value": "conadd"},
    ]}, "PATCH")
    assert u.username == "conadd"


@pytest.mark.parametrize("ruta", ["emails", "name.givenName", "roles", "externalId"])
def test_LA_ASIMETRIA_patch_ignora_campos_que_put_si_aplica(ruta):
    """El hallazgo, fijado.

    PUT aplica correo, nombre, roles y `externalId`; PATCH no. Un proveedor de
    identidad que mande un PATCH cambiando el correo de alguien recibe **200 y
    no pasa nada**.

    El RFC 7644 permite ignorar rutas no soportadas, así que no se ha cambiado
    el comportamiento — pero queda escrito. El día que se añada una de estas
    rutas a PATCH, este test falla y obliga a revisar la tabla completa.
    """
    u = _Usuario()
    antes = (u.email, u.first_name, u.role, u.scim_external_id)
    update_scim_user(u, {"Operations": [
        {"op": "replace", "path": ruta, "value": "cambiado@x.com"},
    ]}, "PATCH")
    assert (u.email, u.first_name, u.role, u.scim_external_id) == antes, (
        f"PATCH ya aplica '{ruta}': actualiza este test y la tabla de la cabecera"
    )


def test_las_rutas_soportadas_en_patch_son_exactamente_tres():
    assert RUTAS_SOPORTADAS_EN_PATCH == {"active", "displayname", "username"}


def test_una_operacion_desconocida_no_hace_nada():
    u = _Usuario()
    update_scim_user(u, {"Operations": [
        {"op": "inventada", "path": "username", "value": "no"},
    ]}, "PATCH")
    assert u.username == "original"


@pytest.mark.parametrize("payload", [{}, {"Operations": None}, {"Operations": []}])
def test_un_patch_vacio_no_revienta(payload):
    u = _Usuario()
    update_scim_user(u, payload, "PATCH")
    assert u.username == "original"


def test_un_valor_vacio_no_borra_el_nombre():
    """`displayName` y `userName` exigen valor con contenido: un proveedor que
    manda cadena vacía por error no deja al usuario sin nombre."""
    u = _Usuario()
    update_scim_user(u, {"Operations": [
        {"op": "replace", "path": "displayname", "value": ""},
    ]}, "PATCH")
    assert u.full_name == "Nombre Original"


# ── La marca de sincronización ───────────────────────────────────────────────

@pytest.mark.parametrize("metodo", ["PUT", "PATCH", "METODO_RARO"])
def test_siempre_se_marca_la_sincronizacion(metodo):
    """Incluso con un método que no se reconoce: el proveedor ha contactado, y
    eso es lo que este campo registra. Sirve para detectar un IdP que dejó de
    sincronizar."""
    u = _Usuario()
    update_scim_user(u, {}, metodo)
    assert u.scim_last_synced_at is not None


def test_un_metodo_desconocido_no_toca_ningun_campo():
    u = _Usuario()
    update_scim_user(u, {"userName": "no-deberia"}, "DELETE")
    assert u.username == "original"
