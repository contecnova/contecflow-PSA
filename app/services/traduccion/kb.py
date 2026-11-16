"""Versiones de los articulos de la base de conocimiento en los idiomas del portal.

- `generar`: traduce titulo, resumen y cuerpo a los idiomas del portal
  (`TRANSLATION_KB_LANGUAGES`, por defecto los 8) menos el del propio articulo.
  Cada version nace **en revision** (`in_review`): no la ve ningun cliente
  hasta que un revisor la publica. Regenerar una version publicada la vuelve a
  revision.
- `editar`: el revisor corrige; la version vuelve a revision.
- `revisar`: publicar o rechazar (con motivo). Solo quien puede publicar
  articulos (`kb_service.puede_publicar`).
- `version_publicada`/`localizar`: lo que lee el portal. Si el articulo cambio
  despues de generar la version (`source_updated_at`), sigue sirviendose (es la
  revisada) y la pantalla de revision la marca como desfasada.

Todo acotado al articulo visible para quien pide (`get_scoped_kb_article_or_404`)
y auditado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.traduccion import KBArticleTranslation
from app.services.traduccion import ajustes
from app.services.traduccion.idiomas import IDIOMAS_DEL_PORTAL, detectar, normalizar
from app.services.traduccion.servicio import TRADUCIDO, traducir

ESTADOS = ("draft", "in_review", "published", "rejected")


def _fecha_del_original(a) -> Optional[datetime]:
    return a.updated_at or a.created_at


def _idioma_del_articulo(db: Session, a) -> Optional[str]:
    idioma, confianza = detectar(f"{a.title}\n{a.body}")
    if idioma and confianza >= ajustes.confianza_minima(db, a.organization_id):
        return idioma
    return ajustes.idioma_por_defecto(db, a.organization_id)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def serializar(v: KBArticleTranslation, articulo=None) -> dict:
    desfasada = bool(articulo is not None and v.source_updated_at and _fecha_del_original(articulo)
                     and _aware(_fecha_del_original(articulo)) > _aware(v.source_updated_at))
    return {"id": v.id, "article_id": v.article_id, "language": v.language, "title": v.title,
            "summary": v.summary, "body": v.body, "status": v.status, "provider": v.provider,
            "outdated": desfasada, "review_comment": v.review_comment,
            "reviewed_at": v.reviewed_at.isoformat() if v.reviewed_at else None,
            "updated_at": (v.updated_at or v.created_at).isoformat() if (v.updated_at or v.created_at) else None}


def _articulo(db: Session, usuario, article_id: str):
    from app.services.service_desk.kb_service import get_scoped_kb_article_or_404
    return get_scoped_kb_article_or_404(db, usuario, article_id)


def listar(db: Session, usuario, article_id: str) -> dict:
    a = _articulo(db, usuario, article_id)
    filas = db.query(KBArticleTranslation).filter(KBArticleTranslation.article_id == a.id) \
        .order_by(KBArticleTranslation.language).all()
    return {"article_id": a.id, "source_language": _idioma_del_articulo(db, a),
            "languages": ajustes.idiomas_de_la_kb(db, a.organization_id),
            "enabled": ajustes.habilitada_en(db, a.organization_id, "kb"),
            "items": [serializar(v, a) for v in filas]}


def generar(db: Session, usuario, article_id: str, idiomas: Optional[list[str]] = None) -> dict:
    from app.services.audit import audit_log
    a = _articulo(db, usuario, article_id)
    origen = _idioma_del_articulo(db, a)
    posibles = ajustes.idiomas_de_la_kb(db, a.organization_id)
    pedidos = [normalizar(i) for i in (idiomas or posibles)]
    if any(i not in IDIOMAS_DEL_PORTAL for i in pedidos):
        raise ErrorDeDominio(422, "trad_idioma_no_soportado")
    destinos = [i for i in dict.fromkeys(pedidos) if i != origen]
    hechos, fallos = [], []
    campos = [("title", a.title or ""), ("summary", a.summary or ""), ("body", a.body or "")]
    for destino in destinos:
        rs = traducir(db, a.organization_id, [t for _, t in campos], destino, canal="kb", origen=origen,
                      user_id=usuario.id)
        utiles = [r for (_, t), r in zip(campos, rs) if t.strip()]
        if not utiles or any(r.estado != TRADUCIDO for r in utiles):
            motivo = next((r.motivo for r in rs if r.estado != TRADUCIDO and r.motivo), "provider_error")
            fallos.append({"language": destino, "reason": motivo})
            continue
        textos = {campo: (r.texto if r.estado == TRADUCIDO else t) for (campo, t), r in zip(campos, rs)}
        v = db.query(KBArticleTranslation).filter(KBArticleTranslation.article_id == a.id,
                                                  KBArticleTranslation.language == destino).first()
        if v is None:
            v = KBArticleTranslation(organization_id=a.organization_id, article_id=a.id, language=destino)
            db.add(v)
        v.title, v.summary, v.body = textos["title"][:500], (textos["summary"] or None), textos["body"]
        v.status, v.provider = "in_review", utiles[0].proveedor
        v.source_updated_at = _fecha_del_original(a)
        v.generated_by_user_id, v.reviewed_by_user_id, v.reviewed_at, v.review_comment = usuario.id, None, None, None
        db.flush()
        audit_log(db, usuario, "TRANSLATE", "kb_article_translation", v.id, f"{a.number} {destino}",
                  new_values={"article_id": a.id, "language": destino, "provider": v.provider, "status": v.status})
        hechos.append(serializar(v, a))
    db.commit()
    return {"generated": hechos, "failed": fallos}


def _version(db: Session, usuario, article_id: str, idioma: str):
    a = _articulo(db, usuario, article_id)
    v = db.query(KBArticleTranslation).filter(KBArticleTranslation.article_id == a.id,
                                              KBArticleTranslation.language == normalizar(idioma)).first()
    if v is None:
        raise ErrorDeDominio(404, "trad_version_no_encontrada")
    return a, v


def editar(db: Session, usuario, article_id: str, idioma: str, datos: dict) -> dict:
    from app.services.audit import audit_log
    a, v = _version(db, usuario, article_id, idioma)
    antes = serializar(v, a)
    if datos.get("title") is not None:
        if not datos["title"].strip():
            raise ErrorDeDominio(422, "trad_titulo_obligatorio")
        v.title = datos["title"].strip()[:500]
    if datos.get("summary") is not None:
        v.summary = datos["summary"].strip()[:500] or None
    if datos.get("body") is not None:
        if not datos["body"].strip():
            raise ErrorDeDominio(422, "trad_cuerpo_obligatorio")
        v.body = datos["body"]
    v.status, v.reviewed_by_user_id, v.reviewed_at = "in_review", None, None
    db.flush()
    audit_log(db, usuario, "UPDATE", "kb_article_translation", v.id, f"{a.number} {v.language}",
              old_values={"status": antes["status"]}, new_values={"status": v.status, "edited": True})
    db.commit()
    return serializar(v, a)


def revisar(db: Session, usuario, article_id: str, idioma: str, publicar: bool, comentario: Optional[str]) -> dict:
    from app.services.audit import audit_log
    from app.services.service_desk.kb_service import puede_publicar
    a, v = _version(db, usuario, article_id, idioma)
    if not puede_publicar(db, usuario):
        raise ErrorDeDominio(403, "trad_solo_revisores")
    if v.status not in ("in_review", "draft"):
        raise ErrorDeDominio(409, "trad_version_no_en_revision")
    if not publicar and not (comentario or "").strip():
        raise ErrorDeDominio(422, "trad_motivo_obligatorio")
    v.status = "published" if publicar else "rejected"
    v.reviewed_by_user_id, v.reviewed_at = usuario.id, datetime.now(timezone.utc)
    v.review_comment = (comentario or "").strip()[:500] or None
    db.flush()
    audit_log(db, usuario, "APPROVE" if publicar else "REJECT", "kb_article_translation", v.id,
              f"{a.number} {v.language}", new_values={"status": v.status, "comment": v.review_comment})
    db.commit()
    return serializar(v, a)


def borrar(db: Session, usuario, article_id: str, idioma: str) -> None:
    from app.services.audit import audit_log
    a, v = _version(db, usuario, article_id, idioma)
    audit_log(db, usuario, "DELETE", "kb_article_translation", v.id, f"{a.number} {v.language}")
    db.delete(v)
    db.commit()


# ── Lo que lee el portal ─────────────────────────────────────────────────────

def publicadas(db: Session, article_ids: list[str], idioma: Optional[str]) -> dict[str, KBArticleTranslation]:
    destino = normalizar(idioma)
    if not destino or not article_ids:
        return {}
    filas = db.query(KBArticleTranslation).filter(KBArticleTranslation.article_id.in_(article_ids),
                                                  KBArticleTranslation.language == destino,
                                                  KBArticleTranslation.status == "published").all()
    return {f.article_id: f for f in filas}


def localizar(db: Session, datos: list[dict], idioma: Optional[str]) -> list[dict]:
    """Cambia titulo, resumen y cuerpo por la version publicada en `idioma` (si la hay)."""
    versiones = publicadas(db, [d["id"] for d in datos if d.get("id")], idioma)
    for d in datos:
        v = versiones.get(d.get("id"))
        if v is None:
            continue
        d["title"] = v.title
        if "summary" in d:
            d["summary"] = v.summary or d.get("summary")
        if d.get("body") is not None:
            d["body"] = v.body
        d["language"] = v.language
    return datos
