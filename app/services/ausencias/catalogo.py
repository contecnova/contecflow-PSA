"""Tipos de ausencia y de documento, requisitos documentales y acceso especial.

Los tipos sustituyen al enum `AbsenceType` (revisión 167). Cada empresa tiene
los siete de sistema (la migración los creó; una empresa nueva los recibe la
primera vez que se consultan, `asegurar`) más los que defina. `absences.type`
sigue guardando la CLAVE del tipo, así que el API antiguo (`type: "vacation"`)
sigue valiendo.

Todas las funciones que escriben confirman (`commit`).
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.services.formato_regional import IDIOMA_DE_RESPALDO
from app.models.ausencias import (AccesoEspecialAusencias, RequisitoDocumentalDeTipo, TipoDeAusencia,
                                  TipoDeDocumentoDeAusencia)

UNIDADES = ("dias", "medios_dias", "horas")
VISIBILIDADES = ("todos", "equipo", "privada")
SALDOS = ("vacaciones", "propio", "bolsa")
#: Rev. 180: cómo se puede pedir un tipo (días enteros, medio día, horas con franja).
MODOS = ("dias", "medio_dia", "horas")
PERIODOS = ("anual", "semestral", "trimestral", "mensual", "sin_periodo")
#: Reglas de la bolsa de horas (todas números ≥ 0; ver `ausencias/bolsa.py`).
BOLSA_CLAVES = ("factor", "factor_festivo", "factor_no_laborable", "umbral_minutos", "tope_diario", "tope_periodo")
BOLSA_DEFECTO = {"factor": 1.0, "factor_festivo": 1.0, "factor_no_laborable": 1.0, "umbral_minutos": 0,
                 "tope_diario": None, "tope_periodo": None, "solo_aprobadas": False,
                 "solo_horas_extra": False}
PLAZO_DESDE = ("solicitud", "inicio", "fin")
#: Iconos que la pantalla sabe pintar (nombres de lucide en `IconoDeAusencia`).
ICONOS = ("umbrella", "sun", "stethoscope", "user", "graduation", "baby", "circle", "plane", "heart", "home",
          "briefcase", "clock", "calendar", "book", "shield", "coffee")
IDIOMAS = ("es", "en", "zh")
_CLAVE = re.compile(r"^[a-z0-9_]{2,50}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

#: Los tipos de sistema (las claves del enum antiguo). Los mismos que crea la 167.
TIPOS_DE_SISTEMA = (
    ("vacation", {"es": "Vacaciones", "en": "Vacation", "zh": "休假"}, "#2fb37f", "sun", True, "vacaciones", "equipo", False, 10),
    ("sick", {"es": "Baja médica", "en": "Sick leave", "zh": "病假"}, "#e5534b", "stethoscope", False, None, "privada", True, 20),
    ("personal", {"es": "Asunto personal", "en": "Personal", "zh": "事假"}, "#8b6cf6", "user", False, None, "equipo", False, 30),
    ("training", {"es": "Formación", "en": "Training", "zh": "培训"}, "#3b82f6", "graduation", False, None, "todos", False, 40),
    ("maternity", {"es": "Maternidad", "en": "Maternity", "zh": "产假"}, "#ec4899", "baby", False, None, "privada", True, 50),
    ("paternity", {"es": "Paternidad", "en": "Paternity", "zh": "陪产假"}, "#06b6d4", "baby", False, None, "privada", False, 60),
    ("other", {"es": "Otro", "en": "Other", "zh": "其他"}, "#7a8aaa", "circle", False, None, "equipo", False, 70),
)
DOCUMENTOS_DE_SISTEMA = (
    ("parte_de_baja", {"es": "Parte de baja", "en": "Sick-leave certificate", "zh": "病假证明"}, True, 10),
    ("parte_de_confirmacion", {"es": "Parte de confirmación", "en": "Extension report", "zh": "续假证明"}, True, 20),
    ("justificante", {"es": "Justificante", "en": "Supporting document", "zh": "证明文件"}, False, 30),
)


def _org(db: Session, usuario=None) -> Optional[str]:
    return getattr(usuario, "organization_id", None) or (db.info or {}).get("organization_id")


def _json(v, defecto):
    try:
        return json.loads(v) if v else defecto
    except ValueError:
        return defecto


def asegurar(db: Session, org: Optional[str]) -> None:
    """Los tipos y documentos de sistema de una empresa nueva (la 167 ya los creó en las que había)."""
    if not org:
        return
    if db.query(TipoDeAusencia.id).filter(TipoDeAusencia.organization_id == org).first() is None:
        for clave, nombres, color, icono, descuenta, saldo, vis, especiales, orden in TIPOS_DE_SISTEMA:
            db.add(TipoDeAusencia(id=str(uuid.uuid4()), organization_id=org, clave=clave, nombre=nombres[IDIOMA_DE_RESPALDO],
                                  nombres=json.dumps(nombres, ensure_ascii=False), color=color, icono=icono,
                                  descuenta_saldo=descuenta, saldo=saldo, unidad="dias", visibilidad=vis,
                                  requiere_aprobacion=True, requiere_sustituto=False, datos_especiales=especiales,
                                  activo=True, orden=orden, de_sistema=True))
    if db.query(TipoDeDocumentoDeAusencia.id).filter(TipoDeDocumentoDeAusencia.organization_id == org).first() is None:
        for clave, nombres, especial, orden in DOCUMENTOS_DE_SISTEMA:
            db.add(TipoDeDocumentoDeAusencia(id=str(uuid.uuid4()), organization_id=org, clave=clave,
                                             nombre=nombres[IDIOMA_DE_RESPALDO], nombres=json.dumps(nombres, ensure_ascii=False),
                                             categoria_especial=especial, activo=True, orden=orden))
    if db.new:
        db.commit()


# ── Tipos de ausencia ────────────────────────────────────────────────────────

def tipos(db: Session, *, incluir_inactivos: bool = False, usuario=None) -> list[TipoDeAusencia]:
    # 18-11-2026: un superadministrador no lleva empresa en la sesión (ve todas),
    # así que la empresa sale de su ficha: sin esto no se creaban los tipos de
    # sistema y la lista salía vacía (el formulario «Pedir ausencia» sin tipo).
    org = _org(db, usuario) if usuario is not None and not (db.info or {}).get("organization_id") else _org(db)
    asegurar(db, org)
    q = db.query(TipoDeAusencia)
    if org:
        q = q.filter(TipoDeAusencia.organization_id == org)
    if not incluir_inactivos:
        q = q.filter(TipoDeAusencia.activo.is_(True))
    return q.order_by(TipoDeAusencia.orden, TipoDeAusencia.nombre).all()


def tipo(db: Session, tipo_id: str) -> TipoDeAusencia:
    t = db.query(TipoDeAusencia).filter(TipoDeAusencia.id == tipo_id).first()
    if t is None:
        raise ErrorDeDominio(404, "Tipo de ausencia no encontrado")
    return t


def tipo_por_clave(db: Session, clave: str) -> Optional[TipoDeAusencia]:
    asegurar(db, _org(db))
    return db.query(TipoDeAusencia).filter(TipoDeAusencia.clave == str(clave)).first()


def resolver_tipo(db: Session, *, tipo_id: Optional[str] = None, clave: Optional[str] = None) -> TipoDeAusencia:
    """El tipo de una petición: por id (pantalla nueva) o por clave (API antiguo, `type`)."""
    t = tipo(db, tipo_id) if tipo_id else (tipo_por_clave(db, clave) if clave else None)
    if t is None:
        raise ErrorDeDominio(422, f"Tipo de ausencia desconocido: {clave or tipo_id}")
    if not t.activo:
        raise ErrorDeDominio(422, f"El tipo «{t.nombre}» está desactivado")
    return t


def requisito_dict(r: RequisitoDocumentalDeTipo) -> dict:
    return {"id": r.id, "tipo_de_documento_id": r.tipo_de_documento_id, "obligatorio": bool(r.obligatorio),
            "plazo_dias": r.plazo_dias, "plazo_desde": r.plazo_desde, "repetir_cada_dias": r.repetir_cada_dias,
            "recordar_dias_antes": r.recordar_dias_antes, "escalar_dias_despues": r.escalar_dias_despues,
            "escalar_a": _json(r.escalar_a, []), "orden": r.orden}


def modos_de(t: TipoDeAusencia) -> list[str]:
    """Los modos de petición del tipo (por defecto, según su unidad)."""
    m = [x for x in _json(getattr(t, "modos", None), []) if x in MODOS]
    if m:
        return m
    return ["horas"] if t.unidad == "horas" else ["dias", "medio_dia"]


def bolsa_de(t: TipoDeAusencia) -> dict:
    return {**BOLSA_DEFECTO, **(_json(getattr(t, "bolsa", None), {}) or {})}


def tipo_dict(t: TipoDeAusencia, *, con_requisitos: bool = True) -> dict:
    d = {"id": t.id, "clave": t.clave, "nombre": t.nombre, "nombres": _json(t.nombres, {}), "color": t.color,
         "icono": t.icono, "descuenta_saldo": bool(t.descuenta_saldo), "saldo": t.saldo, "cupo_anual": t.cupo_anual,
         "unidad": t.unidad, "visibilidad": t.visibilidad, "workflow_id": t.workflow_id,
         "requiere_aprobacion": bool(t.requiere_aprobacion), "requiere_sustituto": bool(t.requiere_sustituto),
         "datos_especiales": bool(t.datos_especiales), "activo": bool(t.activo), "orden": t.orden,
         "de_sistema": bool(t.de_sistema), "modos": modos_de(t), "retribuido": bool(getattr(t, "retribuido", True)),
         "periodo_saldo": getattr(t, "periodo_saldo", None) or "anual",
         "inicio_periodo_mes": int(getattr(t, "inicio_periodo_mes", None) or 1), "arrastre_max": t.arrastre_max,
         "arrastre_caduca_meses": t.arrastre_caduca_meses, "caduca_meses": t.caduca_meses,
         "prorratear_alta": bool(t.prorratear_alta), "derecho_tabla_id": t.derecho_tabla_id,
         "bolsa": bolsa_de(t) if t.saldo == "bolsa" else None}
    if con_requisitos:
        d["requisitos"] = [requisito_dict(r) for r in t.requisitos or []]
    return d


def nombre_en(t, lang: Optional[str]) -> str:
    """El nombre del tipo (o del tipo de documento) en el idioma pedido, o el principal."""
    return (_json(getattr(t, "nombres", None), {}) or {}).get(lang or "") or t.nombre


def _nombres(datos: dict) -> dict:
    nombres = {k: str(v).strip()[:120] for k, v in (datos.get("nombres") or {}).items() if k in IDIOMAS and str(v or "").strip()}
    if not (datos.get("nombre") or "").strip() and not nombres:
        raise ErrorDeDominio(422, "El tipo necesita un nombre")
    return nombres


def _validar_tipo(db: Session, datos: dict, actual: Optional[TipoDeAusencia]) -> dict:
    errores: list[str] = []
    clave = (datos.get("clave") or (actual.clave if actual else "")).strip()
    if not _CLAVE.match(clave):
        errores.append("la clave va en minúsculas, números y _ (2 a 50)")
    elif actual is None or clave != actual.clave:
        if actual is not None and actual.de_sistema:
            errores.append("la clave de un tipo de sistema no cambia")
        elif db.query(TipoDeAusencia.id).filter(TipoDeAusencia.clave == clave).first():
            errores.append(f"ya hay un tipo con la clave {clave}")
    if datos.get("color") and not _COLOR.match(datos["color"]):
        errores.append("color no válido (#rrggbb)")
    if datos.get("icono") and datos["icono"] not in ICONOS:
        errores.append("icono desconocido")
    unidad = datos.get("unidad") or (actual.unidad if actual else "dias")
    if unidad not in UNIDADES:
        errores.append("unidad desconocida")
    if (datos.get("visibilidad") or "equipo") not in VISIBILIDADES:
        errores.append("visibilidad desconocida")
    descuenta = bool(datos.get("descuenta_saldo"))
    saldo = datos.get("saldo") if descuenta else None
    if descuenta and saldo not in SALDOS:
        errores.append("elige de qué saldo descuenta")
    if saldo == "propio" and (datos.get("cupo_anual") is None or float(datos.get("cupo_anual") or 0) <= 0) \
            and not datos.get("derecho_tabla_id"):
        errores.append("indica el cupo por periodo (o la tabla de referencia de la que sale)")
    modos = [m for m in (datos.get("modos") or []) if m]
    if any(m not in MODOS for m in modos):
        errores.append("modo de petición desconocido")
    if (datos.get("periodo_saldo") or "anual") not in PERIODOS:
        errores.append("periodo de saldo desconocido")
    if not 1 <= int(datos.get("inicio_periodo_mes") or 1) <= 12:
        errores.append("el periodo empieza en un mes del 1 al 12")
    for campo in ("arrastre_max", "arrastre_caduca_meses", "caduca_meses"):
        if datos.get(campo) not in (None, "") and float(datos[campo]) < 0:
            errores.append(f"{campo} no puede ser negativo")
    if datos.get("derecho_tabla_id"):
        from app.models.politicas import TablaDeReferencia
        tabla = db.query(TablaDeReferencia).filter(TablaDeReferencia.id == datos["derecho_tabla_id"]).first()
        if tabla is None or tabla.tipo_de_valor != "numero":
            errores.append("la tabla del derecho tiene que existir y ser de números")
    if saldo == "bolsa":
        for k, v in (datos.get("bolsa") or {}).items():
            if k in ("solo_aprobadas", "solo_horas_extra"):
                continue
            if k not in BOLSA_CLAVES:
                errores.append(f"regla de bolsa desconocida: {k}")
            elif v not in (None, "") and float(v) < 0:
                errores.append(f"bolsa: {k} no puede ser negativo")
    if datos.get("workflow_id"):
        from app.models.billing_reports import ApprovalWorkflow
        wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == datos["workflow_id"]).first()
        if wf is None or wf.entity_type != "leave":
            errores.append("el flujo tiene que ser de ausencias (leave)")
    for i, r in enumerate(datos.get("requisitos") or []):
        if not r.get("tipo_de_documento_id") or db.query(TipoDeDocumentoDeAusencia.id).filter(
                TipoDeDocumentoDeAusencia.id == r["tipo_de_documento_id"]).first() is None:
            errores.append(f"documento {i + 1}: elige el tipo de documento")
        if (r.get("plazo_desde") or "inicio") not in PLAZO_DESDE:
            errores.append(f"documento {i + 1}: ¿desde cuándo cuenta el plazo?")
        if int(r.get("plazo_dias") if r.get("plazo_dias") is not None else 0) < 0:
            errores.append(f"documento {i + 1}: el plazo no puede ser negativo")
        if r.get("repetir_cada_dias") not in (None, "") and int(r["repetir_cada_dias"]) < 1:
            errores.append(f"documento {i + 1}: la repetición es de 1 día o más")
    if errores:
        raise ErrorDeDominio(422, {"message": "El tipo tiene errores", "errors": errores})
    return {"clave": clave, "unidad": unidad, "saldo": saldo, "descuenta": descuenta}


def guardar_tipo(db: Session, usuario, datos: dict, tipo_id: Optional[str] = None) -> dict:
    # Los de sistema antes del primer tipo propio: `asegurar` solo siembra una empresa sin ninguno.
    asegurar(db, _org(db, usuario))
    actual = tipo(db, tipo_id) if tipo_id else None
    nombres = _nombres(datos)
    v = _validar_tipo(db, datos, actual)
    t = actual or TipoDeAusencia(id=str(uuid.uuid4()), organization_id=_org(db, usuario), de_sistema=False)
    t.clave = v["clave"]
    t.nombres = json.dumps(nombres, ensure_ascii=False) if nombres else None
    t.nombre = (datos.get("nombre") or "").strip()[:120] or nombres.get(IDIOMA_DE_RESPALDO) or next(iter(nombres.values()))
    t.color = datos.get("color") or t.color or "#4f8cff"
    t.icono = datos.get("icono") or t.icono or "umbrella"
    t.descuenta_saldo = v["descuenta"]
    t.saldo = v["saldo"]
    t.cupo_anual = float(datos["cupo_anual"]) if v["saldo"] == "propio" and datos.get("cupo_anual") not in (None, "") \
        else None
    modos = [m for m in (datos.get("modos") or []) if m in MODOS]
    t.modos = json.dumps(modos) if modos else None
    t.retribuido = bool(datos.get("retribuido", True))
    t.periodo_saldo = datos.get("periodo_saldo") or ("sin_periodo" if v["saldo"] == "bolsa" else "anual")
    t.inicio_periodo_mes = int(datos.get("inicio_periodo_mes") or 1)

    def _num(clave, entero=False):
        x = datos.get(clave)
        return None if x in (None, "") else (int(x) if entero else float(x))
    t.arrastre_max = _num("arrastre_max")
    t.arrastre_caduca_meses = _num("arrastre_caduca_meses", True)
    t.caduca_meses = _num("caduca_meses", True)
    t.prorratear_alta = bool(datos.get("prorratear_alta"))
    t.derecho_tabla_id = datos.get("derecho_tabla_id") or None
    t.bolsa = json.dumps({k: datos["bolsa"][k] for k in (*BOLSA_CLAVES, "solo_aprobadas", "solo_horas_extra") if k in (datos.get("bolsa") or {})}) \
        if v["saldo"] == "bolsa" else None
    t.unidad = v["unidad"]
    t.visibilidad = datos.get("visibilidad") or "equipo"
    t.workflow_id = datos.get("workflow_id") or None
    t.requiere_aprobacion = bool(datos.get("requiere_aprobacion", True))
    t.requiere_sustituto = bool(datos.get("requiere_sustituto"))
    t.datos_especiales = bool(datos.get("datos_especiales"))
    t.activo = bool(datos.get("activo", True))
    t.orden = int(datos.get("orden") if datos.get("orden") is not None else (t.orden or 100))
    if actual is None:
        db.add(t)
    if "requisitos" in datos:
        t.requisitos.clear()
        for i, r in enumerate(datos.get("requisitos") or []):
            t.requisitos.append(RequisitoDocumentalDeTipo(
                id=str(uuid.uuid4()), organization_id=t.organization_id, tipo_de_documento_id=r["tipo_de_documento_id"],
                obligatorio=bool(r.get("obligatorio", True)), plazo_dias=int(r.get("plazo_dias") or 0),
                plazo_desde=r.get("plazo_desde") or "inicio",
                repetir_cada_dias=int(r["repetir_cada_dias"]) if r.get("repetir_cada_dias") not in (None, "") else None,
                recordar_dias_antes=int(r.get("recordar_dias_antes") if r.get("recordar_dias_antes") is not None else 1),
                escalar_dias_despues=int(r["escalar_dias_despues"]) if r.get("escalar_dias_despues") not in (None, "") else None,
                escalar_a=json.dumps(r.get("escalar_a") or [], ensure_ascii=False), orden=i + 1))
    db.commit()
    return tipo_dict(t)


def borrar_tipo(db: Session, usuario, tipo_id: str) -> dict:
    """Un tipo en uso o de sistema se desactiva (las ausencias lo conservan); uno sin uso se borra."""
    from app.models.resources import Absence
    t = tipo(db, tipo_id)
    en_uso = db.query(Absence.id).filter(Absence.absence_type_id == t.id).first() is not None
    if en_uso or t.de_sistema:
        t.activo = False
        resultado = {"desactivado": True}
    else:
        db.delete(t)
        resultado = {"eliminado": True}
    db.commit()
    return resultado


# ── Tipos de documento ───────────────────────────────────────────────────────

def documentos(db: Session, *, incluir_inactivos: bool = False, usuario=None) -> list[TipoDeDocumentoDeAusencia]:
    org = _org(db, usuario) if usuario is not None and not (db.info or {}).get("organization_id") else _org(db)
    asegurar(db, org)
    q = db.query(TipoDeDocumentoDeAusencia)
    if org:
        q = q.filter(TipoDeDocumentoDeAusencia.organization_id == org)
    if not incluir_inactivos:
        q = q.filter(TipoDeDocumentoDeAusencia.activo.is_(True))
    return q.order_by(TipoDeDocumentoDeAusencia.orden, TipoDeDocumentoDeAusencia.nombre).all()


def documento(db: Session, doc_id: str) -> TipoDeDocumentoDeAusencia:
    d = db.query(TipoDeDocumentoDeAusencia).filter(TipoDeDocumentoDeAusencia.id == doc_id).first()
    if d is None:
        raise ErrorDeDominio(404, "Tipo de documento no encontrado")
    return d


def documento_dict(d: TipoDeDocumentoDeAusencia) -> dict:
    return {"id": d.id, "clave": d.clave, "nombre": d.nombre, "nombres": _json(d.nombres, {}),
            "categoria_especial": bool(d.categoria_especial), "activo": bool(d.activo), "orden": d.orden}


def guardar_documento(db: Session, usuario, datos: dict, doc_id: Optional[str] = None) -> dict:
    actual = documento(db, doc_id) if doc_id else None
    nombres = _nombres(datos)
    clave = (datos.get("clave") or (actual.clave if actual else "")).strip()
    if not _CLAVE.match(clave):
        raise ErrorDeDominio(422, "La clave va en minúsculas, números y _ (2 a 50)")
    if (actual is None or actual.clave != clave) and db.query(TipoDeDocumentoDeAusencia.id).filter(
            TipoDeDocumentoDeAusencia.clave == clave).first():
        raise ErrorDeDominio(422, f"Ya hay un tipo de documento con la clave {clave}")
    d = actual or TipoDeDocumentoDeAusencia(id=str(uuid.uuid4()), organization_id=_org(db, usuario))
    d.clave = clave
    d.nombres = json.dumps(nombres, ensure_ascii=False) if nombres else None
    d.nombre = (datos.get("nombre") or "").strip()[:120] or nombres.get(IDIOMA_DE_RESPALDO) or next(iter(nombres.values()))
    d.categoria_especial = bool(datos.get("categoria_especial"))
    d.activo = bool(datos.get("activo", True))
    d.orden = int(datos.get("orden") if datos.get("orden") is not None else (d.orden or 100))
    if actual is None:
        db.add(d)
    db.commit()
    return documento_dict(d)


def borrar_documento(db: Session, usuario, doc_id: str) -> dict:
    from app.models.ausencias import DocumentoDeAusencia, RequisitoDeAusencia
    d = documento(db, doc_id)
    usado = any(db.query(M.id).filter(M.tipo_id == d.id).first() for M in (DocumentoDeAusencia, RequisitoDeAusencia)) \
        or db.query(RequisitoDocumentalDeTipo.id).filter(RequisitoDocumentalDeTipo.tipo_de_documento_id == d.id).first()
    if usado:
        d.activo = False
        resultado = {"desactivado": True}
    else:
        db.delete(d)
        resultado = {"eliminado": True}
    db.commit()
    return resultado


# ── Acceso especial (categoría especial, RGPD art. 9) ────────────────────────

def accesos(db: Session) -> list[dict]:
    from app.models.user import User
    filas = db.query(AccesoEspecialAusencias, User.full_name).join(User, User.id == AccesoEspecialAusencias.user_id).all()
    return [{"id": a.id, "user_id": a.user_id, "nombre": n, "concedido_por": a.concedido_por,
             "created_at": a.created_at.isoformat() if a.created_at else None} for a, n in filas]


def conceder_acceso(db: Session, usuario, user_id: str) -> list[dict]:
    from app.models.user import User
    from app.services.audit import audit_log
    if db.query(User.id).filter(User.id == user_id, User.is_active.is_(True)).first() is None:
        raise ErrorDeDominio(422, "Esa persona no existe en tu empresa o no está activa")
    if db.query(AccesoEspecialAusencias.id).filter(AccesoEspecialAusencias.user_id == user_id).first() is None:
        db.add(AccesoEspecialAusencias(id=str(uuid.uuid4()), organization_id=_org(db, usuario), user_id=user_id,
                                       concedido_por=usuario.id))
        audit_log(db, usuario, "GRANT", "absence_special_access", user_id, None)
        db.commit()
    return accesos(db)


def retirar_acceso(db: Session, usuario, user_id: str) -> list[dict]:
    from app.services.audit import audit_log
    for a in db.query(AccesoEspecialAusencias).filter(AccesoEspecialAusencias.user_id == user_id).all():
        db.delete(a)
        audit_log(db, usuario, "REVOKE", "absence_special_access", user_id, None)
    db.commit()
    return accesos(db)


def tiene_acceso_especial(db: Session, usuario) -> bool:
    """RRHH siempre; cualquier otro (administradores incluidos) solo si está en la lista."""
    rol = str(getattr(usuario.role, "value", usuario.role))
    if rol == "hr":
        return True
    return db.query(AccesoEspecialAusencias.id).filter(AccesoEspecialAusencias.user_id == usuario.id).first() is not None
