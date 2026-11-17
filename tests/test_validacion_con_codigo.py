"""Errores de validacion con codigo traducible (17-11-2026).

Un 422 de `RequestValidationError` sale como `{detail (castellano), code:
"validacion", params: {errores: [{campo, tipo, origen, ...}]}}` con tipos
normalizados, sin devolver nunca el valor enviado.
"""
from app.core import codigos_de_error as cde
from app.core.validacion import TIPOS, cuerpo, normalizar_error
from tests.conftest import auth


def _errores(r):
    assert r.status_code == 422, r.text
    d = r.json()
    assert d["code"] == "validacion" and isinstance(d["detail"], str)
    return {(e["campo"], e["tipo"]): e for e in d["params"]["errores"]}


def test_obligatorio_en_el_cuerpo(client, admin_token):
    r = client.post("/api/v1/sd/announcements", headers=auth(admin_token), json={"title": "Sin cuerpo"})
    errores = _errores(r)
    assert ("body", "obligatorio") in errores
    assert errores[("body", "obligatorio")]["origen"] == "body"
    assert r.json()["detail"].startswith("Revisa los datos: body (obligatorio)")


def test_limites_numericos_en_la_query(client, admin_token):
    r = client.get("/api/v1/analytics/olap/margin-evolution", headers=auth(admin_token), params={"months": 0})
    e = _errores(r)[("months", "minimo")]
    assert e == {"campo": "months", "tipo": "minimo", "origen": "query", "min": 1}
    r = client.get("/api/v1/analytics/olap/margin-evolution", headers=auth(admin_token), params={"months": "x"})
    assert ("months", "entero") in _errores(r)


def test_no_devuelve_el_valor_enviado(client):
    secreto = "ClaveSecretaQueNoDebeVolver"
    # Contraseña demasiado corta para el esquema del portal: 422 de validacion.
    r = client.post("/api/v1/portal/auth/login", json={"email": "no-es-un-email", "password": secreto[:3]})
    assert r.status_code == 422
    assert "input" not in r.text and "no-es-un-email" not in r.text
    tipos = {e["tipo"] for e in r.json()["params"]["errores"]}
    assert tipos <= set(TIPOS)


def test_normalizacion_de_tipos_de_pydantic():
    assert normalizar_error({"type": "string_too_long", "loc": ("body", "lineas", 0, "nombre"),
                             "ctx": {"max_length": 255}}) == \
        {"campo": "lineas.0.nombre", "tipo": "longitud_maxima", "origen": "body", "max": 255}
    e = normalizar_error({"type": "literal_error", "loc": ("query", "por"), "ctx": {"expected": "'proyecto' or 'cliente'"}})
    assert e["tipo"] == "valor_no_permitido" and e["permitidos"] == ["proyecto", "cliente"]
    e = normalizar_error({"type": "enum", "loc": ("body", "estado"), "ctx": {"expected": "'a', 'b' or 'c'"}})
    assert e["permitidos"] == ["a", "b", "c"]
    assert normalizar_error({"type": "algo_nuevo", "loc": ("body",)})["tipo"] == "no_valido"
    assert normalizar_error({"type": "json_invalid", "loc": ("body", 12)})["tipo"] == "json_invalido"
    # Una union da un error por rama del mismo campo: se deja uno.
    c = cuerpo([{"type": "int_parsing", "loc": ("query", "n")}, {"type": "int_parsing", "loc": ("query", "n")}])
    assert len(c["params"]["errores"]) == 1


def test_codigo_en_el_catalogo_del_portal():
    assert "validacion" in cde.MENSAJES
