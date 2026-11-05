"""Banco de preguntas validadas de Ask-the-Data (revisión 2026-11, lo que contecintelligence tenía).

Cuando alguien con autoridad (admin o PM) marca una respuesta como correcta, la
pregunta y la consulta del modelo se guardan para su empresa. Después:

- **la misma pregunta** (normalizada: minúsculas, sin acentos ni signos) reutiliza
  esa consulta sin llamar al modelo (`ASK_DATA_REUSE_EXACT_EXAMPLE`);
- **las parecidas** se le dan al modelo como ejemplos: las
  `ASK_DATA_EXAMPLES_IN_PROMPT` con más palabras en común, a partir de
  `ASK_DATA_EXAMPLE_MIN_SIMILARITY` (Jaccard de palabras).

La consulta se valida al guardarla y otra vez cada vez que se ejecuta (sólo
SELECT, tablas permitidas, filtro de empresa y LIMIT añadidos siempre).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional


def normalizar(pregunta: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", pregunta or "").encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"\w+", sin_acentos.lower()))[:500]


def _palabras(texto: str) -> set[str]:
    # Los caracteres chinos no llevan espacios: cada uno cuenta como palabra.
    return {p for p in re.findall(r"\w+", (texto or "").lower()) if len(p) > 2} | set(re.findall(r"[一-鿿]", texto or ""))


def _parecido(a: str, b: str) -> float:
    pa, pb = _palabras(a), _palabras(b)
    return len(pa & pb) / len(pa | pb) if pa and pb else 0.0


def _ajuste(db, clave: str, org, tipo):
    from app.core.config import settings
    from app.services import settings_service as s
    lector = {"int": s.get_runtime_int, "float": s.get_runtime_float, "bool": s.get_runtime_bool}[tipo]
    valor = lector(db, clave, org)
    return getattr(settings, clave) if valor is None else valor


def _de_la_empresa(db, org):
    from app.db.session import sin_filtro_de_tenant
    from app.models.ai_chat import AskDataExample
    with sin_filtro_de_tenant(db):
        return db.query(AskDataExample).filter(
            AskDataExample.organization_id == org if org else AskDataExample.organization_id.is_(None))


def exacta(db, org, pregunta: str):
    """El ejemplo validado con la misma pregunta, si se reutilizan y existe."""
    if not _ajuste(db, "ASK_DATA_REUSE_EXACT_EXAMPLE", org, "bool"):
        return None
    from app.models.ai_chat import AskDataExample
    return _de_la_empresa(db, org).filter(AskDataExample.question_norm == normalizar(pregunta)).first()


def parecidas(db, org, pregunta: str) -> list:
    n = int(_ajuste(db, "ASK_DATA_EXAMPLES_IN_PROMPT", org, "int") or 0)
    if n <= 0:
        return []
    minimo = float(_ajuste(db, "ASK_DATA_EXAMPLE_MIN_SIMILARITY", org, "float"))
    puntuadas = [(p, e) for e in _de_la_empresa(db, org).all() if (p := _parecido(pregunta, e.question)) >= minimo]
    return [e for _, e in sorted(puntuadas, key=lambda x: x[0], reverse=True)[:n]]


def como_ejemplos(ejemplos: list) -> str:
    if not ejemplos:
        return ""
    partes = ["Consultas validadas por esta empresa para preguntas parecidas (úsalas como referencia):"]
    partes += [f"Pregunta: {e.question}\nSQL: {e.sql}" for e in ejemplos]
    return "\n\n".join(partes)


def usada(db, ejemplo) -> None:
    ejemplo.times_used = (ejemplo.times_used or 0) + 1
    ejemplo.last_used_at = datetime.now(timezone.utc)
    db.commit()


def guardar(db, org, usuario_id: Optional[str], pregunta: str, sql: str):
    """Valida y guarda (o sustituye) la consulta de esa pregunta."""
    from app.models.ai_chat import AskDataExample
    from app.services.ask_the_data import validate_sql
    validate_sql(sql, org)          # SQLValidationError si no pasa la política
    sql = re.sub(r"```(?:sql)?", "", sql, flags=re.I).strip().rstrip(";")
    fila = _de_la_empresa(db, org).filter(AskDataExample.question_norm == normalizar(pregunta)).first()
    if fila is None:
        fila = AskDataExample(organization_id=org, question=pregunta.strip(), question_norm=normalizar(pregunta))
        db.add(fila)
    fila.sql, fila.created_by = sql, usuario_id
    db.commit()
    db.refresh(fila)
    return fila


def lista(db, org) -> list[dict]:
    from app.models.ai_chat import AskDataExample
    return [{"id": e.id, "question": e.question, "sql": e.sql, "times_used": e.times_used or 0,
             "last_used_at": e.last_used_at.isoformat() if e.last_used_at else None,
             "created_at": e.created_at.isoformat() if e.created_at else None}
            for e in _de_la_empresa(db, org).order_by(AskDataExample.created_at.desc()).all()]


def borrar(db, org, ejemplo_id: str) -> bool:
    from app.models.ai_chat import AskDataExample
    n = _de_la_empresa(db, org).filter(AskDataExample.id == ejemplo_id).delete(synchronize_session=False)
    db.commit()
    return bool(n)
