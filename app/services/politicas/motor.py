"""El motor: compila las políticas publicadas, las evalúa y explica por qué.

Rendimiento (tarea #26, punto 7): las políticas publicadas de cada (empresa,
dominio) se compilan una vez —JSON ya leído, ordenadas por prioridad— y se
guardan en memoria con una FIRMA: (número de versiones, última modificación)
de las políticas del dominio y de las tablas de referencia de la empresa. Cada
evaluación paga solo esa consulta de agregados (dos `count/max` por índice);
si la firma cambia —otro proceso publicó—, se recompila. Las escrituras de
este proceso además invalidan su entrada al momento (`invalidar`).

`evaluar` NO escribe nada: es lo que usan el simulador y los dominios antes de
decidir. `registrar` guarda la explicación (`politica_evaluaciones`), y
`ejecutar_avisos` / `aplicar_campos` tienen efectos: los llama el dominio
cuando la entidad se envía de verdad.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.politicas import EvaluacionDePolitica, FilaDeTablaDeReferencia, Politica, TablaDeReferencia
from app.services.politicas import catalogo, resultados as res
from app.services.politicas.condiciones import Evaluador, Indeterminado

logger = logging.getLogger(__name__)

_CACHE: dict = {}
_LOCK = threading.Lock()
ESTADISTICAS = {"compilaciones": 0, "aciertos": 0}


def _json(v, defecto):
    if not v:
        return defecto
    try:
        return json.loads(v)
    except ValueError:
        return defecto


def invalidar(organization_id: Optional[str], dominio: Optional[str] = None) -> None:
    with _LOCK:
        for clave in [k for k in _CACHE if k[0] == organization_id and (dominio is None or k[1] == dominio)]:
            _CACHE.pop(clave, None)


def compilar(p: Politica) -> dict:
    return {
        "id": p.id, "familia_id": p.familia_id, "version": p.version, "nombre": p.nombre,
        "prioridad": p.prioridad or 0, "vigente_desde": p.vigente_desde, "vigente_hasta": p.vigente_hasta,
        "ambito": _json(p.ambito, {}), "activa": bool(p.activa),
        "reglas": [{"id": r.id, "nombre": r.nombre, "orden": r.orden, "condicion": _json(r.condicion, None),
                    "resultados": _json(r.resultados, []), "exceso": _json(r.exceso, None),
                    "detener": bool(r.detener)}
                   for r in sorted(p.reglas or [], key=lambda r: r.orden) if r.activa],
    }


def _firma(db: Session, org: Optional[str], dominio: str) -> tuple:
    q = db.query(func.count(Politica.id), func.max(Politica.updated_at)).filter(Politica.dominio == dominio)
    q = q.filter(Politica.organization_id == org) if org else q.filter(Politica.organization_id.is_(None))
    a = q.one()
    t = db.query(func.count(TablaDeReferencia.id), func.max(TablaDeReferencia.updated_at))
    t = t.filter(TablaDeReferencia.organization_id == org) if org else t.filter(TablaDeReferencia.organization_id.is_(None))
    b = t.one()
    return (a[0], str(a[1]), b[0], str(b[1]))


def cargar_tablas(db: Session, ids: list) -> dict:
    salida: dict = {}
    if not ids:
        return salida
    tablas = {t.id: t for t in db.query(TablaDeReferencia).filter(TablaDeReferencia.id.in_(ids)).all()}
    for t in tablas.values():
        salida[t.id] = (t.tipo_de_valor, [])
    for f in db.query(FilaDeTablaDeReferencia).filter(FilaDeTablaDeReferencia.tabla_id.in_(list(tablas))).all():
        salida[f.tabla_id][1].append({"pais": f.pais, "ciudad": f.ciudad, "categoria": f.categoria, "valor": f.valor,
                                      "moneda": f.moneda, "vigente_desde": f.vigente_desde,
                                      "vigente_hasta": f.vigente_hasta})
    return salida


def _tablas_usadas(politicas: list) -> set:
    ids: set = set()

    def ver(nodo):
        if not isinstance(nodo, dict):
            return
        ref = nodo.get("referencia") or {}
        if ref.get("tipo") == "tabla" and ref.get("tabla_id"):
            ids.add(ref["tabla_id"])
        for h in nodo.get("hijos") or []:
            ver(h)
    for p in politicas:
        for r in p["reglas"]:
            ver(r["condicion"])
            ref = (r["exceso"] or {}).get("referencia") or {}
            if ref.get("tipo") == "tabla" and ref.get("tabla_id"):
                ids.add(ref["tabla_id"])
    return ids


def publicadas(db: Session, org: Optional[str], dominio: str) -> tuple[list, dict]:
    """(políticas compiladas por prioridad, tablas que usan), desde la caché si la firma no cambió."""
    firma = _firma(db, org, dominio)
    clave = (org, dominio)
    with _LOCK:
        entrada = _CACHE.get(clave)
        if entrada and entrada[0] == firma:
            ESTADISTICAS["aciertos"] += 1
            return entrada[1], entrada[2]
    q = db.query(Politica).filter(Politica.dominio == dominio, Politica.estado == "publicada")
    q = q.filter(Politica.organization_id == org) if org else q.filter(Politica.organization_id.is_(None))
    compiladas = sorted((compilar(p) for p in q.all()), key=lambda c: (-c["prioridad"], c["nombre"], c["id"]))
    tablas = cargar_tablas(db, list(_tablas_usadas(compiladas)))
    with _LOCK:
        _CACHE[clave] = (firma, compiladas, tablas)
        ESTADISTICAS["compilaciones"] += 1
    return compiladas, tablas


# ── Ámbito y vigencia ────────────────────────────────────────────────────────

def en_ambito(ambito: dict, sujeto: dict) -> tuple[bool, str]:
    """Las dimensiones con valores se exigen TODAS (Y); dentro de una, basta
    una (O). `personas` suma: una persona listada entra aunque no cumpla el
    resto. Sin nada, aplica a toda la empresa."""
    ambito = ambito or {}
    if sujeto.get("usuario_id") and sujeto["usuario_id"] in (ambito.get("personas") or []):
        return True, "persona incluida"
    dims = {"departamentos": "departamento", "equipos": "equipo", "roles": "rol"}
    exigidas = [k for k in ("departamentos", "equipos", "roles", "ubicaciones") if ambito.get(k)]
    if not exigidas:
        return (False, "solo para las personas indicadas") if ambito.get("personas") else (True, "toda la empresa")
    for k in exigidas:
        if k == "ubicaciones":
            pais = (sujeto.get("pais") or "").upper()
            ciudad = (sujeto.get("ciudad") or "").strip().lower()
            ok = any((u.split("/", 1)[0].upper() == pais and
                      (len(u.split("/", 1)) == 1 or u.split("/", 1)[1].strip().lower() == ciudad))
                     for u in ambito[k])
        else:
            ok = str(sujeto.get(dims[k]) or "").lower() in {str(x).lower() for x in ambito[k]}
        if not ok:
            return False, f"fuera del ámbito ({k})"
    return True, "dentro del ámbito"


def vigente(p: dict, fecha: Optional[date]) -> bool:
    if fecha is None:
        return True
    return not ((p["vigente_desde"] and p["vigente_desde"] > fecha) or (p["vigente_hasta"] and p["vigente_hasta"] < fecha))


# ── Evaluación ───────────────────────────────────────────────────────────────

def _banda(bandas: list, pct: float) -> Optional[dict]:
    """La banda con desde < pct ≤ hasta (sin `hasta`, sin techo). Por encima de 0 siempre."""
    for b in sorted(bandas or [], key=lambda b: float(b.get("desde") or 0)):
        desde = float(b.get("desde") or 0)
        hasta = b.get("hasta")
        if pct > desde and (hasta in (None, "") or pct <= float(hasta)):
            return b
    return None


def _resolver_propios(db: Session, dominio: catalogo.Dominio, salida: list, ctx: dict, fila: dict) -> list:
    """Los resultados propios del dominio (p. ej. el cupo de ausencias) se
    quedan en la salida —el dominio los necesita al enviar— y el gancho
    `resolver_propio` añade los resultados del motor que salen de ellos AHORA
    (cupo lleno → lista de espera, bloqueo…). Solo lee; su detalle va a la
    explicación de la regla."""
    if not dominio.resultados_propios or dominio.resolver_propio is None:
        return salida
    final: list = []
    for x in salida:
        final.append(x)
        if dominio.resultado_propio((x or {}).get("tipo")) is None:
            continue
        extra, detalle = dominio.resolver_propio(db, ctx, x)
        fila.setdefault("propios", []).append({"tipo": x.get("tipo"), **(detalle or {})})
        final.extend(extra or [])
    return final


def evaluar_con(db: Session, dominio: catalogo.Dominio, politicas: list, tablas: dict, ctx: dict) -> dict:
    """Evalúa una lista de políticas compiladas contra un contexto. Sin efectos."""
    ev = Evaluador(db, dominio, tablas)
    sujeto = ctx.get("_sujeto") or {}
    fecha = ctx.get("_fecha")
    aplicados: list = []
    explicacion: list = []
    for p in politicas:
        item = {"politica_id": p["id"], "familia_id": p["familia_id"], "politica": p["nombre"],
                "version": p["version"], "prioridad": p["prioridad"], "reglas": []}
        explicacion.append(item)
        if not p["activa"]:
            item.update(aplica=False, motivo="desactivada")
            continue
        if not vigente(p, fecha):
            item.update(aplica=False, motivo="fuera de vigencia")
            continue
        dentro, motivo = en_ambito(p["ambito"], sujeto)
        item.update(aplica=dentro, motivo=motivo)
        if not dentro:
            continue
        for r in p["reglas"]:
            traza: list = []
            cumple = ev.evaluar(r["condicion"], ctx, traza)
            fila = {"regla_id": r["id"], "regla": r["nombre"], "cumple": cumple, "traza": traza, "resultados": []}
            item["reglas"].append(fila)
            origen = {"politica_id": p["id"], "politica": p["nombre"], "regla_id": r["id"], "regla": r["nombre"]}
            if cumple is None:
                aviso = {"tipo": "warn", "mensaje": f"No se pudo evaluar «{r['nombre']}» ({p['nombre']}): "
                                                    + "; ".join(t["nota"] for t in traza if t.get("nota"))}
                aplicados.append((origen, aviso))
                fila["resultados"].append(aviso)
                continue
            if not cumple:
                continue
            salida = list(r["resultados"] or [])
            exc = r["exceso"]
            if exc and exc.get("campo"):
                detalle: dict = {}
                try:
                    pct = ev.exceso_pct(exc["campo"], exc.get("referencia") or {}, ctx, detalle)
                    banda = _banda(exc.get("bandas"), pct)
                    detalle["banda"] = banda and {"desde": banda.get("desde"), "hasta": banda.get("hasta")}
                    salida += list((banda or {}).get("resultados") or [])
                except Indeterminado as e:
                    detalle["nota"] = str(e)
                    salida.append({"tipo": "warn", "mensaje": f"No se pudo medir el exceso en «{r['nombre']}»: {e}"})
                fila["exceso"] = detalle
            salida = _resolver_propios(db, dominio, salida, ctx, fila)
            for x in salida:
                aplicados.append((origen, x))
            fila["resultados"] = salida
            if r["detener"]:
                break
    combinado = res.combinar(aplicados)
    return {"decision": combinado["decision"], "resultado": combinado, "explicacion": explicacion}


def _limpio(v):
    """Contexto serializable (fechas a texto) para guardar y devolver."""
    if isinstance(v, dict):
        return {k: _limpio(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_limpio(x) for x in v]
    if isinstance(v, date):
        return v.isoformat()
    return v


def evaluar(db: Session, dominio_clave: str, entidad=None, *, contexto: Optional[dict] = None,
            organization_id: Optional[str] = None) -> dict:
    """La función que llaman los dominios. Sin efectos.

    Devuelve {decision, resultado (combinado), explicacion, contexto}.
    `decision`: block | review | auto_approve | allow.
    """
    dominio = catalogo.dominio(dominio_clave)
    ctx = contexto if contexto is not None else dominio.contexto(db, entidad)
    org = organization_id or getattr(entidad, "organization_id", None) or (db.info or {}).get("organization_id")
    politicas, tablas = publicadas(db, org, dominio.clave)
    salida = evaluar_con(db, dominio, politicas, tablas, ctx)
    salida["contexto"] = _limpio(ctx)
    return salida


def resumen(evaluacion: dict) -> dict:
    """Lo esencial de una evaluación para listas y bandejas (sin la traza).

    `exceso_pct`: el mayor exceso medido por una regla que encajó (None si
    ninguna midió exceso). Lo guarda la solicitud de aprobación
    (`contexto._politica`) y lo enseña la bandeja de quien aprueba.
    """
    r = evaluacion.get("resultado") or {}
    pcts = [fila["exceso"]["exceso_pct"] for p in evaluacion.get("explicacion") or [] for fila in p.get("reglas") or []
            if fila.get("cumple") and (fila.get("exceso") or {}).get("exceso_pct") is not None]
    return {"decision": evaluacion.get("decision"), "niveles": int(r.get("niveles") or 0),
            "pasos": len(r.get("pasos") or []), "avisos": [a.get("mensaje") for a in r.get("avisos") or []][:10],
            "requisitos": [q.get("tipo") for q in r.get("requisitos") or []],
            "bloqueos": [b.get("mensaje") for b in r.get("bloqueos") or []][:10],
            "etiquetas": list(r.get("etiquetas") or []), "exceso_pct": max(pcts) if pcts else None,
            "politicas": sorted({x for x in [o.get("politica") for o in (r.get("avisos") or []) + (r.get("bloqueos") or [])
                                              + (r.get("requisitos") or []) + (r.get("avisar") or [])]
                                 + [(p.get("origen") or {}).get("politica") for p in r.get("pasos") or []]
                                 + [((r.get("origenes") or {}).get("niveles") or {}).get("politica")] if x})}


def registrar(db: Session, dominio_clave: str, entidad_id: str, evaluacion: dict, *, momento: str = "envio",
              usuario_id: Optional[str] = None, solicitud_id: Optional[str] = None,
              organization_id: Optional[str] = None) -> EvaluacionDePolitica:
    """Guarda la explicación (auditoría y «por qué» para el usuario). No hace commit."""
    fila = EvaluacionDePolitica(
        id=str(uuid.uuid4()), organization_id=organization_id or (db.info or {}).get("organization_id"),
        dominio=dominio_clave, entidad_id=str(entidad_id), momento=momento, decision=evaluacion["decision"],
        resultado=json.dumps(evaluacion["resultado"], ensure_ascii=False, default=str),
        explicacion=json.dumps({"politicas": evaluacion["explicacion"], "contexto": evaluacion.get("contexto")},
                               ensure_ascii=False, default=str),
        solicitud_id=solicitud_id, evaluado_por=usuario_id)
    db.add(fila)
    db.flush()
    return fila


def aplicar_campos(db: Session, dominio_clave: str, entidad, resultado: dict) -> list:
    """Aplica los `set_field` ganadores con el gancho del dominio. Devuelve los aplicados."""
    dominio = catalogo.dominio(dominio_clave)
    hechos = []
    if not dominio.aplicar_campo:
        return hechos
    for campo, d in (resultado.get("campos") or {}).items():
        c = dominio.campo(campo)
        if c and c.asignable:
            dominio.aplicar_campo(db, entidad, campo, d.get("valor"))
            hechos.append(campo)
    return hechos


def requisitos_pendientes(db: Session, dominio_clave: str, entidad, resultado: dict) -> list:
    """Los `require_*` que la entidad aún no cumple (según el gancho del dominio)."""
    dominio = catalogo.dominio(dominio_clave)
    if not dominio.cumple_requisito:
        return list(resultado.get("requisitos") or [])
    return [r for r in resultado.get("requisitos") or [] if not dominio.cumple_requisito(db, entidad, r)]


def _destinatarios(db: Session, d: dict, solicitante_id: Optional[str], org: Optional[str]) -> set:
    from app.models.user import User
    from app.services.approval_engine._base import responsable_de_nivel
    q = db.query(User.id).filter(User.is_active.is_(True))
    if org:
        q = q.filter(User.organization_id == org)
    t, v = d.get("tipo"), d.get("valor") or d.get("id")
    if t == "persona" and v:
        return {u for (u,) in q.filter(User.id == v).all()}
    if t == "rol" and v:
        return {u for (u,) in q.filter(User.role == v).all()}
    if t == "departamento" and v:
        return {u for (u,) in q.filter(User.department == v).all()}
    if t == "solicitante" and solicitante_id:
        return {solicitante_id}
    if t == "responsable" and solicitante_id:
        jefe = responsable_de_nivel(db, solicitante_id, int(d.get("nivel") or 1))
        return {jefe} if jefe else set()
    if t == "grupo" and v:
        from app.models.billing_reports import ApprovalGroup
        g = db.query(ApprovalGroup).filter(ApprovalGroup.id == v).first()
        return set(_json(g.member_ids, [])) if g else set()
    return set()


def ejecutar_avisos(db: Session, resultado: dict, solicitante_id: Optional[str], recurso: str,
                    recurso_id: str, resumen: str, organization_id: Optional[str]) -> int:
    """Envía los `notify` combinados por el sistema de avisos existente.

    Canales: `app` (aviso en la aplicación, respeta las preferencias), `email`
    (si el usuario lo quiere, en segundo plano) y `canal` (Slack/Teams de la
    empresa, `integrations.notify_event`). Devuelve cuántos avisos salieron.
    """
    from app.models.user import User
    from app.services.notifications import notify_user
    from app.services.preferencias_de_aviso import quiere
    n = 0
    for aviso in resultado.get("avisar") or []:
        titulo = f"Política: {aviso.get('politica') or ''}"[:255]
        cuerpo = f"{resumen} — {aviso.get('mensaje') or aviso.get('regla') or ''}"[:1000]
        ids: set = set()
        for d in aviso.get("destinatarios") or []:
            ids |= _destinatarios(db, d, solicitante_id, organization_id)
        for uid in sorted(i for i in ids if i):
            if "app" in aviso["canales"]:
                notify_user(db, uid, "system", titulo, cuerpo, resource=recurso, resource_id=recurso_id)
                n += 1
            if "email" in aviso["canales"] and quiere(db, uid, "system", "email"):
                fila = db.query(User.email).filter(User.id == uid).first()
                if fila and fila[0]:
                    from app.core.segundo_plano import encolar
                    from app.services.notification_service import send_email_notification
                    encolar(send_email_notification, fila[0], titulo, cuerpo)
                    n += 1
        if "canal" in aviso["canales"]:
            try:
                from app.services.integrations import notify_event
                notify_event("policy.matched", {"title": titulo, "summary": cuerpo, "resource": recurso,
                                                "id": recurso_id}, db, organization_id=organization_id)
                n += 1
            except Exception:
                logger.warning("no se pudo avisar al canal de la política", exc_info=True)
    return n


def condicion_de_rama(cond: dict, req) -> bool:
    """Condición de una rama del diseñador gráfico sobre el contexto de la solicitud.

    Falla hacia «la rama está activa» (pide la firma), como `_step_condition_met`.
    """
    from sqlalchemy.orm import object_session
    from app.services.approval_engine.pasos import contexto_de
    try:
        dominio = catalogo.dominio(cond.get("dominio") or "")
    except ErrorDeDominio:
        # Dominio desconocido (p. ej. quitado del registro): la rama queda activa y se avisa.
        logger.warning("condición de rama con dominio desconocido %r en la solicitud %s",
                       cond.get("dominio"), getattr(req, "id", None))
        return True
    db = object_session(req)
    ctx = contexto_de(req)
    if ctx.get("_fecha"):
        try:
            ctx["_fecha"] = date.fromisoformat(str(ctx["_fecha"])[:10])
        except ValueError:
            ctx["_fecha"] = None
    r = Evaluador(db, dominio).evaluar(cond.get("arbol"), ctx, [])
    return True if r is None else r
