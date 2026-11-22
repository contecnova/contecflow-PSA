"""Punto de entrada común para los canales (portal de clientes, portal interno, operador, proveedor).

Un canal solo tiene que construir el actor y llamar a estas funciones; el
motor hace el resto (tipos del canal, alcance, ficha, envío, edición,
adjuntos, comentarios, retirada). Ejemplo del portal interno de clientes
internos (usuario interno):

    from app.services.demanda import entrada
    s = entrada.Solicitante(kind="internal_user", user=current_user, client_id=unidad.id)
    entrada.crear(db, s, {"title": …, "description": …, "kind": "servicio"})  # -> resumen (dict)
    entrada.listar(db, s)                                                       # -> [resumen]

Sin `type_key`, el tipo es el primero (por orden) de los ofrecidos en el canal
(`tipo_por_defecto`): se configura ordenando los tipos, sin código.

El cliente del portal se construye con `de_cliente(client_user)` y sus
proyectos permitidos (`client.get_project_ids()`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio

from app.core.codigos_de_error import error
from app.services.demanda import config, consultas, documentos, expediente, serializacion
from app.services.demanda import definicion as D
from app.services.demanda.acceso import Actor
from app.services.demanda.motor import flujo_de, jload


def tipos_del_canal(db: Session, canal: str, org_id: Optional[str], idioma: str = "es") -> list[dict]:
    """Tipos activos ofrecidos en el canal, con los campos que rellena el solicitante."""
    from app.models.demanda import DemandFlow, DemandRequestType
    salida = []
    for t in db.query(DemandRequestType).filter(DemandRequestType.organization_id == org_id,
                                                DemandRequestType.is_active.is_(True)) \
            .order_by(DemandRequestType.sort_order, DemandRequestType.name).all():
        if canal not in jload(t.channels, []) or not t.flow_id:
            continue
        f = db.query(DemandFlow).filter(DemandFlow.id == t.flow_id, DemandFlow.is_active.is_(True)).first()
        if f is None:
            continue
        defn = D.cargar(f.definition)
        campos = [c for c in D.campos(defn) if c.get("owner", "client") == "client" and c.get("client_visible", True)]
        d = config.tipo_dict(t, idioma)
        d["fields"] = [{"key": c["key"], "label": D.nombre(c.get("label"), idioma), "type": c.get("type", "text"),
                        "options": [{"value": o.get("value"), "label": D.nombre(o.get("label"), idioma)}
                                    for o in c.get("options") or []]} for c in campos]
        d["submit_required"] = defn.get("submit_required") or []
        d["phases"] = [{"key": x["key"], "name": D.nombre(x.get("name"), idioma)} for x in D.fases(defn)]
        salida.append(d)
    return salida


def opciones_de_alcance(db: Session, org_id: Optional[str], tipo: str, q: Optional[str] = None,
                        limite: int = 200) -> list[dict]:
    """Opciones del selector de alcance: elementos del catálogo de servicios
    (`service`) o elementos de configuración activos de la CMDB (`asset`), de la empresa."""
    if tipo == "service":
        from app.models.service_desk.catalog import ServiceItem as M
        consulta = db.query(M)
    elif tipo == "asset":
        from app.models.service_desk.cmdb import ConfigurationItem as M
        consulta = db.query(M).filter(M.is_active.is_(True))
    else:
        return []
    if org_id:
        consulta = consulta.filter(M.organization_id == org_id)
    if q:
        consulta = consulta.filter(M.name.ilike(f"%{q.strip()}%"))
    salida = []
    for x in consulta.order_by(M.name).limit(limite).all():
        codigo = getattr(x, "code", None)
        salida.append({"value": x.id, "label": f"{codigo} · {x.name}" if codigo else x.name})
    return salida


def obtener_propio(db: Session, actor: Actor, req_id: str):
    """El expediente si es del solicitante (cliente o usuario); si no, 404."""
    from app.models.demanda import DemandRequest
    req = db.query(DemandRequest).filter(DemandRequest.id == req_id).first()
    if req is None or not expediente.es_solicitante(actor, req):
        raise error(404, "dem_expediente_no_encontrado")
    return req


def crear_expediente(db: Session, actor: Actor, canal: str, datos: dict, *, org_id: Optional[str],
                     proyectos_permitidos: Optional[list] = None):
    return expediente.crear(db, actor, canal, datos, org_id=org_id, proyectos_permitidos=proyectos_permitidos)


def listar_propios(db: Session, actor: Actor, idioma: str = "es") -> list[dict]:
    return consultas.listar_del_solicitante(db, actor, idioma)


# ── Fachada para otros canales (contrato del portal interno de clientes internos) ──

@dataclass
class Solicitante:
    """Quién pide por un canal. `kind`: internal_user (portal interno), employee
    (operador), supplier (portal del proveedor) o client_user (portal de clientes:
    `user` es el `ClientUser`). `client_id`: el cliente o unidad interna."""
    kind: str
    user: object = None
    client_id: Optional[str] = None


CANAL_DE_SOLICITANTE = {"internal_user": "internal_portal", "employee": "operator",
                        "supplier": "supplier_portal", "client_user": "client_portal"}


def _actor(s) -> Actor:
    if isinstance(s, Actor):
        return s
    from app.services.demanda.acceso import de_cliente, de_usuario
    return de_cliente(s.user) if s.kind == "client_user" else de_usuario(s.user)


def tipo_por_defecto(db: Session, canal: str, org_id: Optional[str], pista: Optional[str] = None) -> Optional[str]:
    """El tipo que usa un canal cuando quien pide no elige: el primero (por orden) de los
    tipos activos del canal. Configurable sin código ordenando los tipos en
    Configuración → Flujos de demanda. `pista` (p. ej. «servicio» o «proyecto»)
    prefiere un tipo cuya clave la contenga o cuyo alcance la cubra."""
    lista = tipos_del_canal(db, canal, org_id)
    if not lista:
        return None
    if pista:
        alcance = {"servicio": "service", "proyecto": "project", "activo": "asset"}.get(pista, pista)
        for t in lista:
            if pista in t["key"] or (alcance != "project" and alcance in (t.get("scopes") or [])):
                return t["key"]
    return lista[0]["key"]


def _rellenar(db: Session, canal: str, org_id: Optional[str], datos: dict) -> dict:
    """Pasa los datos genéricos de un canal (description, estimated_budget…) a los
    campos del flujo del tipo elegido."""
    from app.models.demanda import DemandFlow, DemandRequestType
    tipos = {t["key"]: t for t in tipos_del_canal(db, canal, org_id)}
    clave = datos.get("type_key") or tipo_por_defecto(db, canal, org_id, datos.get("kind"))
    if not clave or clave not in tipos:
        raise error(404, "dem_tipo_no_encontrado")
    t = db.query(DemandRequestType).filter(DemandRequestType.organization_id == org_id,
                                           DemandRequestType.key == clave).first()
    defn = D.cargar(db.query(DemandFlow.definition).filter(DemandFlow.id == t.flow_id).scalar())
    data = dict(datos.get("data") or {})
    textos = [c for c in D.campos(defn) if c.get("type") == "textarea" and c.get("owner", "client") == "client"]
    if datos.get("description") and textos and textos[0]["key"] not in data:
        data[textos[0]["key"]] = datos["description"]
    coste = D.campo_de_politica(defn, "coste")
    campo_coste = D.campo(defn, coste) if coste else None
    if datos.get("estimated_budget") not in (None, "") and campo_coste \
            and campo_coste.get("owner", "client") == "client":
        data.setdefault(coste, datos["estimated_budget"])
    alcances = tipos[clave].get("scopes") or []
    if datos.get("scope_kind"):
        alcance = datos["scope_kind"]
    elif datos.get("project_id"):
        alcance = "project"
    elif datos.get("kind") == "servicio" and "service" in alcances:
        alcance = "service"
    else:
        alcance = "none"
    return {"type_key": clave, "title": datos.get("title"), "project_id": datos.get("project_id"),
            "scope_kind": alcance, "scope_ref_id": datos.get("scope_ref_id"), "client_id": datos.get("client_id"),
            "data": data}


def crear(db: Session, solicitante, datos: dict, canal: Optional[str] = None, *, org_id: Optional[str] = None,
          proyectos_permitidos: Optional[list] = None, idioma: str = "es") -> dict:
    """Alta por un canal. Intenta enviarla; si faltan datos obligatorios queda en borrador.
    Devuelve el resumen del expediente (id, code, title, status, created_at…)."""
    actor = _actor(solicitante)
    canal = canal or CANAL_DE_SOLICITANTE.get(getattr(solicitante, "kind", ""), "operator")
    org_id = org_id or actor.organization_id
    if getattr(solicitante, "client_id", None) and not datos.get("client_id"):
        datos = {**datos, "client_id": solicitante.client_id}
    pedir_envio = datos.get("submit", True)
    preparados = _rellenar(db, canal, org_id, datos)
    preparados["submit"] = False
    req = expediente.crear(db, actor, canal, preparados, org_id=org_id, proyectos_permitidos=proyectos_permitidos)
    if pedir_envio:
        try:
            expediente.enviar(db, actor, req)
        except ErrorDeDominio as exc:
            if getattr(exc, "code", None) != "dem_campos_obligatorios":
                raise
            db.rollback()
    return serializacion.resumen(db, req, idioma)


def listar(db: Session, solicitante, idioma: str = "es") -> list[dict]:
    """Las solicitudes de quien pide (y, con `client_id`, solo las de ese cliente o unidad)."""
    filas = consultas.listar_del_solicitante(db, _actor(solicitante), idioma)
    cliente = getattr(solicitante, "client_id", None)
    if cliente and getattr(solicitante, "kind", "") != "client_user":
        from app.models.demanda import DemandRequest
        ids = {i for (i,) in db.query(DemandRequest.id).filter(DemandRequest.client_id == cliente).all()}
        filas = [f for f in filas if f["id"] in ids]
    return filas


def detalle(db: Session, actor: Actor, req_id: str, idioma: str = "es") -> dict:
    return serializacion.detalle(db, obtener_propio(db, actor, req_id), actor, idioma)


def editar(db: Session, actor: Actor, req_id: str, titulo: Optional[str], datos: dict) -> None:
    expediente.editar(db, actor, obtener_propio(db, actor, req_id), titulo, datos)


def enviar(db: Session, actor: Actor, req_id: str, nota: Optional[str] = None) -> None:
    expediente.enviar(db, actor, obtener_propio(db, actor, req_id), nota)


def comentar(db: Session, actor: Actor, req_id: str, cuerpo: str) -> None:
    expediente.comentar(db, actor, obtener_propio(db, actor, req_id), cuerpo, False)


def retirar(db: Session, actor: Actor, req_id: str, motivo: Optional[str]) -> None:
    expediente.retirar(db, actor, obtener_propio(db, actor, req_id), motivo)


def adjuntar(db: Session, actor: Actor, req_id: str, **kw):
    return documentos.subir(db, actor, obtener_propio(db, actor, req_id), **kw)


def descargar(db: Session, actor: Actor, req_id: str, doc_id: str, ip: Optional[str] = None):
    return documentos.descargar(db, actor, obtener_propio(db, actor, req_id), doc_id, ip)


def decidir(db: Session, actor: Actor, req_id: str, paso: str, decision: str,
            justificacion: Optional[str] = None, destino: Optional[str] = None) -> None:
    """Paso cuyo responsable es el propio solicitante (p. ej. «el cliente confirma el presupuesto»)."""
    from app.services.demanda.motor import decidir as decidir_paso
    decidir_paso(db, obtener_propio(db, actor, req_id), actor, paso, decision, destino=destino,
                 justificacion=justificacion)


def fases_del_expediente(req) -> list:
    return [f["key"] for f in D.fases(flujo_de(req))]
