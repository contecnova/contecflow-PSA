"""Dominio `demanda` del motor de políticas (flujo de demanda, migración 195).

Las puertas y las fases condicionales de un flujo de demanda pueden preguntar
al motor de políticas (`use_policies`): si una política publicada devuelve
«revisar» (o bloquear) o pone la etiqueta `comite`, la puerta pide comité.
Ejemplos de reglas (Configuración → Políticas, dominio «Demanda»):

  · «Coste > 50000» → revisar (al comité);
  · «Impacto estratégico es alto» → etiqueta comite;
  · «Tipo es new_feature Y Independiente» → +1 nivel o aviso.

Los valores salen de los campos del flujo marcados con `policy_field`
(`coste`, `esfuerzo`, `roi`, `impacto`, `transversal`); los demás, del expediente.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.services.politicas.registro import Campo, Dominio, Opcion, registrar

_NUM = ("gt", "gte", "lt", "lte", "eq", "ne", "between")

CAMPOS = [
    Campo("tipo", "Tipo de solicitud", "texto"),
    Campo("origen", "Canal", "enum", opciones=(Opcion("client_portal", "Portal de clientes"),
                                               Opcion("internal_portal", "Portal interno"),
                                               Opcion("operator", "Operador"),
                                               Opcion("supplier_portal", "Portal del proveedor"))),
    Campo("independiente", "Iniciativa independiente (sin proyecto)", "booleano"),
    Campo("coste", "Coste estimado", "numero", operadores=_NUM),
    Campo("esfuerzo", "Esfuerzo (horas)", "numero", operadores=_NUM),
    Campo("roi", "ROI estimado (%)", "numero", operadores=_NUM),
    Campo("impacto", "Impacto estratégico", "enum", opciones=(Opcion("bajo", "Bajo"), Opcion("medio", "Medio"),
                                                              Opcion("alto", "Alto"))),
    Campo("transversal", "Transversal", "booleano"),
    Campo("proyecto", "Proyecto", "entidad", entidad="proyecto"),
    Campo("persona", "Quién pide", "entidad", entidad="usuario"),
]


def contexto(db, req) -> dict:
    from app.services.demanda import definicion as D
    from app.services.demanda.motor import datos_de, flujo_de
    defn = flujo_de(req)
    datos = datos_de(req)

    def valor(alias):
        clave = D.campo_de_politica(defn, alias)
        return datos.get(clave) if clave else None

    def numero(alias):
        try:
            v = valor(alias)
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    transversal = valor("transversal")
    return {"tipo": req.type_key, "origen": req.origin, "independiente": bool(req.standalone),
            "coste": numero("coste"), "esfuerzo": numero("esfuerzo"), "roi": numero("roi"),
            "impacto": valor("impacto"), "transversal": transversal in (True, "true", "1", 1),
            "proyecto": req.project_id, "persona": req.requester_user_id,
            "_sujeto": {"user_id": req.requester_user_id}, "_fecha": date.today()}


def cargar(db, entidad_id: str):
    from app.models.demanda import DemandRequest
    return db.query(DemandRequest).filter(DemandRequest.id == entidad_id).first()


def historicos(db, desde: Optional[date], hasta: Optional[date], limite: int) -> list:
    from app.models.demanda import DemandRequest
    q = db.query(DemandRequest).filter(DemandRequest.status != "draft")
    if desde:
        q = q.filter(DemandRequest.created_at >= desde)
    if hasta:
        q = q.filter(DemandRequest.created_at <= hasta)
    return q.order_by(DemandRequest.created_at.desc()).limit(limite).all()


def resumen(req) -> str:
    return f"{req.code} · {req.title}"


registrar(Dominio(
    clave="demanda", etiqueta="Demanda", campos=CAMPOS, contexto=contexto, cargar=cargar, historicos=historicos,
    propietario=lambda r: r.requester_user_id, resumen=resumen, tipo_de_aprobacion="demand_step",
))
