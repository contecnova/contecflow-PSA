"""Simulador: qué cambiaría si esta política (borrador o sin guardar) estuviera publicada.

Rehace la evaluación de las últimas N entidades del dominio (o las de un
rango de fechas) dos veces —con las políticas publicadas hoy y con el borrador
en lugar de la versión publicada de su familia— y devuelve las diferencias.

NO escribe nada: no guarda evaluaciones, no añade pasos, no avisa a nadie. Usa
`motor.evaluar_con`, que es puro, y al terminar comprueba que la sesión no
tiene nada pendiente de escribir (si lo tuviera, deshace y falla: un
adaptador de dominio que escribe al dar el contexto es un error).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.services.politicas import catalogo, motor
from app.services.politicas.servicio import _fecha, _org, detalle, validar
from app.core.codigos_de_error import error


def _compilar_doc(doc: dict) -> dict:
    return {
        "id": doc.get("id") or "borrador", "familia_id": doc.get("familia_id") or doc.get("id") or "borrador",
        "version": doc.get("version") or 0, "nombre": doc.get("nombre") or "(borrador)",
        "prioridad": int(doc.get("prioridad") or 0), "activa": True,
        "vigente_desde": _fecha(doc.get("vigente_desde")), "vigente_hasta": _fecha(doc.get("vigente_hasta")),
        "ambito": doc.get("ambito") or {},
        "reglas": [{"id": r.get("id") or f"regla-{i + 1}", "nombre": r.get("nombre") or f"Regla {i + 1}",
                    "orden": i + 1, "condicion": r.get("condicion"), "resultados": r.get("resultados") or [],
                    "exceso": r.get("exceso"), "detener": bool(r.get("detener"))}
                   for i, r in enumerate(doc.get("reglas") or []) if r.get("activa", True)],
    }


def _huella(ev: dict) -> dict:
    r = ev["resultado"]
    return {"decision": ev["decision"], "niveles": r["niveles"], "pasos": len(r["pasos"]),
            "avisos": len(r["avisos"]), "requisitos": [q["tipo"] for q in r["requisitos"]],
            "bloqueos": [b["mensaje"] for b in r["bloqueos"]], "etiquetas": r["etiquetas"],
            "avisar": sum(len(a["destinatarios"]) for a in r["avisar"])}


def simular(db: Session, usuario, *, politica_id: Optional[str] = None, documento: Optional[dict] = None,
            ultimos: Optional[int] = None, desde: Optional[str] = None, hasta: Optional[str] = None) -> dict:
    from app.services import settings_service as s
    if documento is None and politica_id is None:
        raise error(422, "simulacion_sin_politica")
    doc = documento if documento is not None else detalle(db, politica_id)
    errores = validar(db, usuario, doc)
    if errores:
        raise ErrorDeDominio(422, {"message": "La política tiene errores", "errors": errores})
    dominio = catalogo.dominio(doc["dominio"])
    org = _org(usuario)
    tope = int(s.get_runtime_int(db, "POLICY_SIMULATION_MAX_ENTITIES", org) or 1000)
    d0, d1 = _fecha(desde), _fecha(hasta)
    n = int(ultimos or (0 if (d0 or d1) else s.get_runtime_int(db, "POLICY_SIMULATION_DEFAULT_LAST_N", org) or 100))
    limite = min(n, tope) if n else tope

    actuales, tablas = motor.publicadas(db, org, dominio.clave)
    borrador = _compilar_doc(doc)
    despues = sorted([p for p in actuales if p["familia_id"] != borrador["familia_id"]] + [borrador],
                     key=lambda c: (-c["prioridad"], c["nombre"], c["id"]))
    tablas = {**tablas, **motor.cargar_tablas(db, list(motor._tablas_usadas([borrador]) - set(tablas)))}

    entidades = dominio.historicos(db, d0, d1, limite)
    items, cambios = [], {"decision": 0, "mas_aprobacion": 0, "menos_aprobacion": 0, "nuevos_bloqueos": 0,
                          "nuevos_avisos": 0, "auto_aprobadas": 0}
    por_decision = {"antes": {}, "despues": {}}
    for e in entidades:
        ctx = dominio.contexto(db, e)
        antes = motor.evaluar_con(db, dominio, actuales, tablas, ctx)
        tras = motor.evaluar_con(db, dominio, despues, tablas, ctx)
        a, b = _huella(antes), _huella(tras)
        por_decision["antes"][a["decision"]] = por_decision["antes"].get(a["decision"], 0) + 1
        por_decision["despues"][b["decision"]] = por_decision["despues"].get(b["decision"], 0) + 1
        cambia = a != b
        if cambia:
            cambios["decision"] += a["decision"] != b["decision"]
            nivel_a, nivel_b = a["niveles"] + a["pasos"], b["niveles"] + b["pasos"]
            cambios["mas_aprobacion"] += nivel_b > nivel_a
            cambios["menos_aprobacion"] += nivel_b < nivel_a
            cambios["nuevos_bloqueos"] += b["decision"] == "block" and a["decision"] != "block"
            cambios["nuevos_avisos"] += b["avisos"] > a["avisos"]
            cambios["auto_aprobadas"] += b["decision"] == "auto_approve" and a["decision"] != "auto_approve"
        items.append({"entidad_id": e.id, "resumen": dominio.resumen(e), "fecha": _iso(ctx.get("_fecha")),
                      "cambia": cambia, "antes": a, "despues": b,
                      "explicacion": tras["explicacion"] if cambia else None})
    if db.new or db.dirty or db.deleted:
        db.rollback()
        raise error(500, "simulacion_intento_escribir")
    return {"dominio": dominio.clave, "evaluadas": len(items), "tope": tope, "cambian": sum(i["cambia"] for i in items),
            "resumen_de_cambios": cambios, "por_decision": por_decision,
            "items": sorted(items, key=lambda i: (not i["cambia"], i["fecha"] or ""), reverse=False)}


def _iso(v):
    return v.isoformat() if isinstance(v, date) else v
