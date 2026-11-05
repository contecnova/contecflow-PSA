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


def refrescar_vector(article: KBArticle, modelo=None, db: Optional[Session] = None) -> None:
    """Guarda el vector del articulo; sin modelo lo deja vacio (busqueda por palabras).

    Con `db`, lo copia tambien a la columna de pgvector si la hay.
    """
    from app.services.service_desk import kb_vectores

    modelo = modelo or _modelo()
    if modelo is None or not texto_de(article):
        article.embedding = None
        if db is not None and article.id:
            kb_vectores.guardar(db, article.id, None)
        return
    vector = _a_lista(modelo.encode([texto_de(article)], show_progress_bar=False)[0])
    article.embedding = json.dumps(vector)
    if db is not None and article.id:
        kb_vectores.guardar(db, article.id, vector)


def _por_vector(db: Session, q, texto: str, limite: int) -> Optional[list[tuple[float, KBArticle]]]:
    from app.services.semantic_classifier import _cosine

    modelo = _modelo()
    if modelo is None:
        return None
    from app.services.service_desk import kb_vectores

    consulta = _a_lista(modelo.encode([texto], show_progress_bar=False)[0])
    for a in q.filter(KBArticle.embedding.is_(None)).all():
        refrescar_vector(a, modelo, db)
    if kb_vectores.disponible(db):
        # La base ordena (pgvector): solo viajan ids, no vectores.
        ids = [i for (i,) in q.with_entities(KBArticle.id).all()]
        encontrados = kb_vectores.buscar(db, ids, consulta, limite)
        por_id = {a.id: a for a in q.filter(KBArticle.id.in_([i for _, i in encontrados])).all()}
        return [(s, por_id[i]) for s, i in encontrados if s > 0 and i in por_id]
    puntuados = []
    for a in q.all():
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


def _sin_tildes(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def _raiz(palabra: str) -> str:
    """Las seis primeras letras: «restablezco» y «restablecer» comparten «restab».

    Revisión 2026-11, medido en la copia: «¿Cómo restablezco mi contraseña?» no
    encontraba «Como restablecer tu contrasena» (otra persona del verbo, y la
    eñe escrita sin tilde). Las de hasta cinco letras van enteras (siglas).
    """
    return palabra if len(palabra) <= 5 else palabra[:6]


def _por_palabras(q, texto: str, limite: int) -> list[tuple[float, KBArticle]]:
    palabras = list(dict.fromkeys(p for p in re.findall(r"\w{3,}", _sin_tildes(texto)) if p not in _VACIAS))[:8]
    if not palabras:
        return []
    raices = [_raiz(p) for p in palabras]
    candidatos = q.filter(or_(*[KBArticle.title.ilike(f"%{r}%") for r in raices],
                              *[KBArticle.body.ilike(f"%{r}%") for r in raices])).limit(50).all()
    puntuados = []
    for a in candidatos:
        contenido = _sin_tildes(texto_de(a))
        puntuados.append((sum(1 for r in raices if r in contenido) / len(raices), a))
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
    metodo = "vector"
    if puntuados is None:
        puntuados, metodo = _por_palabras(q, texto, limite), "words"
    # `method`: la escala de `score` depende de él (coseno o fracción de palabras).
    return [{"id": a.id, "number": a.number, "title": a.title, "summary": a.summary,
             "score": round(s, 4), "method": metodo} for s, a in puntuados]
