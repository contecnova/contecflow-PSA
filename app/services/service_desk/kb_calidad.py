"""Calidad de la base de conocimiento (revisión 2026-11, lo que contecmind ya tenía).

Un solo sitio para preguntar a la base de conocimiento desde la IA:

- `contexto(db, pregunta, …)`: la corrección de un experto que encaje (va por
  delante, es la respuesta autoritativa) y los artículos relevantes, con su
  número para citarlos. Antes el asistente buscaba en `ai_kb_articles` (vacía:
  medido, 0 filas, mientras la base del Service Desk tenía 3 publicados), el
  chat del portal no miraba la base y el bot del portal buscaba la pregunta
  entera como subcadena literal.
- Si una pregunta de un cliente llega sin artículo ni corrección, queda en la
  lista de **preguntas sin respuesta** (`KBGap`), agrupando las repetidas.
- Una **corrección** (`KBCorrection`) se aplica al momento a las preguntas
  parecidas: por vector si hay modelo de frases, si no por palabras.
- La **pasada diaria** avisa de artículos sin revisar desde hace
  `SD_KB_STALE_DAYS` y, con IA, de pares de artículos parecidos que se
  contradicen (como mucho `SD_KB_CONTRADICTION_MAX_PAIRS` por pasada; un par ya
  comparado no se vuelve a comparar hasta que uno de los dos cambie).
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.service_desk import KBArticle, KBStatus
from app.models.service_desk.kb_calidad import KBCorrection, KBFinding, KBGap

logger = logging.getLogger(__name__)


# ── Ajustes ─────────────────────────────────────────────────────────────────

def _f(db: Session, clave: str, org: Optional[str]) -> float:
    from app.services.settings_service import get_runtime_float
    return float(get_runtime_float(db, clave, org) or 0)


def _i(db: Session, clave: str, org: Optional[str]) -> int:
    from app.services.settings_service import get_runtime_int
    return int(get_runtime_int(db, clave, org) or 0)


def _org(db: Session) -> Optional[str]:
    return db.info.get("organization_id")


# ── Preguntas: clave y parecido ─────────────────────────────────────────────

def _palabras(texto: str) -> set[str]:
    from app.services.service_desk.kb_sugerencias import _VACIAS
    plano = unicodedata.normalize("NFKD", (texto or "").lower()).encode("ascii", "ignore").decode()
    return {p for p in re.findall(r"\w{3,}", plano) if p not in _VACIAS}


def clave_de(pregunta: str) -> str:
    """La pregunta normalizada: las mismas palabras en cualquier orden son la misma pregunta."""
    return " ".join(sorted(_palabras(pregunta)))[:255] or (pregunta or "").strip().lower()[:255]


def _vector(texto: str) -> Optional[list]:
    from app.services.service_desk.kb_sugerencias import _a_lista, _modelo
    modelo = _modelo()
    if modelo is None or not texto:
        return None
    return _a_lista(modelo.encode([texto], show_progress_bar=False)[0])


def _parecido(vec_a: Optional[list], palabras_a: set, corr: KBCorrection) -> float:
    if vec_a and corr.question_vec:
        from app.services.semantic_classifier import _cosine
        return float(_cosine(vec_a, json.loads(corr.question_vec)))
    palabras_b = _palabras(corr.question)
    if not palabras_a or not palabras_b:
        return 0.0
    return len(palabras_a & palabras_b) / len(palabras_a | palabras_b)


# ── Correcciones ────────────────────────────────────────────────────────────

def buscar_correccion(db: Session, pregunta: str, *, solo_publica: bool) -> Optional[KBCorrection]:
    q = db.query(KBCorrection).filter(KBCorrection.status == "active")
    if solo_publica:
        q = q.filter(KBCorrection.is_public.is_(True))
    activas = q.all()
    if not activas:
        return None
    umbral = _f(db, "SD_KB_CORRECTION_MATCH", _org(db))
    vec, palabras = _vector(pregunta), _palabras(pregunta)
    mejor = max(((_parecido(vec, palabras, c), c) for c in activas), key=lambda x: x[0])
    return mejor[1] if mejor[0] >= umbral else None


def crear_correccion(db: Session, autor, pregunta: str, respuesta: str, *, es_publica: bool = False,
                     gap_id: Optional[str] = None, article_id: Optional[str] = None) -> KBCorrection:
    pregunta, respuesta = (pregunta or "").strip(), (respuesta or "").strip()
    if not pregunta or not respuesta:
        raise ValueError("pregunta_y_respuesta")
    vec = _vector(pregunta)
    corr = KBCorrection(question=pregunta, answer=respuesta, is_public=bool(es_publica), gap_id=gap_id,
                        article_id=article_id, created_by=getattr(autor, "id", None),
                        organization_id=getattr(autor, "organization_id", None),
                        question_vec=json.dumps(vec) if vec else None)
    db.add(corr)
    db.flush()
    if gap_id:
        hueco = db.get(KBGap, gap_id)
        if hueco:
            hueco.status, hueco.correction_id, hueco.closed_by = "answered", corr.id, corr.created_by
    db.commit()
    return corr


# ── Huecos ──────────────────────────────────────────────────────────────────

def registrar_hueco(db: Session, pregunta: str, origen: str) -> Optional[KBGap]:
    """Suma una pregunta sin respuesta (agrupa las repetidas). No confirma."""
    pregunta = (pregunta or "").strip()
    if len(pregunta) < 8:
        return None
    clave = clave_de(pregunta)
    hueco = db.query(KBGap).filter(KBGap.question_key == clave).first()
    ahora = datetime.now(timezone.utc)
    if hueco:
        hueco.times_asked = (hueco.times_asked or 0) + 1
        hueco.question, hueco.last_asked_at = pregunta[:4000], ahora
        if hueco.status == "dismissed":
            return hueco                     # descartada: se cuenta, pero no vuelve a la lista
        hueco.status = "open"
        return hueco
    hueco = KBGap(question_key=clave, question=pregunta[:4000], source=origen, organization_id=_org(db),
                  first_asked_at=ahora, last_asked_at=ahora)
    db.add(hueco)
    return hueco


# ── Contexto para la IA ─────────────────────────────────────────────────────

def fuentes(db: Session, pregunta: str, *, solo_publico: bool) -> list[dict]:
    """Artículos lo bastante relevantes para citarlos (umbral según cómo se buscó)."""
    from app.services.service_desk.kb_sugerencias import sugerir
    org = _org(db)
    maximo = max(1, _i(db, "SD_KB_RAG_MAX_SOURCES", org))
    umbral = {"vector": _f(db, "SD_KB_RAG_MIN_SCORE_VECTOR", org),
              "words": _f(db, "SD_KB_RAG_MIN_SCORE_WORDS", org)}
    candidatos = sugerir(db, pregunta, solo_publico=solo_publico, limite=maximo)
    return [c for c in candidatos if c["score"] >= umbral.get(c.get("method"), 1.0)]


def contexto(db: Session, pregunta: str, *, solo_publico: bool, origen: Optional[str] = None) -> dict:
    """{prompt, sources, correction}. Con `origen`, una pregunta sin nada se apunta como hueco."""
    correccion = buscar_correccion(db, pregunta, solo_publica=solo_publico)
    citas = fuentes(db, pregunta, solo_publico=solo_publico)
    partes = []
    if correccion:
        correccion.usage_count = (correccion.usage_count or 0) + 1
        correccion.last_used_at = datetime.now(timezone.utc)
        partes.append("RESPUESTA VALIDADA POR UN EXPERTO para una pregunta como esta. Si responde a lo que "
                      f"se pregunta, úsala por encima de todo lo demás:\n{correccion.answer}")
    if citas:
        cuerpos = {a.id: a for a in db.query(KBArticle).filter(KBArticle.id.in_([c["id"] for c in citas]))}
        bloques = []
        for c in citas:
            a = cuerpos.get(c["id"])
            texto = (a.body if a else c.get("summary")) or ""
            bloques.append(f"[{c['number']}] {c['title']}\n{texto[:1200]}")
        partes.append("ARTÍCULOS DE LA BASE DE CONOCIMIENTO. Si los usas, cita su número entre corchetes, "
                      "p. ej. [" + citas[0]["number"] + "]. No inventes números:\n\n" + "\n\n".join(bloques))
    if not partes and origen:
        registrar_hueco(db, pregunta, origen)
    return {"prompt": ("\n\n" + "\n\n".join(partes)) if partes else "",
            "sources": [{"id": c["id"], "number": c["number"], "title": c["title"]} for c in citas],
            "correction": bool(correccion)}


# ── Pasada diaria: caducados y contradicciones ──────────────────────────────

def _avisar(db: Session, articulo: KBArticle, titulo: str, cuerpo: str) -> None:
    from app.services.notifications import notify_user
    destinatario = articulo.author_id or articulo.reviewer_id
    if destinatario:
        notify_user(db, destinatario, "system", titulo, cuerpo, resource="kb_article",
                    resource_id=articulo.id, action_url="/service-desk?tab=kb")


def _aviso(db: Session, clave: str, **campos) -> tuple[KBFinding, bool]:
    fila = db.query(KBFinding).filter(KBFinding.dedupe_key == clave).first()
    if fila:
        fila.last_seen_at = datetime.now(timezone.utc)
        return fila, False
    fila = KBFinding(dedupe_key=clave, organization_id=_org(db), **campos)
    db.add(fila)
    db.flush()
    return fila, True


def _cuando(a: KBArticle) -> datetime:
    momento = a.updated_at or a.published_at or a.created_at or datetime.now(timezone.utc)
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def _caducados(db: Session, org: str) -> int:
    dias = _i(db, "SD_KB_STALE_DAYS", org)
    if dias <= 0:
        return 0
    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    n = 0
    for a in db.query(KBArticle).filter(KBArticle.status == KBStatus.published):
        cuando = _cuando(a)
        if cuando >= limite:
            continue
        _, nuevo = _aviso(db, f"stale:{a.id}:{cuando.date()}", kind="stale", article_id=a.id,
                          detail=f"Sin cambios desde {cuando.date()}")
        if nuevo:
            n += 1
            _avisar(db, a, f"Revisa el artículo {a.number}",
                    f"«{a.title}» no se ha revisado desde {cuando.date()}.")
    return n


def preguntar_contradiccion(db: Session, a: KBArticle, b: KBArticle, org: str) -> dict:
    """{"contradicts": bool, "explanation": str} según la IA. Separada para poder sustituirla en pruebas."""
    from app.services.ai_provider_service import call_ai
    sistema = ("Comparas dos artículos de una base de conocimiento. Responde SOLO con JSON "
               '{"contradicts": true|false, "explanation": "<una frase>"}. contradicts es true solo si '
               "dan instrucciones o datos incompatibles sobre lo mismo (no si uno amplía al otro).")
    texto = f"ARTÍCULO A [{a.number}] {a.title}\n{(a.body or '')[:2500]}\n\nARTÍCULO B [{b.number}] {b.title}\n{(b.body or '')[:2500]}"
    bruto = call_ai(db, [{"role": "user", "content": texto}], system=sistema, module="knowledge_base",
                    max_tokens=300, organization_id=org)
    limpio = re.sub(r"^```(json)?|```$", "", (bruto or "").strip(), flags=re.M).strip()
    datos = json.loads(limpio[limpio.find("{"): limpio.rfind("}") + 1])
    return {"contradicts": bool(datos.get("contradicts")), "explanation": str(datos.get("explanation") or "")[:1000]}


def _contradicciones(db: Session, org: str) -> dict:
    maximo = _i(db, "SD_KB_CONTRADICTION_MAX_PAIRS", org)
    if maximo <= 0:
        return {"checked": 0, "found": 0, "skipped": "off"}
    from app.services.ai_provider_service import get_default_provider
    if not get_default_provider(db, organization_id=org):
        return {"checked": 0, "found": 0, "skipped": "sin proveedor de IA"}
    from app.services.semantic_classifier import _cosine
    umbral = _f(db, "SD_KB_CONTRADICTION_SIMILARITY", org)
    articulos = [a for a in db.query(KBArticle).filter(KBArticle.status == KBStatus.published,
                                                       KBArticle.embedding.isnot(None))]
    vectores = {a.id: json.loads(a.embedding) for a in articulos}
    pares = []
    for i, a in enumerate(articulos):
        for b in articulos[i + 1:]:
            s = float(_cosine(vectores[a.id], vectores[b.id]))
            if s >= umbral:
                x, y = sorted([a, b], key=lambda r: r.id)
                pares.append((s, x, y))
    pares.sort(key=lambda p: p[0], reverse=True)
    comprobados = encontrados = 0
    for s, a, b in pares:
        if comprobados >= maximo:
            break
        clave = f"contradiction:{a.id}:{_cuando(a).isoformat()}:{b.id}:{_cuando(b).isoformat()}"[:255]
        if db.query(KBFinding.id).filter(KBFinding.dedupe_key == clave).first():
            continue                                   # ya comparados con estas versiones
        comprobados += 1
        try:
            veredicto = preguntar_contradiccion(db, a, b, org)
        except Exception:
            logger.warning("kb: no se pudo comparar %s y %s", a.number, b.number, exc_info=True)
            continue
        fila, _ = _aviso(db, clave, kind="contradiction", article_id=a.id, other_article_id=b.id,
                         score=round(s, 4), detail=veredicto["explanation"],
                         status="open" if veredicto["contradicts"] else "checked")
        if veredicto["contradicts"]:
            encontrados += 1
            for art, otro in ((a, b), (b, a)):
                _avisar(db, art, f"{art.number} contradice a {otro.number}", veredicto["explanation"])
    return {"checked": comprobados, "found": encontrados}


def pasada(db: Session, org: str) -> dict:
    """Caducados y contradicciones de una empresa. Confirma."""
    salida = {"stale": _caducados(db, org)}
    salida["contradictions"] = _contradicciones(db, org)
    db.commit()
    return salida


def pasada_diaria(db: Session) -> dict:
    from app.services.service_desk.ticket_events import como_organizacion
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        orgs = [o for (o,) in db.query(KBArticle.organization_id).filter(
            KBArticle.status == KBStatus.published, KBArticle.organization_id.isnot(None)).distinct()]
    salida = {}
    for org in orgs:
        with como_organizacion(db, org):
            try:
                salida[org] = pasada(db, org)
            except Exception:
                db.rollback()
                logger.exception("kb: la pasada de calidad falló en %s", org)
    return salida


def pasada_diaria_job() -> None:
    from app.db.session import worker_db_session
    with worker_db_session() as db:
        logger.info("kb, pasada de calidad: %s", pasada_diaria(db))


# ── Para la pantalla ────────────────────────────────────────────────────────

def resumen(db: Session) -> dict:
    titulos = dict(db.query(KBArticle.id, KBArticle.number).all())
    huecos = db.query(KBGap).filter(KBGap.status == "open").order_by(
        KBGap.times_asked.desc(), KBGap.last_asked_at.desc()).limit(200).all()
    correcciones = db.query(KBCorrection).filter(KBCorrection.status == "active").order_by(
        KBCorrection.created_at.desc()).limit(200).all()
    avisos = db.query(KBFinding).filter(KBFinding.status == "open").order_by(
        KBFinding.kind, KBFinding.first_seen_at.desc()).limit(200).all()
    return {
        "gaps": [{"id": g.id, "question": g.question, "times_asked": g.times_asked, "source": g.source,
                  "last_asked_at": g.last_asked_at.isoformat() if g.last_asked_at else None} for g in huecos],
        "corrections": [{"id": c.id, "question": c.question, "answer": c.answer, "is_public": c.is_public,
                         "usage_count": c.usage_count,
                         "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None}
                        for c in correcciones],
        "findings": [{"id": f.id, "kind": f.kind, "article_id": f.article_id,
                      "article_number": titulos.get(f.article_id), "other_article_id": f.other_article_id,
                      "other_article_number": titulos.get(f.other_article_id), "detail": f.detail,
                      "first_seen_at": f.first_seen_at.isoformat() if f.first_seen_at else None}
                     for f in avisos],
        "counts": {"gaps": len(huecos), "corrections": len(correcciones), "findings": len(avisos)},
    }


def cerrar(db: Session, modelo, fila_id: str, estado: str, usuario) -> None:
    validos = {KBGap: {"dismissed", "open", "answered"}, KBFinding: {"resolved", "dismissed"},
               KBCorrection: {"archived", "active"}}[modelo]
    if estado not in validos:
        raise ValueError("estado")
    fila = db.get(modelo, fila_id)
    if fila is None:
        raise LookupError("no_encontrado")
    fila.status = estado
    if hasattr(fila, "closed_by"):
        fila.closed_by = getattr(usuario, "id", None)
    db.commit()
