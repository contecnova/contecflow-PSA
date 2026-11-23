"""Catálogo de cambios estándar del CAB (ITIL 4), 23-11-2026.

Auditoría 2026-11-22, A-SD19: un cambio se aprobaba solo porque el solicitante
declaraba el tipo `standard`. Ahora el tipo lo fija el servidor:

- un cambio es `standard` solo si referencia un modelo (`StandardChangeModel`)
  de su empresa aprobado, activo y vigente (`next_review_at` futura), cuyo
  alcance (CIs, tipos de CI, servicios) cubre los CIs afectados y cuyo riesgo
  máximo cubre el del cambio; si no, es `normal` y pasa por el CAB;
- un modelo nace `proposed` y lo aprueba como estándar alguien con
  `sd.gestionar` que sea del CAB (o administrador) y no lo haya propuesto (SoD);
- cada cierre de un cambio estándar suma éxito o fallo al modelo; por encima de
  `SD_STANDARD_CHANGE_MAX_FAILURE_PCT` (con al menos
  `SD_STANDARD_CHANGE_MIN_CLOSURES` cierres) se suspende y sus cambios vuelven
  al CAB; reactivarlo lo devuelve a `proposed` (nueva aprobación);
- altas, cambios, aprobaciones, suspensiones, reactivaciones y bajas dejan
  rastro en `audit_log`.

Documentación: docs/SERVICE_DESK.md («Cambios estándar»).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.service_desk import (
    ChangeRisk,
    ChangeType,
    ConfigurationItem,
    ESTADO_MODELO_APROBADO,
    ESTADO_MODELO_PROPUESTO,
    ESTADO_MODELO_RETIRADO,
    ESTADO_MODELO_SUSPENDIDO,
    ITSMChangeRequest,
    StandardChangeModel,
)
from app.models.user import User

#: Orden de los riesgos para comparar el del cambio con el máximo del modelo.
ORDEN_DE_RIESGO = {r.value: i for i, r in enumerate((ChangeRisk.low, ChangeRisk.medium,
                                                      ChangeRisk.high, ChangeRisk.critical))}
#: Campos que definen lo que el CAB aprobó: si cambian, el modelo vuelve a `proposed`.
CAMPOS_SUSTANCIALES = ("procedure", "rollback_plan", "test_plan", "max_risk",
                       "applies_to_ci_ids", "applies_to_ci_types", "applies_to_service_ids")
CAMPOS_EDITABLES = ("name", "description", "review_interval_days") + CAMPOS_SUSTANCIALES
_LISTAS = ("applies_to_ci_ids", "applies_to_ci_types", "applies_to_service_ids")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _valor(x):
    return getattr(x, "value", x)


def _lista(raw) -> list:
    try:
        v = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(i) for i in v] if isinstance(v, list) else []


def _ajuste_int(db: Session, clave: str, org_id) -> int:
    from app.services import settings_service as _ss
    return int(_ss.get_runtime_int(db, clave, org_id))


# ── consulta ────────────────────────────────────────────────────────────────

def _query_de_empresa(db: Session, usuario: User):
    q = db.query(StandardChangeModel)
    if not usuario.is_superadmin:
        q = q.filter(StandardChangeModel.organization_id == usuario.organization_id)
    return q


def obtener_modelo(db: Session, usuario: User, modelo_id: str) -> StandardChangeModel:
    modelo = _query_de_empresa(db, usuario).filter(StandardChangeModel.id == modelo_id).first()
    if not modelo:
        raise error(404, "no_encontrado", que="modelo_de_cambio_estandar")
    return modelo


def vigente(modelo: StandardChangeModel, ahora: Optional[datetime] = None) -> bool:
    """Aprobado, activo y con la revisión periódica sin vencer."""
    ahora = ahora or _ahora()
    proxima = _aware(modelo.next_review_at)
    return (bool(modelo.is_active) and modelo.status == ESTADO_MODELO_APROBADO
            and (proxima is None or proxima > ahora))


def tasa_de_fallo(modelo: StandardChangeModel) -> Optional[float]:
    cierres = (modelo.success_count or 0) + (modelo.failure_count or 0)
    return round(100.0 * (modelo.failure_count or 0) / cierres, 1) if cierres else None


def serializar_modelo(modelo: StandardChangeModel) -> dict:
    return {
        "id": modelo.id,
        "name": modelo.name,
        "description": modelo.description,
        "procedure": modelo.procedure,
        "rollback_plan": modelo.rollback_plan,
        "test_plan": modelo.test_plan,
        "max_risk": modelo.max_risk,
        "applies_to_ci_ids": _lista(modelo.applies_to_ci_ids),
        "applies_to_ci_types": _lista(modelo.applies_to_ci_types),
        "applies_to_service_ids": _lista(modelo.applies_to_service_ids),
        "status": modelo.status,
        "is_active": bool(modelo.is_active),
        "vigente": vigente(modelo),
        "caducado": modelo.status == ESTADO_MODELO_APROBADO and not vigente(modelo) and bool(modelo.is_active),
        "proposed_by": modelo.proposed_by,
        "proposer": getattr(modelo.proposer, "full_name", None),
        "approved_by": modelo.approved_by,
        "approver": getattr(modelo.approver, "full_name", None),
        "approved_at": modelo.approved_at.isoformat() if modelo.approved_at else None,
        "review_interval_days": modelo.review_interval_days,
        "next_review_at": modelo.next_review_at.isoformat() if modelo.next_review_at else None,
        "suspended_at": modelo.suspended_at.isoformat() if modelo.suspended_at else None,
        "suspended_reason": modelo.suspended_reason,
        "use_count": modelo.use_count or 0,
        "success_count": modelo.success_count or 0,
        "failure_count": modelo.failure_count or 0,
        "failure_rate_pct": tasa_de_fallo(modelo),
        "created_at": modelo.created_at.isoformat() if modelo.created_at else None,
    }


def listar_modelos(db: Session, usuario: User, solo_vigentes: bool = False,
                   incluir_bajas: bool = False) -> list[dict]:
    q = _query_de_empresa(db, usuario)
    if not incluir_bajas:
        q = q.filter(StandardChangeModel.is_active == True)  # noqa: E712
    modelos = q.order_by(StandardChangeModel.name, StandardChangeModel.id).all()
    if solo_vigentes:
        ahora = _ahora()
        modelos = [m for m in modelos if vigente(m, ahora)]
    return [serializar_modelo(m) for m in modelos]


# ── alta, edición y ciclo de vida ───────────────────────────────────────────

def _normalizar(datos: dict) -> dict:
    limpio = {}
    for campo in CAMPOS_EDITABLES:
        if campo not in datos:
            continue
        valor = datos[campo]
        if campo in _LISTAS:
            valor = json.dumps([str(v) for v in (valor or [])])
        elif campo == "max_risk":
            if valor not in ORDEN_DE_RIESGO:
                raise error(422, "estado_no_valido", estado=valor)
        elif campo == "review_interval_days" and valor is not None:
            valor = int(valor)
            if valor < 1:
                raise error(422, "cambio_estandar_revision_no_valida")
        limpio[campo] = valor
    return limpio


def _auditar(db: Session, usuario: Optional[User], accion: str, modelo: StandardChangeModel,
             detalle: Optional[dict] = None) -> None:
    from app.services.audit import audit_log
    audit_log(db, usuario, {"alta": "CREATE", "baja": "DELETE"}.get(accion, "UPDATE"), "sd_standard_change_model",
              modelo.id, modelo.name, metadata={"accion": accion, "status": modelo.status, **(detalle or {})})


def proponer_modelo(db: Session, usuario: User, datos: dict) -> StandardChangeModel:
    limpio = _normalizar(datos)
    if not (limpio.get("name") or "").strip() or not (limpio.get("procedure") or "").strip():
        raise error(422, "campos_obligatorios", campos="name, procedure")
    modelo = StandardChangeModel(organization_id=usuario.organization_id, proposed_by=usuario.id,
                                 status=ESTADO_MODELO_PROPUESTO, is_active=True, **limpio)
    db.add(modelo)
    db.flush()
    _auditar(db, usuario, "alta", modelo)
    return modelo


def editar_modelo(db: Session, usuario: User, modelo_id: str, datos: dict) -> StandardChangeModel:
    modelo = obtener_modelo(db, usuario, modelo_id)
    if modelo.status == ESTADO_MODELO_RETIRADO:
        raise error(409, "cambio_estandar_retirado")
    limpio = _normalizar(datos)
    sustancial = any(c in limpio and limpio[c] != getattr(modelo, c) for c in CAMPOS_SUSTANCIALES)
    for campo, valor in limpio.items():
        setattr(modelo, campo, valor)
    if sustancial and modelo.status == ESTADO_MODELO_APROBADO:
        # Lo aprobado era otro procedimiento: vuelve a pasar por el CAB.
        modelo.status = ESTADO_MODELO_PROPUESTO
        modelo.approved_by = modelo.approved_at = modelo.next_review_at = None
    _auditar(db, usuario, "edicion", modelo, {"campos": sorted(limpio), "vuelve_a_cab": sustancial})
    return modelo


def _es_del_cab_o_admin(db: Session, usuario: User) -> bool:
    if usuario.is_superadmin or _valor(usuario.role) == "admin":
        return True
    from app.models.service_desk import AgentGroupMember
    from app.services import settings_service as _ss
    grupo = _ss.get_runtime_str(db, "SD_CAB_GROUP_ID", usuario.organization_id)
    if not grupo:
        return False
    return db.query(AgentGroupMember).filter(AgentGroupMember.group_id == grupo,
                                             AgentGroupMember.user_id == usuario.id).first() is not None


def aprobar_modelo(db: Session, usuario: User, modelo_id: str) -> StandardChangeModel:
    """El CAB lo declara estándar: desde ahora sus cambios no pasan por el comité."""
    modelo = obtener_modelo(db, usuario, modelo_id)
    if modelo.status != ESTADO_MODELO_PROPUESTO or not modelo.is_active:
        raise error(409, "cambio_estandar_no_propuesto")
    if not _es_del_cab_o_admin(db, usuario):
        raise error(403, "cambio_estandar_solo_cab")
    from app.services.approval_engine._base import exigir_que_no_sea_suyo
    exigir_que_no_sea_suyo(db, modelo.proposed_by, usuario, "itsm_change", modelo.id)  # mismo modulo GRC que el cambio
    ahora = _ahora()
    dias = modelo.review_interval_days or _ajuste_int(db, "SD_STANDARD_CHANGE_REVIEW_DAYS", modelo.organization_id)
    modelo.status = ESTADO_MODELO_APROBADO
    modelo.approved_by, modelo.approved_at = usuario.id, ahora
    modelo.next_review_at = ahora + timedelta(days=dias)
    modelo.suspended_at = modelo.suspended_reason = None
    _auditar(db, usuario, "aprobacion", modelo, {"proxima_revision": modelo.next_review_at.isoformat()})
    return modelo


def suspender_modelo(db: Session, usuario: Optional[User], modelo: StandardChangeModel, motivo: str,
                     automatica: bool = False) -> StandardChangeModel:
    if modelo.status == ESTADO_MODELO_RETIRADO:
        raise error(409, "cambio_estandar_retirado")
    modelo.status = ESTADO_MODELO_SUSPENDIDO
    modelo.suspended_at = _ahora()
    modelo.suspended_reason = motivo
    _auditar(db, usuario, "suspension", modelo, {"motivo": motivo, "automatica": automatica,
                                                 "tasa_de_fallo": tasa_de_fallo(modelo)})
    return modelo


def reactivar_modelo(db: Session, usuario: User, modelo_id: str) -> StandardChangeModel:
    """Un suspendido vuelve a `proposed`: necesita otra aprobación del CAB.
    Los contadores de cierre empiezan de cero (nuevo periodo de medida)."""
    modelo = obtener_modelo(db, usuario, modelo_id)
    if modelo.status != ESTADO_MODELO_SUSPENDIDO:
        raise error(409, "cambio_estandar_no_suspendido")
    modelo.status = ESTADO_MODELO_PROPUESTO
    modelo.approved_by = modelo.approved_at = modelo.next_review_at = None
    modelo.success_count = modelo.failure_count = 0
    _auditar(db, usuario, "reactivacion", modelo)
    return modelo


def retirar_modelo(db: Session, usuario: User, modelo_id: str) -> StandardChangeModel:
    """Baja lógica: los cambios que lo referencian conservan la referencia."""
    modelo = obtener_modelo(db, usuario, modelo_id)
    modelo.status = ESTADO_MODELO_RETIRADO
    modelo.is_active = False
    _auditar(db, usuario, "baja", modelo)
    return modelo


# ── el cambio y su modelo ───────────────────────────────────────────────────

def _cis_del_servicio(db: Session, servicios: list[str]) -> set[str]:
    """Los servicios y los CIs relacionados con ellos en la CMDB (un salto)."""
    if not servicios:
        return set()
    from app.models.service_desk import CIRelation
    filas = db.query(CIRelation.source_ci_id, CIRelation.target_ci_id).filter(
        (CIRelation.source_ci_id.in_(servicios)) | (CIRelation.target_ci_id.in_(servicios))).all()
    return set(servicios) | {x for f in filas for x in f}


def motivo_de_no_estandar(db: Session, change: ITSMChangeRequest,
                          modelo: Optional[StandardChangeModel]) -> Optional[str]:
    """Por qué el cambio NO puede ir como estándar con ese modelo; None si puede."""
    if modelo is None:
        return "sin_modelo"
    if modelo.organization_id != change.organization_id:
        return "otra_empresa"
    if modelo.status == ESTADO_MODELO_SUSPENDIDO:
        return "suspendido"
    if not modelo.is_active or modelo.status == ESTADO_MODELO_RETIRADO:
        return "retirado"
    if modelo.status != ESTADO_MODELO_APROBADO:
        return "sin_aprobar"
    if not vigente(modelo):
        return "caducado"
    riesgo = _valor(change.risk) or ChangeRisk.medium.value
    if ORDEN_DE_RIESGO.get(riesgo, 99) > ORDEN_DE_RIESGO.get(modelo.max_risk, -1):
        return "riesgo"
    ids, tipos, servicios = (_lista(modelo.applies_to_ci_ids), _lista(modelo.applies_to_ci_types),
                             _lista(modelo.applies_to_service_ids))
    if ids or tipos or servicios:
        try:
            afectados = [str(x) for x in json.loads(change.affected_cis or "[]")]
        except (TypeError, ValueError):
            afectados = []
        if not afectados:
            return "fuera_de_alcance"
        cis = {ci.id: ci for ci in db.query(ConfigurationItem).filter(ConfigurationItem.id.in_(afectados)).all()}
        del_servicio = _cis_del_servicio(db, servicios)
        for ci_id in afectados:
            ci = cis.get(ci_id)
            if ci is None or ci.organization_id != change.organization_id:
                return "fuera_de_alcance"
            if not (ci_id in ids or _valor(ci.ci_type) in tipos or ci_id in del_servicio):
                return "fuera_de_alcance"
    return None


def aplicar_tipo_pedido(db: Session, usuario: User, change: ITSMChangeRequest, payload: dict) -> None:
    """Fija `change_type` y `standard_model_id` desde lo que pide el cliente.

    `standard` exige `standard_model_id` de un modelo que encaje (409 con el
    motivo si no); `normal`/`emergency` se aceptan tal cual y sueltan el modelo.
    Con el modelo, la plantilla rellena los planes que vengan vacíos.
    """
    if "change_type" not in payload and "standard_model_id" not in payload:
        return
    pedido = payload.get("change_type") or (ChangeType.standard.value if payload.get("standard_model_id")
                                            else _valor(change.change_type) or ChangeType.normal.value)
    if pedido not in {t.value for t in ChangeType}:
        raise error(422, "estado_no_valido", estado=pedido)
    if pedido != ChangeType.standard.value:
        change.change_type = pedido
        change.standard_model_id = None
        return
    modelo_id = payload.get("standard_model_id") or change.standard_model_id
    if not modelo_id:
        raise error(422, "cambio_estandar_sin_modelo")
    modelo = obtener_modelo(db, usuario, modelo_id)
    if change.organization_id is None:
        change.organization_id = modelo.organization_id
    motivo = motivo_de_no_estandar(db, change, modelo)
    if motivo:
        raise error(409, "cambio_estandar_no_aplica", motivo=motivo)
    change.change_type = ChangeType.standard.value
    change.standard_model_id = modelo.id
    if not change.implementation_plan:
        change.implementation_plan = modelo.procedure
    if not change.rollback_plan:
        change.rollback_plan = modelo.rollback_plan
    if not change.test_plan:
        change.test_plan = modelo.test_plan


def puede_aprobarse_como_estandar(db: Session, change: ITSMChangeRequest) -> bool:
    """Lo que decide la auto-aprobación. Si ya no encaja (modelo suspendido,
    caducado, fuera de alcance), el servidor lo pasa a `normal`: irá al CAB."""
    if _valor(change.change_type) != ChangeType.standard.value:
        return False
    modelo = db.get(StandardChangeModel, change.standard_model_id) if change.standard_model_id else None
    if motivo_de_no_estandar(db, change, modelo) is not None:
        change.change_type = ChangeType.normal.value
        return False
    return True


def anotar_uso(change: ITSMChangeRequest) -> None:
    modelo = change.standard_model
    if modelo is not None:
        modelo.use_count = (modelo.use_count or 0) + 1


def anotar_cierre(db: Session, change: ITSMChangeRequest, exito: bool, usuario: Optional[User]) -> None:
    """Suma el cierre al modelo y lo suspende si su tasa de fallo pasa del umbral."""
    if _valor(change.change_type) != ChangeType.standard.value or not change.standard_model_id:
        return
    modelo = db.get(StandardChangeModel, change.standard_model_id)
    if modelo is None:
        return
    if exito:
        modelo.success_count = (modelo.success_count or 0) + 1
    else:
        modelo.failure_count = (modelo.failure_count or 0) + 1
    if modelo.status != ESTADO_MODELO_APROBADO:
        return
    cierres = (modelo.success_count or 0) + (modelo.failure_count or 0)
    minimo = _ajuste_int(db, "SD_STANDARD_CHANGE_MIN_CLOSURES", modelo.organization_id)
    maximo = _ajuste_int(db, "SD_STANDARD_CHANGE_MAX_FAILURE_PCT", modelo.organization_id)
    tasa = tasa_de_fallo(modelo)
    if cierres >= minimo and tasa is not None and tasa > maximo:
        suspender_modelo(db, usuario, modelo, f"tasa_de_fallo:{tasa}>{maximo}", automatica=True)
