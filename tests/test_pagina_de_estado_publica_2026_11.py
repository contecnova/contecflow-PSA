"""Página de estado pública y widget para webs de clientes (revisión 2026-11).

Medido antes: la página llevaba su JavaScript en línea y la propia CSP de la API
lo bloqueaba; leía el estado fuera del sobre `data`; el widget salía con
`Cross-Origin-Resource-Policy: same-origin` (la web del cliente no podía
cargarlo) y pedía la API al dominio del cliente. Se midió en el navegador:
página y widget desde otro origen pintan los componentes, escapados.
"""
from __future__ import annotations

import re

from app.models.mfa import Organization
from app.models.service_desk import StatusPageComponent


def _org(db):
    org = db.query(Organization).first()
    db.add(StatusPageComponent(name="API <b>pública</b>", status="operational", group_name="Plataforma",
                               is_public=True, organization_id=org.id))
    db.commit()
    return org


def test_EL_HALLAZGO_la_pagina_no_lleva_codigo_en_linea_y_la_csp_lo_admite(client, db):
    org = _org(db)
    r = client.get(f"/status?org={org.slug}")
    assert r.status_code == 200
    assert not re.search(r"<script>(?!\s*</script>)", r.text)               # nada en línea
    assert '<script src="/status/page.js"></script>' in r.text
    assert "script-src 'self'" in r.headers["content-security-policy"]
    js = client.get("/status/page.js")
    assert js.status_code == 200 and "cuerpo.data || cuerpo" in js.text   # lee dentro del sobre


def test_EL_HALLAZGO_el_widget_se_puede_cargar_desde_otro_origen(client):
    r = client.get("/status/embed.js")
    assert r.headers["cross-origin-resource-policy"] == "cross-origin"
    assert "new URL(script.src)).origin" in r.text                        # la API es la suya, no la del cliente
    assert client.get("/status/page.js").headers["cross-origin-resource-policy"] == "same-origin"


def test_los_datos_publicos_se_leen_desde_cualquier_origen_y_dicen_el_idioma(client, db):
    org = _org(db)
    r = client.get(f"/api/v1/sd/status-page?org={org.slug}", headers={"Origin": "https://web-del-cliente.example"})
    assert r.headers["access-control-allow-origin"] == "*"
    d = r.json()["data"]
    assert d["idioma"] in {"es", "en", "zh"} and d["groups"]["Plataforma"][0]["name"] == "API <b>pública</b>"


def test_el_widget_duplicado_ya_no_existe(client):
    assert client.get("/api/v1/sd/status-page/embed.js").status_code in (404, 405)
