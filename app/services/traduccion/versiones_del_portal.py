"""Versiones revisables de avisos y catalogo en los idiomas del portal (17-11-2026).

Lo mismo que ya hacen los articulos de la KB (`traduccion/kb.py`), para el
otro contenido de operadores que lee el cliente del portal:

- avisos (`announcement`: `title`, `body`);
- categorias del catalogo (`catalog_category`: `name`, `description`);
- servicios del catalogo (`catalog_service`: `name`, `description`).

Ciclo de una version (`PortalContentTranslation`, migracion 181):

- `generar`: traduce los campos a los idiomas del portal elegidos
  (`TRANSLATION_KB_LANGUAGES`, por defecto los 8) menos el del original. Cada
  version nace **en revision** (`in_review`); regenerar una publicada la
  devuelve a revision.
- `editar`: un editor corrige; vuelve a revision y toma como base el original
  de ahora (deja de estar desactualizada).
- `revisar`: publicar o rechazar (con motivo). Solo un revisor (`puede_revisar`).
- `borrar`.

Lo que ve el portal (`localizar_para_el_portal`): la version **publicada** en
su idioma; si no la hay, la traduccion automatica en cache de siempre
(`contenido_del_portal.localizar`, con `translated_from` y `original`: la marca
«Traducido automaticamente»). Una publicada sigue sirviendose aunque el
original cambie (es la revisada), pero queda **desactualizada**
(`source_hash` distinto de la huella actual): la pantalla de revision lo marca
y, al guardar el cambio del original, se avisa a los revisores
(`avisar_si_desactualizadas`).

Permisos (minimo privilegio):

- revisor (publicar/rechazar): administrador de la empresa o miembro de la
  cola de revisores de contenido (`SD_KB_REVIEWER_GROUP_ID`, la misma que
  revisa la KB);
- editor (generar, corregir, borrar): administrador o revisor.

Todo acotado a la empresa de quien pide y auditado (`TRANSLATE`, `UPDATE`,
`APPROVE`, `REJECT`, `DELETE` sobre `portal_content_translation`).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.traduccion import PortalContentTranslation
from app.services.traduccion import ajustes
from app.services.traduccion.idiomas import IDIOMAS_DEL_PORTAL, detectar, normalizar
from app.services.traduccion.servicio import TRADUCIDO, traducir

logger = logging.getLogger(__name__)

ESTADOS = ("draft", "in_review", "published", "rejected")
CANAL = "portal"
RECURSO = "portal_content_translation"
MAX_CAMPO = {"title": 255, "name": 255}


@dataclass(frozen=True)
class Tipo:
    clave: str
    campos: tuple[str, ...]
    #: El primero es obligatorio (titulo o nombre).
    obligatorio: str

    @property
    def modelo(self):
        from app.models.service_desk import Announcement, ServiceCategory, ServiceItem
        return {"announcement": Announcement, "catalog_category": ServiceCategory,
                "catalog_service": ServiceItem}[self.clave]


TIPOS: dict[str, Tipo] = {
    "announcement": Tipo("announcement", ("title", "body"), "title"),
    "catalog_category": Tipo("catalog_category", ("name", "description"), "name"),
    "catalog_service": Tipo("catalog_service", ("name", "description"), "name"),
}


def tipo_de(clave: str) -> Tipo:
    t = TIPOS.get(clave)
    if t is None:
        raise ErrorDeDominio(422, "trad_tipo_de_contenido_desconocido")
    return t


# ── Permisos ─────────────────────────────────────────────────────────────────

def _es_admin(usuario) -> bool:
    return bool(getattr(usuario, "is_superadmin", False)) or getattr(usuario.role, "value", usuario.role) == "admin"


def puede_revisar(db: Session, usuario) -> bool:
    if _es_admin(usuario):
        return True
    from app.models.service_desk import AgentGroupMember
    from app.services import settings_service as _ss
    grupo = _ss.get_runtime_str(db, "SD_KB_REVIEWER_GROUP_ID", usuario.organization_id)
    return bool(grupo) and db.query(AgentGroupMember.id).filter(
        AgentGroupMember.group_id == grupo, AgentGroupMember.user_id == usuario.id).first() is not None


def _exigir_editor(db: Session, usuario) -> None:
    if not (_es_admin(usuario) or puede_revisar(db, usuario)):
        raise ErrorDeDominio(403, "trad_sin_permiso")


def revisores(db: Session, org_id: Optional[str]) -> list[str]:
    from app.models.service_desk import AgentGroupMember
    from app.models.user import User, UserRole
    from app.services import settings_service as _ss
    grupo = _ss.get_runtime_str(db, "SD_KB_REVIEWER_GROUP_ID", org_id)
    ids = set()
    if grupo:
        ids |= {r[0] for r in db.query(AgentGroupMember.user_id).filter(AgentGroupMember.group_id == grupo).all()}
    ids |= {r[0] for r in db.query(User.id).filter(User.role == UserRole.admin, User.is_active == True,  # noqa: E712
                                                   User.organization_id == org_id).all()}
    return sorted(ids)


# ── Original ─────────────────────────────────────────────────────────────────

def textos_del_original(tipo: Tipo, obj) -> dict[str, str]:
    return {c: (getattr(obj, c, None) or "") for c in tipo.campos}


def huella(tipo: Tipo, obj) -> str:
    crudo = json.dumps(textos_del_original(tipo, obj), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def _idioma_del_original(db: Session, tipo: Tipo, obj) -> Optional[str]:
    texto = "\n".join(t for t in textos_del_original(tipo, obj).values() if t)
    idioma, confianza = detectar(texto)
    if idioma and confianza >= ajustes.confianza_minima(db, obj.organization_id):
        return idioma
    return ajustes.idioma_por_defecto(db, obj.organization_id)


def _contenido(db: Session, usuario, tipo: Tipo, content_id: str):
    m = tipo.modelo
    q = db.query(m).filter(m.id == content_id)
    if usuario.organization_id:
        q = q.filter(m.organization_id == usuario.organization_id)
    obj = q.first()
    if obj is None:
        raise ErrorDeDominio(404, "trad_contenido_no_encontrado")
    return obj


def _etiqueta(tipo: Tipo, obj) -> str:
    return (getattr(obj, tipo.obligatorio, None) or "")[:120]


# ── Serializacion ────────────────────────────────────────────────────────────

def _campos(v: PortalContentTranslation) -> dict[str, str]:
    try:
        datos = json.loads(v.fields or "{}")
    except ValueError:
        datos = {}
    return datos if isinstance(datos, dict) else {}


def esta_desactualizada(v: PortalContentTranslation, huella_actual: Optional[str]) -> bool:
    return bool(v.source_hash and huella_actual and v.source_hash != huella_actual)


def serializar(v: PortalContentTranslation, huella_actual: Optional[str] = None) -> dict:
    return {"id": v.id, "content_type": v.content_type, "content_id": v.content_id, "language": v.language,
            "fields": _campos(v), "status": v.status, "provider": v.provider,
            "outdated": esta_desactualizada(v, huella_actual), "review_comment": v.review_comment,
            "reviewed_at": v.reviewed_at.isoformat() if v.reviewed_at else None,
            "updated_at": (v.updated_at or v.created_at).isoformat() if (v.updated_at or v.created_at) else None}


def _versiones(db: Session, tipo: Tipo, content_id: str) -> list[PortalContentTranslation]:
    return db.query(PortalContentTranslation).filter(PortalContentTranslation.content_type == tipo.clave,
                                                     PortalContentTranslation.content_id == content_id) \
        .order_by(PortalContentTranslation.language).all()


# ── Operaciones ──────────────────────────────────────────────────────────────

def listar(db: Session, usuario, clave: str, content_id: str) -> dict:
    tipo = tipo_de(clave)
    _exigir_editor(db, usuario)
    obj = _contenido(db, usuario, tipo, content_id)
    actual = huella(tipo, obj)
    return {"content_type": tipo.clave, "content_id": obj.id, "label": _etiqueta(tipo, obj),
            "fields": list(tipo.campos), "required_field": tipo.obligatorio,
            "original": textos_del_original(tipo, obj),
            "source_language": _idioma_del_original(db, tipo, obj),
            "languages": ajustes.idiomas_de_la_kb(db, obj.organization_id),
            "enabled": ajustes.habilitada_en(db, obj.organization_id, CANAL),
            "can_review": puede_revisar(db, usuario),
            "items": [serializar(v, actual) for v in _versiones(db, tipo, obj.id)]}


def generar(db: Session, usuario, clave: str, content_id: str, idiomas: Optional[list[str]] = None) -> dict:
    from app.services.audit import audit_log
    tipo = tipo_de(clave)
    _exigir_editor(db, usuario)
    obj = _contenido(db, usuario, tipo, content_id)
    origen = _idioma_del_original(db, tipo, obj)
    posibles = ajustes.idiomas_de_la_kb(db, obj.organization_id)
    pedidos = [normalizar(i) for i in (idiomas or posibles)]
    if any(i not in IDIOMAS_DEL_PORTAL for i in pedidos):
        raise ErrorDeDominio(422, "trad_idioma_no_soportado")
    destinos = [i for i in dict.fromkeys(pedidos) if i != origen]
    originales = textos_del_original(tipo, obj)
    campos = list(originales.items())
    actual = huella(tipo, obj)
    hechos, fallos = [], []
    for destino in destinos:
        rs = traducir(db, obj.organization_id, [t for _, t in campos], destino, canal=CANAL, origen=origen,
                      user_id=usuario.id)
        utiles = [r for (_, t), r in zip(campos, rs) if t.strip()]
        if not utiles or any(r.estado != TRADUCIDO for r in utiles):
            motivo = next((r.motivo for r in rs if r.estado != TRADUCIDO and r.motivo), "provider_error")
            fallos.append({"language": destino, "reason": motivo})
            continue
        textos = {c: (r.texto if r.estado == TRADUCIDO else t) for (c, t), r in zip(campos, rs)}
        v = db.query(PortalContentTranslation).filter(PortalContentTranslation.content_type == tipo.clave,
                                                      PortalContentTranslation.content_id == obj.id,
                                                      PortalContentTranslation.language == destino).first()
        if v is None:
            v = PortalContentTranslation(organization_id=obj.organization_id, content_type=tipo.clave,
                                         content_id=obj.id, language=destino)
            db.add(v)
        v.fields = json.dumps(_recortar(textos), ensure_ascii=False)
        v.status, v.provider, v.source_language, v.source_hash = "in_review", utiles[0].proveedor, origen, actual
        v.generated_by_user_id, v.reviewed_by_user_id, v.reviewed_at, v.review_comment = usuario.id, None, None, None
        db.flush()
        audit_log(db, usuario, "TRANSLATE", RECURSO, v.id, f"{tipo.clave} {_etiqueta(tipo, obj)} {destino}",
                  new_values={"content_type": tipo.clave, "content_id": obj.id, "language": destino,
                              "provider": v.provider, "status": v.status})
        hechos.append(serializar(v, actual))
    db.commit()
    return {"generated": hechos, "failed": fallos}


def _recortar(textos: dict[str, str]) -> dict[str, str]:
    return {c: (t[:MAX_CAMPO[c]] if c in MAX_CAMPO else t) for c, t in textos.items()}


def _version(db: Session, usuario, tipo: Tipo, content_id: str, idioma: str):
    obj = _contenido(db, usuario, tipo, content_id)
    v = db.query(PortalContentTranslation).filter(PortalContentTranslation.content_type == tipo.clave,
                                                  PortalContentTranslation.content_id == obj.id,
                                                  PortalContentTranslation.language == normalizar(idioma)).first()
    if v is None:
        raise ErrorDeDominio(404, "trad_version_no_encontrada")
    return obj, v


def editar(db: Session, usuario, clave: str, content_id: str, idioma: str, campos: dict) -> dict:
    from app.services.audit import audit_log
    tipo = tipo_de(clave)
    _exigir_editor(db, usuario)
    obj, v = _version(db, usuario, tipo, content_id, idioma)
    antes = v.status
    datos = _campos(v)
    for c, texto in (campos or {}).items():
        if c not in tipo.campos or texto is None:
            continue
        texto = str(texto).strip()
        if c == tipo.obligatorio and not texto:
            raise ErrorDeDominio(422, "trad_titulo_obligatorio")
        datos[c] = texto
    v.fields = json.dumps(_recortar(datos), ensure_ascii=False)
    # El editor corrige a la vista del original de ahora: deja de estar desactualizada.
    v.status, v.reviewed_by_user_id, v.reviewed_at, v.source_hash = "in_review", None, None, huella(tipo, obj)
    db.flush()
    audit_log(db, usuario, "UPDATE", RECURSO, v.id, f"{tipo.clave} {_etiqueta(tipo, obj)} {v.language}",
              old_values={"status": antes}, new_values={"status": v.status, "edited": True})
    db.commit()
    return serializar(v, huella(tipo, obj))


def revisar(db: Session, usuario, clave: str, content_id: str, idioma: str, publicar: bool,
            comentario: Optional[str]) -> dict:
    from app.services.audit import audit_log
    tipo = tipo_de(clave)
    obj, v = _version(db, usuario, tipo, content_id, idioma)
    if not puede_revisar(db, usuario):
        raise ErrorDeDominio(403, "trad_solo_revisores")
    if v.status not in ("in_review", "draft"):
        raise ErrorDeDominio(409, "trad_version_no_en_revision")
    if not publicar and not (comentario or "").strip():
        raise ErrorDeDominio(422, "trad_motivo_obligatorio")
    v.status = "published" if publicar else "rejected"
    v.reviewed_by_user_id, v.reviewed_at = usuario.id, datetime.now(timezone.utc)
    v.review_comment = (comentario or "").strip()[:500] or None
    db.flush()
    audit_log(db, usuario, "APPROVE" if publicar else "REJECT", RECURSO, v.id,
              f"{tipo.clave} {_etiqueta(tipo, obj)} {v.language}",
              new_values={"status": v.status, "comment": v.review_comment})
    db.commit()
    return serializar(v, huella(tipo, obj))


def borrar(db: Session, usuario, clave: str, content_id: str, idioma: str) -> None:
    from app.services.audit import audit_log
    tipo = tipo_de(clave)
    _exigir_editor(db, usuario)
    obj, v = _version(db, usuario, tipo, content_id, idioma)
    audit_log(db, usuario, "DELETE", RECURSO, v.id, f"{tipo.clave} {_etiqueta(tipo, obj)} {v.language}")
    db.delete(v)
    db.commit()


def resumen(db: Session, usuario) -> dict:
    """La pantalla de revision: cada aviso activo y cada categoria y servicio
    activos de la empresa, con cuantas versiones tiene en cada estado y cuantas
    estan desactualizadas. Primero lo que pide atencion."""
    _exigir_editor(db, usuario)
    org = usuario.organization_id
    versiones = db.query(PortalContentTranslation)
    if org:
        versiones = versiones.filter(PortalContentTranslation.organization_id == org)
    por_contenido: dict[tuple[str, str], list[PortalContentTranslation]] = {}
    for v in versiones.all():
        por_contenido.setdefault((v.content_type, v.content_id), []).append(v)
    filas = []
    for tipo in TIPOS.values():
        m = tipo.modelo
        q = db.query(m).filter(m.is_active == True)  # noqa: E712
        if org:
            q = q.filter(m.organization_id == org)
        for obj in q.all():
            vs = por_contenido.get((tipo.clave, obj.id), [])
            actual = huella(tipo, obj)
            cuenta = {e: sum(1 for v in vs if v.status == e) for e in ESTADOS}
            filas.append({"content_type": tipo.clave, "content_id": obj.id, "label": _etiqueta(tipo, obj),
                          "counts": cuenta, "outdated": sum(1 for v in vs if esta_desactualizada(v, actual)),
                          "languages": sorted(v.language for v in vs)})
    filas.sort(key=lambda f: (-(f["counts"]["in_review"] + f["counts"]["draft"] + f["outdated"]),
                              f["content_type"], f["label"].lower()))
    return {"can_review": puede_revisar(db, usuario),
            "enabled": ajustes.habilitada_en(db, org, CANAL), "items": filas}


# ── Al cambiar el original ───────────────────────────────────────────────────

def avisar_si_desactualizadas(db: Session, usuario, clave: str, obj) -> int:
    """Tras guardar un cambio del original: cuenta sus versiones que han quedado
    desactualizadas y, si las hay, avisa a los revisores (campana) y lo audita.
    Devuelve cuantas. Nunca rompe el guardado."""
    try:
        tipo = tipo_de(clave)
        actual = huella(tipo, obj)
        vs = [v for v in _versiones(db, tipo, obj.id) if esta_desactualizada(v, actual)]
        if not vs:
            return 0
        from app.services.audit import audit_log
        from app.services.notifications import notify_user
        etiqueta = _etiqueta(tipo, obj)
        for uid in revisores(db, obj.organization_id):
            if uid != getattr(usuario, "id", None):
                notify_user(db, uid, "system", f"Traducciones desactualizadas: {etiqueta}"[:255],
                            "El original ha cambiado: revisa sus versiones en los idiomas del portal.",
                            resource=RECURSO, resource_id=obj.id, action_url="/service-desk")
        audit_log(db, usuario, "UPDATE", RECURSO, obj.id, f"{tipo.clave} {etiqueta}",
                  new_values={"outdated": [v.language for v in vs]})
        db.commit()
        return len(vs)
    except Exception:
        logger.warning("versiones del portal: no se pudo avisar de las desactualizadas", exc_info=True)
        db.rollback()
        return 0


# ── Lo que lee el portal ─────────────────────────────────────────────────────

def publicadas(db: Session, org_id: Optional[str], clave: str, ids: Iterable[str],
               idioma: Optional[str]) -> dict[str, PortalContentTranslation]:
    destino = normalizar(idioma)
    ids = [i for i in ids if i]
    if not destino or not ids:
        return {}
    q = db.query(PortalContentTranslation).filter(PortalContentTranslation.content_type == clave,
                                                  PortalContentTranslation.content_id.in_(ids),
                                                  PortalContentTranslation.language == destino,
                                                  PortalContentTranslation.status == "published")
    if org_id:
        q = q.filter(PortalContentTranslation.organization_id == org_id)
    return {v.content_id: v for v in q.all()}


def _aplicar(elementos: list[dict], versiones: dict[str, PortalContentTranslation], campos: tuple[str, ...]) -> list[dict]:
    """Pone la version publicada; devuelve los elementos que se quedan sin ella."""
    sin_version = []
    for e in elementos:
        v = versiones.get(e.get("id"))
        if v is None:
            sin_version.append(e)
            continue
        datos = _campos(v)
        for c in campos:
            if datos.get(c) and c in e:
                e[c] = datos[c]
        e["language"] = v.language
        e["translation_reviewed"] = True
    return sin_version


def localizar_para_el_portal(db: Session, org_id: Optional[str], clave: str, elementos: list[dict],
                             idioma: Optional[str], *, clave_hijos: Optional[str] = None,
                             hijos: Optional[str] = None) -> list[dict]:
    """Versiones publicadas en `idioma`; lo que no tenga, traduccion automatica
    (cache, marcada) en una sola llamada. Nunca lanza."""
    from app.services.traduccion import contenido_del_portal as _auto
    destino = normalizar(idioma)
    if not destino or not elementos:
        return elementos
    try:
        tipo = tipo_de(clave)
        pendientes = _aplicar(elementos, publicadas(db, org_id, clave, [e.get("id") for e in elementos], destino),
                              tipo.campos)
        if clave_hijos and hijos:
            tipo_h = tipo_de(clave_hijos)
            todos_h = [h for e in elementos for h in (e.get(hijos) or [])]
            pendientes_h = _aplicar(todos_h, publicadas(db, org_id, clave_hijos, [h.get("id") for h in todos_h],
                                                        destino), tipo_h.campos)
        else:
            tipo_h, pendientes_h = None, []
    except Exception:
        logger.exception("versiones del portal: no se pudieron leer; se traduce al vuelo")
        db.rollback()
        pendientes, tipo_h, pendientes_h = elementos, None, []
        tipo = TIPOS.get(clave)
    # Una sola llamada para padres e hijos cuando comparten campos (catalogo).
    if tipo_h is not None and tipo_h.campos == tipo.campos:
        _auto.localizar(db, org_id, pendientes + pendientes_h, tipo.campos, destino)
    else:
        if pendientes and tipo is not None:
            _auto.localizar(db, org_id, pendientes, tipo.campos, destino)
        if pendientes_h and tipo_h is not None:
            _auto.localizar(db, org_id, pendientes_h, tipo_h.campos, destino)
    return elementos
