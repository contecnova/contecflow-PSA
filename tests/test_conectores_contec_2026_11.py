"""Conectores con contecmind y contecintelligence (revisión 2026-11).

Sin los productos de verdad: dos dobles que siguen el contrato medido en su
OpenAPI el 05-11-2026 (rutas, cuerpos, canje con rol y alcances, escrituras
que exigen el rol alto). Se comprueba lo que contecflow manda y lo que hace
con cada respuesta: el canje con la identidad de quien llama, el rol rebajado,
la carpeta de cada ficha, el control de acceso de la ficha, los fallos con
nombre y el registro de cada llamada.
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.models.conectores import CarpetaDocumental, ConectorLlamada, EnlaceDocumental
from app.models.service_desk.tickets import Ticket
from app.services import integration_credentials_service as creds
from app.services import settings_service
from app.services.conectores import anfitrion
from tests.conftest import auth

BASE_CM = "https://cm.test"
BASE_CI = "https://ci.test"


class _Doble:
    """contecmind y contecintelligence en memoria, con su protocolo de aplicación anfitriona."""

    def __init__(self):
        self.llamadas: list[tuple[str, str, dict]] = []
        self.tenants = {"1"}
        self.caido = False
        self.no_listo = False
        self.docs: dict[str, dict] = {"d-vpn": {"id": "d-vpn", "title": "Procedimiento VPN", "mime_type": "application/pdf",
                                                "size_bytes": 1200, "status": "indexed"}}
        self.carpetas: dict[str, dict] = {}

    # tokens: «u|rol|alcance,alcance»
    @staticmethod
    def _quien(req) -> tuple[str, set]:
        tok = req.headers.get("authorization", "").removeprefix("Bearer ")
        if not tok.startswith("u|"):
            return "", set()
        _, rol, alc = tok.split("|")
        return rol, set(alc.split(","))

    def handler(self, req: httpx.Request) -> httpx.Response:
        if self.caido:
            raise httpx.ConnectError("caído", request=req)
        ruta = req.url.path
        cuerpo = {}
        if req.headers.get("content-type", "").startswith("application/json") and req.content:
            cuerpo = json.loads(req.content)
        self.llamadas.append((req.method, str(req.url.host) + ruta, cuerpo))
        if (req.url.host, ruta) in (("cm.test", "/health"), ("ci.test", "/livez")):
            return httpx.Response(200, json={"status": "alive"})
        if (req.url.host, ruta) in (("cm.test", "/health/ready"), ("ci.test", "/readyz")):
            return httpx.Response(503 if self.no_listo else 200, json={"status": "not ready" if self.no_listo else "ready"})
        if ruta in ("/health", "/livez"):
            return httpx.Response(401, json={"detail": "exige sesión"})   # como contecintelligence en /health
        if ruta.endswith("/oauth/token"):
            if cuerpo.get("client_secret") != "secreto":
                return httpx.Response(401, json={"detail": "credencial de aplicación inválida"})
            return httpx.Response(200, json={"access_token": "app-tok", "expires_in": 600})
        if ruta.endswith("/tokens/exchange"):
            assert req.headers["authorization"] == "Bearer app-tok"
            if cuerpo["tenant"] not in self.tenants:
                return httpx.Response(403, json={"detail": "tenant not mapped"})
            return httpx.Response(200, json={"access_token": f"u|{cuerpo['role']}|{','.join(cuerpo['scopes'])}",
                                             "token": "x", "expires_in": cuerpo["ttl_s"]})
        rol, alcances = self._quien(req)
        if not rol:
            return httpx.Response(401, json={"detail": "sin token"})
        if req.url.host == "cm.test":
            return self._cm(req, ruta.removeprefix("/api/v1"), rol, alcances, cuerpo)
        return self._ci(req, ruta.removeprefix("/api"), rol, alcances, cuerpo)

    def _cm(self, req, ruta, rol, alcances, cuerpo):
        escribe = req.method in ("POST", "PUT", "PATCH", "DELETE") and not ruta.endswith("/summary")
        if escribe and (rol != "writer" or "documents:write" not in alcances):
            return httpx.Response(403, json={"detail": "write requires the curator role"})
        if ruta == "/documents/search":
            q = req.url.params["q"].lower()
            items = [{"document_id": d["id"], "title": d["title"], "snippet": "…", "score": 0.9}
                     for d in self.docs.values() if any(p in d["title"].lower() for p in q.split())]
            return httpx.Response(200, json={"query": q, "scope": "all_corpus", "items": items})
        if ruta == "/areas":
            return httpx.Response(200, json={"items": [{"id": "area-1", "name": "General"}]})
        if ruta == "/folders" and req.method == "GET":
            padre = req.url.params.get("parent_id")
            return httpx.Response(200, json={"items": [c for c in self.carpetas.values()
                                                       if c["parent_id"] == padre]})
        if ruta == "/folders" and req.method == "POST":
            c = {"id": f"f-{len(self.carpetas) + 1}", "name": cuerpo["name"], "parent_id": cuerpo["parent_id"],
                 "area_id": cuerpo["area_id"]}
            self.carpetas[c["id"]] = c
            return httpx.Response(201, json=c)
        if ruta == "/documents" and req.method == "POST":
            # Como contecmind: la misma `Idempotency-Key` devuelve el documento ya creado.
            repetido = next((d for d in self.docs.values() if d.get("_idem") and d["_idem"] == req.headers.get("idempotency-key")), None)
            if repetido:
                return httpx.Response(201, json={k: v for k, v in repetido.items() if not k.startswith("_")})
            d = {"id": f"d-{uuid.uuid4().hex[:6]}", "title": "Contrato firmado", "mime_type": "application/pdf",
                 "size_bytes": len(req.content), "status": "processing",
                 "_idem": req.headers.get("idempotency-key"), "_form": req.content}
            self.docs[d["id"]] = d
            return httpx.Response(201, json={k: v for k, v in d.items() if not k.startswith("_")})
        if ruta.startswith("/documents/") and ruta.endswith("/raw"):
            return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf",
                                                                     "content-disposition": 'attachment; filename="vpn.pdf"'})
        if ruta.startswith("/documents/") and ruta.count("/") == 2:
            d = self.docs.get(ruta.split("/")[2])
            if d is None:
                return httpx.Response(404, json={"detail": "document not found"})
            return httpx.Response(200, json={**{k: v for k, v in d.items() if not k.startswith("_")},
                                             "extracted_text": "Paso 1…", "doc_metadata": {}})
        if ruta.endswith("/approval") and req.method == "GET":
            return httpx.Response(200, json={"document_id": ruta.split("/")[2], "title": "x", "control_state": "controlled",
                                             "current_version_no": 1, "requires_approval": True, "puedo_pedir": True,
                                             "solicitud": None, "versions": [
                                                 {"version_no": 1, "state": "published", "filename": "v1.pdf",
                                                  "created_at": "2026-10-01T10:00:00Z", "published_at": "2026-10-02T10:00:00Z"},
                                                 {"version_no": 2, "state": "draft", "filename": "v2.pdf",
                                                  "change_note": "Anexo de precios", "created_at": "2026-11-05T10:00:00Z"}]})
        if ruta.endswith("/approval") and req.method == "POST":
            return httpx.Response(201, json={"id": "ap-1", "status": "pending", "version_no": cuerpo.get("version_no")})
        if ruta.endswith("/summary"):
            return httpx.Response(200, json={"answer": "Vence el 31-12-2027.", "documents": [],
                                             "citations": [{"document_id": "d-1", "document_title": "Contrato",
                                                            "text": "vigencia hasta el 31-12-2027", "page_number": 3}]})
        return httpx.Response(404, json={"detail": f"ruta no simulada {ruta}"})

    def _ci(self, req, ruta, rol, alcances, cuerpo):
        if ruta == "/sources":
            return httpx.Response(200, json=[{"id": "s-erp", "name": "ERP", "source_type": "postgres", "status": "ok"}])
        if ruta == "/ask":
            return httpx.Response(200, json={"text": "Facturado: 120.000 €", "payload": {"rows": [[120000]]},
                                             "receipt_id": "r-1", "receipt_signed": True, "conversation_id": "c-1"})
        if ruta == "/ask/stream":
            # Formato real (contecintelligence `api/ask.py`): eventos con `event`, el resultado
            # con la misma forma que `POST /ask`, y `done` al cerrar.
            fin = {"event": "result", "text": "Facturado: 120.000 €", "receipt_id": "r-1", "receipt_signed": True,
                   "conversation_id": "c-1", "payload": {"type": "bar_chart", "title": "Facturado por cliente",
                                                         "xAxis": {"key": "cliente", "label": "Cliente"},
                                                         "series": [{"key": "importe", "label": "Importe"}],
                                                         "data": [{"cliente": "Acme", "importe": 80000},
                                                                  {"cliente": "Globex", "importe": 40000}]}}
            cuerpo = (b'data: {"event": "token", "text": "Facturado"}\n\n' + b"data: " + json.dumps(fin).encode()
                      + b'\n\ndata: {"event": "done"}\n\n')
            return httpx.Response(200, content=cuerpo, headers={"content-type": "text/event-stream"})
        if ruta == "/catalog/metrics":
            if rol != "analyst":
                return httpx.Response(403, json={"detail": "permission denied: metrics"})
            return httpx.Response(200, json=[{"id": "m1", "name": "ventas_netas", "label": "Ventas netas",
                                              "source_id": "s-erp", "dimensions": ["zona"]}])
        if ruta.endswith("/verify"):
            return httpx.Response(200, json={"valid": True, "reason": "firma correcta"})
        return httpx.Response(404, json={"detail": f"ruta no simulada {ruta}"})


class _Shim:
    """El módulo `httpx` que ve el conector, con el transporte del doble."""

    HTTPError = httpx.HTTPError
    Timeout = httpx.Timeout

    def __init__(self, doble):
        self._t = httpx.MockTransport(doble.handler)

    def _c(self):
        return httpx.Client(transport=self._t)

    def post(self, url, **k):
        k.pop("timeout", None)
        return self._c().post(url, **k)

    def get(self, url, **k):
        k.pop("timeout", None)
        return self._c().get(url, **k)

    def request(self, metodo, url, **k):
        k.pop("timeout", None)
        return self._c().request(metodo, url, **k)

    def Client(self, **k):
        return httpx.Client(transport=self._t)


@pytest.fixture
def doble(db, monkeypatch):
    d = _Doble()
    monkeypatch.setattr(anfitrion, "httpx", _Shim(d))
    anfitrion.olvidar_tokens()
    for prov, base in (("contecmind", BASE_CM), ("contecintelligence", BASE_CI)):
        creds.set_credential(db, prov, "base_url", base, "1")
        creds.set_credential(db, prov, "client_id", "cid", "1")
        creds.set_credential(db, prov, "client_secret", "secreto", "1")
    creds.set_credential(db, "contecintelligence", "source_id", "s-erp", "1")
    db.commit()
    creds.invalidate_cache() if hasattr(creds, "invalidate_cache") else None
    yield d
    anfitrion.olvidar_tokens()


@pytest.fixture
def ticket(db):
    t = Ticket(id="t-con", number="INC-777", ticket_type="incident", title="La VPN no conecta",
               description="Desde casa no entra", organization_id="1")
    db.add(t)
    db.commit()
    return t


def _proyecto(db):
    from app.models.project import Project, ProjectStatus, ProjectType
    db.add(Project(id="p-con", code="PRJ-CON", name="Conectores", status=ProjectStatus.active,
                   project_type=ProjectType.development, organization_id="1"))
    db.flush()
    return "p-con"


def _canjes(doble):
    return [c for _, r, c in doble.llamadas if r.endswith("/tokens/exchange")]


URL = "/api/v1/conectores"


def test_EL_HALLAZGO_busca_con_la_identidad_de_quien_llama_y_el_token_se_reutiliza(client, doble, pm_token):
    for _ in range(2):
        r = client.get(f"{URL}/contecmind/buscar", params={"q": "vpn"}, headers=auth(pm_token))
        assert r.status_code == 200, r.text
    assert [i["title"] for i in r.json()["data"]["items"]] == ["Procedimiento VPN"]
    assert [c for _, r_, c in doble.llamadas if r_.endswith("/oauth/token")] == [
        {"client_id": "cid", "client_secret": "secreto", "grant_type": "client_credentials"}]
    (canje,) = _canjes(doble)              # una vez: la segunda búsqueda usa el token guardado
    assert canje == {"tenant": "1", "subject": "pm@contecflow.com", "role": "reader",
                     "scopes": ["documents:read", "documents:search"], "ttl_s": 300}


def test_subir_crea_la_carpeta_de_la_ficha_una_vez_y_enlaza(client, db, doble, pm_token, ticket):
    for _ in range(2):
        r = client.post(f"{URL}/contecmind/fichas/ticket/{ticket.id}/subir", headers=auth(pm_token),
                        files={"file": ("contrato.pdf", b"%PDF uno", "application/pdf")}, data={"nota": "firmado"})
        assert r.status_code == 200, r.text
    assert [(c["name"], c["parent_id"]) for c in doble.carpetas.values()] == [
        ("contecflow", None), ("Tickets", "f-1"), ("INC-777 — La VPN no conecta", "f-2")]
    carpeta = db.query(CarpetaDocumental).one()
    assert (carpeta.folder_id, carpeta.area_id, carpeta.ruta) == ("f-3", "area-1",
                                                                   "contecflow/Tickets/INC-777 — La VPN no conecta")
    subidos = [d for d in doble.docs.values() if "_idem" in d]
    assert len(subidos) == 1 and subidos[0]["_idem"]          # la misma subida, la misma clave: un documento
    assert b'name="folder_id"\r\n\r\nf-3' in subidos[0]["_form"] and b'name="area_id"\r\n\r\narea-1' in subidos[0]["_form"]
    assert any(c["role"] == "writer" and "documents:write" in c["scopes"] for c in _canjes(doble))
    enlaces = client.get(f"{URL}/contecmind/fichas/ticket/{ticket.id}/documentos", headers=auth(pm_token)).json()
    assert [e["origen"] for e in enlaces["data"]["items"]] == ["subido"]      # y un solo enlace


def test_un_rol_que_no_escribe_no_sube_y_lo_dice(client, db, doble, hr_token, ticket):
    settings_service.set_runtime_value(db, "conectores", "CONTECMIND_WRITER_ROLES", "admin", "1")
    db.commit()
    settings_service.invalidate_cache()
    r = client.post(f"{URL}/contecmind/fichas/ticket/{ticket.id}/subir", headers=auth(hr_token),
                    files={"file": ("a.pdf", b"x", "application/pdf")})
    assert r.status_code == 403 and r.headers["x-conector-codigo"] == "sin_permiso"
    assert "CONTECMIND_WRITER_ROLES" in r.json()["detail"]
    assert doble.llamadas == [] and db.query(EnlaceDocumental).count() == 0


def test_la_ficha_se_abre_con_su_propio_control_de_acceso(client, db, doble, dev_token, pm_token, ticket):
    # Un empleado sólo ve los tickets que pidió o tiene asignados: este no.
    r = client.get(f"{URL}/contecmind/fichas/ticket/{ticket.id}/documentos", headers=auth(dev_token))
    assert r.status_code == 404
    r = client.post(f"{URL}/contecmind/fichas/ticket/{ticket.id}/documentos", headers=auth(dev_token),
                    json={"document_id": "d-vpn"})
    assert r.status_code == 404 and _canjes(doble) == []
    from app.models.pipeline import Contract
    db.add(Contract(id="c-1", code="CTR-1", name="Soporte", organization_id="1", project_id=_proyecto(db), client_name="Acme",
                    contract_type="fixed_price"))
    db.commit()
    assert client.get(f"{URL}/contecmind/fichas/contract/c-1/documentos", headers=auth(dev_token)).status_code == 403
    assert client.get(f"{URL}/contecmind/fichas/contract/c-1/documentos", headers=auth(pm_token)).status_code == 200


def test_enlazar_lee_el_documento_con_sus_permisos_y_las_sugerencias_quitan_lo_enlazado(client, doble, pm_token, ticket):
    s = client.get(f"{URL}/contecmind/fichas/ticket/{ticket.id}/sugerencias", headers=auth(pm_token)).json()
    assert [i["document_id"] for i in s["data"]["items"]] == ["d-vpn"]
    r = client.post(f"{URL}/contecmind/fichas/ticket/{ticket.id}/documentos", headers=auth(pm_token),
                    json={"document_id": "d-vpn", "nota": "resuelve"})
    assert r.json()["data"]["title"] == "Procedimiento VPN"
    s = client.get(f"{URL}/contecmind/fichas/ticket/{ticket.id}/sugerencias", headers=auth(pm_token)).json()
    assert s["data"]["items"] == []
    r = client.post(f"{URL}/contecmind/fichas/ticket/{ticket.id}/documentos", headers=auth(pm_token),
                    json={"document_id": "no-existe"})
    assert r.status_code == 404 and r.headers["x-conector-codigo"] == "no_encontrado"
    enlace = client.get(f"{URL}/contecmind/fichas/ticket/{ticket.id}/documentos", headers=auth(pm_token)).json()
    eid = enlace["data"]["items"][0]["id"]
    assert client.delete(f"{URL}/contecmind/fichas/ticket/{ticket.id}/documentos/{eid}",
                         headers=auth(pm_token)).status_code == 200
    assert "d-vpn" in doble.docs                       # el documento sigue en contecmind


def test_preguntar_a_la_carpeta_exige_que_exista_y_devuelve_citas(client, doble, pm_token, ticket):
    url = f"{URL}/contecmind/fichas/ticket/{ticket.id}/preguntar"
    assert client.post(url, headers=auth(pm_token), json={"pregunta": "¿Cuándo vence?"}).status_code == 409
    client.post(f"{URL}/contecmind/fichas/ticket/{ticket.id}/subir", headers=auth(pm_token),
                files={"file": ("c.pdf", b"%PDF", "application/pdf")})
    r = client.post(url, headers=auth(pm_token), json={"pregunta": "¿Cuándo vence?"}).json()["data"]
    assert r["answer"] == "Vence el 31-12-2027." and r["citations"][0]["page"] == 3


def test_pedir_aprobacion_exige_el_rol_que_escribe(client, db, doble, pm_token, hr_token):
    a = client.get(f"{URL}/contecmind/documentos/d-vpn/aprobacion", headers=auth(pm_token)).json()["data"]
    assert [v["state"] for v in a["versions"]] == ["published", "draft"]
    r = client.post(f"{URL}/contecmind/documentos/d-vpn/aprobacion", params={"version_no": 2}, headers=auth(pm_token))
    assert r.status_code == 200 and r.json()["data"]["version_no"] == 2
    settings_service.set_runtime_value(db, "conectores", "CONTECMIND_WRITER_ROLES", "admin", "1")
    db.commit()
    settings_service.invalidate_cache()
    r = client.post(f"{URL}/contecmind/documentos/d-vpn/aprobacion", params={"version_no": 2}, headers=auth(hr_token))
    assert r.status_code == 403 and r.headers["x-conector-codigo"] == "sin_permiso"


def test_descargar_el_original(client, doble, pm_token):
    r = client.get(f"{URL}/contecmind/documentos/d-vpn/original", headers=auth(pm_token))
    assert r.content == b"%PDF-1.4" and 'filename="vpn.pdf"' in r.headers["content-disposition"]


def test_los_fallos_tienen_nombre_y_quedan_registrados(client, db, doble, pm_token):
    doble.tenants = set()
    r = client.get(f"{URL}/contecmind/buscar", params={"q": "vpn"}, headers=auth(pm_token))
    assert r.status_code == 403 and r.headers["x-conector-codigo"] == "no_alta"
    anfitrion.olvidar_tokens()
    doble.caido = True
    r = client.get(f"{URL}/contecmind/buscar", params={"q": "vpn"}, headers=auth(pm_token))
    assert r.status_code == 503 and r.headers["x-conector-codigo"] == "no_responde"
    filas = db.query(ConectorLlamada).order_by(ConectorLlamada.created_at).all()
    assert [(f.operacion, f.ok, f.estado_http) for f in filas] == [("buscar", False, 403), ("buscar", False, None)]
    assert "dada de alta" in filas[0].error and "ConnectError" in filas[1].error


def test_sin_configurar_lo_dice_y_no_llama(client, db, doble, pm_token):
    creds.set_credential(db, "contecmind", "client_secret", None, "1")
    db.commit()
    creds.invalidate_cache() if hasattr(creds, "invalidate_cache") else None
    r = client.get(f"{URL}/contecmind/buscar", params={"q": "vpn"}, headers=auth(pm_token))
    assert r.status_code == 409 and r.headers["x-conector-codigo"] == "no_configurado"
    assert doble.llamadas == []
    assert client.get(f"{URL}/contecmind/disponible", headers=auth(pm_token)).json()["data"] == {
        "configurado": False, "puede_escribir": False}


def test_un_fichero_demasiado_grande_no_sale(client, db, doble, pm_token, ticket):
    settings_service.set_runtime_value(db, "conectores", "CONTECMIND_UPLOAD_MAX_MB", 1, "1")
    db.commit()
    settings_service.invalidate_cache()
    r = client.post(f"{URL}/contecmind/fichas/ticket/{ticket.id}/subir", headers=auth(pm_token),
                    files={"file": ("g.bin", b"0" * (1024 * 1024 + 1), "application/octet-stream")})
    assert r.status_code == 413 and doble.llamadas == []


def test_contecintelligence_pregunta_con_recibo_y_reenvia_el_directo(client, doble, pm_token, dev_token):
    r = client.post(f"{URL}/contecintelligence/preguntar", headers=auth(pm_token),
                    json={"question": "¿Cuánto hemos facturado?"}).json()["data"]
    assert (r["text"], r["receipt_id"], r["source_id"]) == ("Facturado: 120.000 €", "r-1", "s-erp")
    assert _canjes(doble)[0]["role"] == "analyst" and _canjes(doble)[0]["scopes"] == ["chat:ask", "sources:read"]
    r = client.post(f"{URL}/contecintelligence/preguntar/directo", headers=auth(pm_token), json={"question": "x"})
    assert r.headers["content-type"].startswith("text/event-stream")
    assert b'"event": "result"' in r.content and r.content.endswith(b'data: {"event": "done"}\n\n')
    # Un empleado entra como `viewer`: pregunta, pero el catálogo de métricas le dice que no.
    r = client.get(f"{URL}/contecintelligence/metricas", headers=auth(dev_token))
    assert r.status_code == 403 and r.headers["x-conector-codigo"] == "sin_permiso"
    assert client.get(f"{URL}/contecintelligence/metricas", headers=auth(pm_token)).json()["data"]["items"][0][
        "name"] == "ventas_netas"
    assert client.get(f"{URL}/contecintelligence/recibos/r-1/verificar", headers=auth(pm_token)).json()["data"][
        "valid"] is True


def test_el_token_de_los_componentes_no_lleva_la_credencial(client, doble, pm_token):
    d = client.post(f"{URL}/contecintelligence/token", headers=auth(pm_token), json={"source_id": "s-erp"}).json()["data"]
    assert set(d) == {"access_token", "expires_in", "base_url"} and "secreto" not in json.dumps(d)
    assert _canjes(doble)[-1]["source_id"] == "s-erp"


def test_estado_y_prueba_de_conexion_para_el_admin(client, db, doble, admin_token, pm_token):
    client.get(f"{URL}/contecmind/buscar", params={"q": "vpn"}, headers=auth(pm_token))
    assert client.get(f"{URL}/estado", headers=auth(pm_token)).status_code == 403
    e = client.get(f"{URL}/estado", headers=auth(admin_token)).json()["data"]
    cm = next(p for p in e["productos"] if p["producto"] == "contecmind")
    assert cm["configurado"] is True and cm["llamadas"] == 1 and cm["fallos"] == 0
    assert cm["operaciones"][0]["operacion"] == "buscar" and cm["p50_ms"] is not None
    doble.tenants = set()
    anfitrion.olvidar_tokens()
    p = client.post(f"{URL}/contecmind/probar", headers=auth(admin_token)).json()["data"]
    assert p["aplicacion"]["ok"] is True and p["empresa"]["codigo"] == "no_alta" and p["ok"] is False
    p = client.post(f"{URL}/contecintelligence/probar", headers=auth(admin_token)).json()["data"]
    assert p["aplicacion"]["ok"] is True, p
    doble.no_listo = True     # vivo, pero su `readyz` dice que no puede atender
    p = client.post(f"{URL}/contecintelligence/probar", headers=auth(admin_token)).json()["data"]
    assert p["aplicacion"]["codigo"] == "no_listo" and "/readyz" in p["aplicacion"]["detail"] and p["empresa"] is None


def test_cambiar_la_credencial_olvida_los_tokens(client, doble, admin_token, pm_token):
    client.get(f"{URL}/contecmind/buscar", params={"q": "vpn"}, headers=auth(pm_token))
    r = client.put("/api/v1/settings/integrations/contecmind/client_secret", headers=auth(admin_token),
                   json={"value": "otro"})
    assert r.status_code == 200
    r = client.get(f"{URL}/contecmind/buscar", params={"q": "vpn"}, headers=auth(pm_token))
    assert r.status_code == 502 and r.headers["x-conector-codigo"] == "rechazado"


def test_purgar_el_registro_respeta_los_dias(db):
    from datetime import datetime, timedelta, timezone

    from app.services.conectores.estado import purgar
    viejo = datetime.now(timezone.utc) - timedelta(days=40)
    db.add(ConectorLlamada(organization_id="1", producto="contecmind", operacion="buscar", ok=True, ms=5,
                           created_at=viejo))
    db.add(ConectorLlamada(organization_id="1", producto="contecmind", operacion="buscar", ok=True, ms=5))
    db.commit()
    assert purgar(db) == 1 and db.query(ConectorLlamada).count() == 1


def test_las_cabeceras_de_un_error_llegan_al_cliente(client):
    """Antes el gestor general las tiraba: un 401 salía sin `WWW-Authenticate`."""
    r = client.get("/api/v1/conectores/estado", headers={"Authorization": "Bearer no-vale"})
    assert r.status_code == 401 and r.headers.get("www-authenticate") == "Bearer"
