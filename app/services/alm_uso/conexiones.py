"""Conexiones de fuentes de uso de una empresa y sus credenciales.

Las credenciales se guardan con el mecanismo común
(`integration_credentials_service.set_credential`: cifradas, auditadas,
nunca devueltas en claro) en el proveedor `alm_*` del conector y SIEMPRE con
la empresa: se leen con `credenciales()`, que solo mira la fila de esa empresa
(ni la global ni el entorno), para que una empresa no lea nunca con las
credenciales de otra ni con las de la plataforma.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.alm_uso import ALMUsoConexion, ALMUsoSincronizacion
from app.services.alm_uso._comun import FIABILIDADES, ahora, ajuste_int, cargar_json, exigir_org, volcar_json
from app.services.alm_uso.proveedores import proveedor, proveedores
from app.services.alm_uso.proveedores.base import ContextoDeLectura


def credenciales(db: Session, clave_credencial: str, org_id: str) -> dict:
    """Las credenciales de ESA empresa para un proveedor `alm_*`, descifradas. Sin respaldo global."""
    from app.core.encryption import decrypt_value
    from app.db.session import sin_filtro_de_tenant
    from app.models.settings import IntegrationCredential
    from app.services.integration_credentials_service import PROVIDER_REGISTRY

    exigir_org(org_id)
    campos = {f[0]: f for f in PROVIDER_REGISTRY[clave_credencial]["fields"]}
    salida = {k: None for k in campos}
    with sin_filtro_de_tenant(db):
        filas = db.query(IntegrationCredential).filter(IntegrationCredential.provider == clave_credencial,
                                                       IntegrationCredential.organization_id == org_id).all()
    for f in filas:
        if f.key not in campos:
            continue
        secreto = campos[f.key][2]
        salida[f.key] = (decrypt_value(f.value_encrypted) if f.value_encrypted else None) if secreto else f.value
    return salida


def _faltan(p, creds: dict) -> list[str]:
    return [k for k in p.obligatorias if not (creds.get(k) or "").strip()] if p.credencial else []


def _conexion(db: Session, org_id: str, clave: str) -> Optional[ALMUsoConexion]:
    return db.query(ALMUsoConexion).filter(ALMUsoConexion.organization_id == org_id,
                                           ALMUsoConexion.proveedor == clave).first()


def conexion_o_404(db: Session, org_id: str, conexion_id: str) -> ALMUsoConexion:
    c = db.query(ALMUsoConexion).filter(ALMUsoConexion.id == conexion_id,
                                        ALMUsoConexion.organization_id == exigir_org(org_id)).first()
    if c is None:
        raise ErrorDeDominio(404, {"code": "ALM_USAGE_CONNECTION_NOT_FOUND", "message": "Conexión no encontrada"})
    return c


def _ultima(db: Session, conexion_id: str) -> Optional[dict]:
    s = db.query(ALMUsoSincronizacion).filter(ALMUsoSincronizacion.conexion_id == conexion_id) \
        .order_by(ALMUsoSincronizacion.iniciada_at.desc()).first()
    return sincronizacion_dict(s) if s else None


def sincronizacion_dict(s: ALMUsoSincronizacion) -> dict:
    return {"id": s.id, "proveedor": s.proveedor, "origen": s.origen, "estado": s.estado,
            "iniciada_at": s.iniciada_at.isoformat() if s.iniciada_at else None,
            "terminada_at": s.terminada_at.isoformat() if s.terminada_at else None,
            "leidos": s.leidos, "nuevas": s.nuevas, "actualizadas": s.actualizadas, "sin_titular": s.sin_titular,
            "sin_licencia": s.sin_licencia, "dispositivos": s.dispositivos,
            "errores": cargar_json(s.errores, []), "avisos": cargar_json(s.avisos, [])}


def listar(db: Session, org_id: str) -> list[dict]:
    """Todas las fuentes registradas, configuradas o no, con su estado y su última sincronización."""
    from app.services.integration_credentials_service import describe_provider
    exigir_org(org_id)
    salida = []
    for p in proveedores():
        c = _conexion(db, org_id, p.clave)
        creds_cfg: list = []
        faltan: list = []
        if p.credencial:
            creds = credenciales(db, p.credencial, org_id)
            faltan = _faltan(p, creds)
            # Solo «configurado sí/no» de cada campo (y el valor de los no secretos): nunca un secreto.
            for it in describe_provider(db, p.credencial, None)["items"]:
                valor = creds.get(it["key"])
                creds_cfg.append({"clave": it["key"], "etiqueta": it["label"], "secreto": it["is_secret"],
                                  "configurado": bool(valor), "valor": None if it["is_secret"] else valor})
        salida.append({
            **p.describir(),
            "conexion_id": c.id if c else None,
            "activa": bool(c and c.activa),
            "fiabilidad_efectiva": (c.fiabilidad if c and c.fiabilidad else p.fiabilidad),
            "fiabilidad_propia": c.fiabilidad if c else None,
            "configuracion": cargar_json(c.configuracion, {}) if c else {},
            "credenciales": creds_cfg, "faltan": faltan, "lista": not faltan,
            "ultima_sincronizacion_at": c.ultima_sincronizacion_at.isoformat() if c and c.ultima_sincronizacion_at else None,
            "ultimo_estado": c.ultimo_estado if c else "nunca",
            "ultimo_error": c.ultimo_error if c else None,
            "ultima": _ultima(db, c.id) if c else None,
        })
    return salida


def guardar(db: Session, usuario, clave: str, datos: dict) -> dict:
    """Crea o cambia la conexión de una fuente: activa, fiabilidad, opciones y credenciales.

    `datos.credenciales`: {clave: valor}; un valor vacío borra esa credencial y
    una clave ausente no se toca (así un secreto no se reescribe sin querer).
    """
    from app.services.audit import audit_log
    from app.services.integration_credentials_service import set_credential
    org = exigir_org(getattr(usuario, "organization_id", None))
    p = proveedor(clave)
    c = _conexion(db, org, clave)
    nueva = c is None
    if nueva:
        c = ALMUsoConexion(organization_id=org, proveedor=clave, activa=False, created_by=usuario.id)
        db.add(c)
    if "fiabilidad" in datos:
        f = datos.get("fiabilidad") or None
        if f is not None and f not in FIABILIDADES:
            raise ErrorDeDominio(422, {"code": "ALM_USAGE_BAD_RELIABILITY", "message": "Fiabilidad no válida"})
        c.fiabilidad = f
    if "configuracion" in datos:
        cfg = datos.get("configuracion") or {}
        if not isinstance(cfg, dict):
            raise ErrorDeDominio(422, {"code": "ALM_USAGE_BAD_OPTIONS", "message": "Las opciones deben ser un objeto"})
        validas = {k for k, _ in p.opciones}
        desconocidas = sorted(set(cfg) - validas)
        if desconocidas:
            raise ErrorDeDominio(422, {"code": "ALM_USAGE_BAD_OPTIONS",
                                       "message": f"Opciones desconocidas: {', '.join(desconocidas)}"})
        c.configuracion = volcar_json(cfg)
    db.flush()
    cambiadas = []
    if p.credencial and isinstance(datos.get("credenciales"), dict):
        from app.services.integration_credentials_service import PROVIDER_REGISTRY
        validas = {f[0] for f in PROVIDER_REGISTRY[p.credencial]["fields"]}
        for k, v in datos["credenciales"].items():
            if k not in validas:
                raise ErrorDeDominio(422, {"code": "ALM_USAGE_BAD_CREDENTIAL", "message": f"Campo desconocido: {k}"})
            set_credential(db, p.credencial, k, (v or "").strip() or None, org, usuario.id)
            cambiadas.append(k)
    if "activa" in datos:
        activar = bool(datos["activa"])
        if activar and p.credencial:
            faltan = _faltan(p, credenciales(db, p.credencial, org))
            if faltan:
                raise ErrorDeDominio(422, {"code": "ALM_USAGE_MISSING_CREDENTIALS",
                                           "message": f"Faltan credenciales: {', '.join(faltan)}", "faltan": faltan})
        c.activa = activar
    audit_log(db, usuario, "CREATE" if nueva else "UPDATE", "alm_uso_conexion", c.id, p.etiqueta,
              new_values={"activa": c.activa, "fiabilidad": c.fiabilidad, "credenciales_cambiadas": cambiadas,
                          "opciones": sorted((cargar_json(c.configuracion, {}) or {}).keys())})
    db.commit()
    return next(x for x in listar(db, org) if x["clave"] == clave)


def contexto_de_lectura(db: Session, org: str, p, conexion: Optional[ALMUsoConexion], http=None) -> ContextoDeLectura:
    """Lo que un proveedor necesita para leer: credenciales, opciones, cliente HTTP y topes."""
    from app.services.alm_uso.proveedores.http import cliente_para
    creds = credenciales(db, p.credencial, org) if p.credencial else {}
    return ContextoDeLectura(
        db=db, organization_id=org, credenciales=creds,
        configuracion=cargar_json(conexion.configuracion, {}) if conexion else {},
        http=http or cliente_para(db, f"alm_uso_{p.clave}"),
        max_paginas=ajuste_int(db, "ALM_USAGE_MAX_PAGES", org, minimo=1),
        periodo_dias=ajuste_int(db, "ALM_USAGE_REPORT_PERIOD_DAYS", org, minimo=1),
        max_apps=ajuste_int(db, "ALM_USAGE_INTUNE_MAX_APPS", org, minimo=1),
        ahora=ahora())


def probar(db: Session, usuario, clave: str) -> dict:
    """Prueba credenciales y permisos con la llamada más barata de la fuente (no guarda nada)."""
    from app.services.alm_uso.proveedores.base import ErrorDeConector
    org = exigir_org(getattr(usuario, "organization_id", None))
    p = proveedor(clave)
    c = _conexion(db, org, clave)
    ctx = contexto_de_lectura(db, org, p, c)
    faltan = _faltan(p, ctx.credenciales)
    if faltan:
        return {"ok": False, "codigo": "MISSING_CREDENTIALS", "mensaje": f"Faltan: {', '.join(faltan)}"}
    try:
        return {"ok": True, **p.probar(ctx)}
    except ErrorDeConector as e:
        return {"ok": False, "codigo": e.codigo, "mensaje": e.mensaje}
    except ErrorDeDominio as e:   # URL rechazada por la protección de salidas
        return {"ok": False, "codigo": "URL_NOT_ALLOWED", "mensaje": str(e.detail)}


def historial(db: Session, org_id: str, conexion_id: Optional[str] = None, limite: int = 50) -> list[dict]:
    q = db.query(ALMUsoSincronizacion).filter(ALMUsoSincronizacion.organization_id == exigir_org(org_id))
    if conexion_id:
        q = q.filter(ALMUsoSincronizacion.conexion_id == conexion_id)
    return [sincronizacion_dict(s) for s in q.order_by(ALMUsoSincronizacion.iniciada_at.desc()).limit(limite)]


def conexion_del_agente(db: Session, org_id: str) -> Optional[ALMUsoConexion]:
    """La conexión del agente de inventario de la empresa; se crea activa la primera vez que envía."""
    c = _conexion(db, org_id, "agente_cmdb")
    if c is None:
        c = ALMUsoConexion(organization_id=org_id, proveedor="agente_cmdb", activa=True)
        db.add(c)
        db.flush()
    return c
