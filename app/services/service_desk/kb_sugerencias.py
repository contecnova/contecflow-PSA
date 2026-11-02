"""Sugerencias de la base de conocimiento: al agente y al cliente del portal.

Auditoria 2026-11 (medido): la sugerencia al agente volvia a calcular el
vector de CADA articulo publicado en CADA peticion — con mil articulos, mil
codificaciones por clic. Ahora el vector se guarda con el articulo
(`embedding`) y solo se calcula el de los que aun no lo tienen.

El mismo buscador sirve al portal mientras el cliente escribe su peticion:
si un articulo le resuelve el problema, no hace falta abrir el ticket (y se
cuenta en `deflection_count`).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.service_desk import KBArticle, KBStatus

logger = logging.getLogger(__name__)


def _modelo():
    """El modelo de frases, o None: entonces se busca por palabras.

    Solo el modelo de frases (`SEMANTIC_EMBEDDINGS_BACKEND=transformer`) da
    vectores que se pueden guardar. El TF-IDF de respaldo fija su vocabulario
    con los primeros textos que ve CADA proceso: un vector guardado por un
    worker no se puede comparar con el de otro (medido: la consulta salia
    vacia cuando otro uso habia fijado antes el vocabulario).
    """
    try:
        from app.services.semantic_classifier import _get_model
        modelo, es_transformer = _get_model()
    except Exception:
        logger.debug("sin modelo de vectores: se busca por palabras", exc_info=True)
        return None
    return modelo if es_transformer else None


def _a_lista(v) -> list:
    return v.tolist() if hasattr(v, "tolist") else list(v)


def texto_de(article: KBArticle) -> str:
    return f"{article.title or ''}\n{article.summary or ''}\n{article.body or ''}".strip()


def refrescar_vector(article: KBArticle, modelo=None) -> None:
    """Guarda el vector del articulo; sin modelo lo deja vacio (busqueda por palabras)."""
    modelo = modelo or _modelo()
    if modelo is None or not texto_de(article):
        article.embedding = None
        return
    article.embedding = json.dumps(_a_lista(modelo.encode([texto_de(article)], show_progress_bar=False)[0]))


def _por_vector(db: Session, q, texto: str, limite: int) -> Optional[list[tuple[float, KBArticle]]]:
    from app.services.semantic_classifier import _cosine

    modelo = _modelo()
    if modelo is None:
        return None
    consulta = _a_lista(modelo.encode([texto], show_progress_bar=False)[0])
    puntuados = []
    for a in q.all():
        if not a.embedding:
            refrescar_vector(a, modelo)
        if a.embedding:
            puntuados.append((float(_cosine(consulta, json.loads(a.embedding))), a))
    puntuados.sort(key=lambda x: x[0], reverse=True)
    return [p for p in puntuados if p[0] > 0][:limite]


#: Palabras que no distinguen nada. Las de tres letras si cuentan: en soporte
#: casi todo son siglas (VPN, SAP, DNS, ERP).
_VACIAS = frozenset({
    "the", "and", "for", "not", "can", "you", "are", "with", "this", "that", "from",
    "que", "los", "las", "por", "para", "con", "una", "uno", "del", "como", "pero", "mas",
    "más", "sin", "este", "esta", "esto", "hay", "muy", "ya", "puedo", "tengo",
})


def _por_palabras(q, texto: str, limite: int) -> list[tuple[float, KBArticle]]:
    palabras = list(dict.fromkeys(p for p in re.findall(r"\w{3,}", texto.lower()) if p not in _VACIAS))[:8]
    if not palabras:
        return []
    candidatos = q.filter(or_(*[KBArticle.title.ilike(f"%{p}%") for p in palabras],
                              *[KBArticle.body.ilike(f"%{p}%") for p in palabras])).limit(50).all()
    puntuados = []
    for a in candidatos:
        contenido = texto_de(a).lower()
        puntuados.append((sum(1 for p in palabras if p in contenido) / len(palabras), a))
    puntuados.sort(key=lambda x: x[0], reverse=True)
    return puntuados[:limite]


def sugerir(db: Session, texto: str, *, solo_publico: bool, limite: int = 5) -> list[dict]:
    """Los articulos publicados mas parecidos a `texto` (para un cliente, solo los publicos)."""
    texto = (texto or "").strip()
    if len(texto) < 4:
        return []
    q = db.query(KBArticle).filter(KBArticle.status == KBStatus.published)
    if solo_publico:
        q = q.filter(KBArticle.is_public == True)  # noqa: E712
    try:
        puntuados = _por_vector(db, q, texto, limite)
    except Exception:
        logger.warning("busqueda por vectores fallida; se busca por palabras", exc_info=True)
        puntuados = None
    if puntuados is None:
        puntuados = _por_palabras(q, texto, limite)
    return [{"id": a.id, "number": a.number, "title": a.title, "summary": a.summary,
             "score": round(s, 4)} for s, a in puntuados]
