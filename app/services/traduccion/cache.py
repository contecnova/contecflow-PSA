"""Cache de traducciones por empresa: (texto, origen, destino, glosario).

La clave es el SHA-256 de esos cuatro datos: el texto no se guarda dos veces y
la cache de una empresa nunca sirve a otra (la fila lleva su `organization_id`
y la consulta filtra por el). El proveedor no forma parte de la clave: cambiar
de proveedor reutiliza lo ya pagado.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.traduccion import TranslationCacheEntry

_SEPARADOR = "\x1f"


def clave(texto: str, origen: Optional[str], destino: str, huella_del_glosario: str) -> str:
    crudo = _SEPARADOR.join((origen or "", destino, huella_del_glosario or "", texto))
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def buscar(db: Session, org_id: str, claves: list[str]) -> dict[str, TranslationCacheEntry]:
    if not claves:
        return {}
    filas = db.query(TranslationCacheEntry).filter(TranslationCacheEntry.organization_id == org_id,
                                                   TranslationCacheEntry.cache_key.in_(set(claves))).all()
    ahora = datetime.now(timezone.utc)
    for f in filas:
        f.hits = (f.hits or 0) + 1
        f.last_used_at = ahora
    return {f.cache_key: f for f in filas}


def guardar(db: Session, org_id: str, clave_: str, origen: Optional[str], destino: str, texto: str,
            proveedor: str, caracteres: int) -> None:
    existente = db.query(TranslationCacheEntry).filter(TranslationCacheEntry.organization_id == org_id,
                                                       TranslationCacheEntry.cache_key == clave_).first()
    ahora = datetime.now(timezone.utc)
    if existente is not None:
        existente.translated_text, existente.provider, existente.last_used_at = texto, proveedor, ahora
        return
    db.add(TranslationCacheEntry(organization_id=org_id, cache_key=clave_, source_language=origen,
                                 target_language=destino, translated_text=texto, provider=proveedor,
                                 characters=caracteres, hits=0, last_used_at=ahora))


def purgar(db: Session) -> int:
    """Borra lo que lleva mas de `TRANSLATION_CACHE_RETENTION_DAYS` sin usarse, empresa a empresa."""
    from app.db.session import sin_filtro_de_tenant
    from app.services.traduccion.ajustes import dias_de_cache

    borradas = 0
    with sin_filtro_de_tenant(db):
        orgs = [o for (o,) in db.query(TranslationCacheEntry.organization_id).distinct().all() if o]
        for org in orgs:
            dias = dias_de_cache(db, org)
            if dias <= 0:
                continue
            limite = datetime.now(timezone.utc) - timedelta(days=dias)
            borradas += db.query(TranslationCacheEntry).filter(
                TranslationCacheEntry.organization_id == org,
                TranslationCacheEntry.last_used_at < limite).delete(synchronize_session=False)
    db.commit()
    return borradas


def estadisticas(db: Session, org_id: str) -> dict:
    from sqlalchemy import func
    total, caracteres, aciertos = db.query(
        func.count(TranslationCacheEntry.id), func.coalesce(func.sum(TranslationCacheEntry.characters), 0),
        func.coalesce(func.sum(TranslationCacheEntry.hits), 0),
    ).filter(TranslationCacheEntry.organization_id == org_id).one()
    return {"entries": int(total or 0), "characters": int(caracteres or 0), "hits": int(aciertos or 0)}
