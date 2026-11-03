"""Vectores de la base de conocimiento en Postgres (pgvector), cuando lo hay.

Auditoria 2026-11: la busqueda por vectores comparaba en Python contra todos
los articulos publicados (cada vector viaja de la base al proceso). Con
pgvector la base ordena por distancia del coseno y, con indice HNSW, sin
recorrerlos todos.

Es opcional y se decide midiendo, no por configuracion:

- la columna `sd_kb_articles.embedding_vec` solo existe si el Postgres tiene la
  extension `vector` (migracion 116, o `preparar` a mano tras cambiar a una
  imagen con pgvector);
- sin ella, `disponible()` da False y la busqueda sigue en Python, como antes.

La columna no esta en el modelo ORM a proposito: en una base sin pgvector,
cada consulta de articulos fallaria. Se lee y se escribe con SQL.

El indice HNSW necesita la dimension del vector, que depende del modelo de
frases; se crea la primera vez que se guarda uno (`_asegurar_indice`).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TABLA, COLUMNA = "sd_kb_articles", "embedding_vec"
_disponible: dict[str, bool] = {}
_indices: set[tuple[str, int]] = set()


def _clave(db: Session) -> str:
    return str(db.get_bind().url)


def disponible(db: Session) -> bool:
    """Postgres con la columna de vectores. Se mide una vez por base y proceso."""
    clave = _clave(db)
    if clave not in _disponible:
        bind = db.get_bind()
        _disponible[clave] = bind.dialect.name == "postgresql" and any(
            c["name"] == COLUMNA for c in inspect(bind).get_columns(TABLA))
    return _disponible[clave]


def preparar(conexion) -> bool:
    """Crea la extension y la columna si el Postgres lo permite, y rellena desde `embedding`.

    La usa la migracion 116; tambien sirve a mano tras cambiar a una imagen
    con pgvector. Devuelve si quedo preparada.
    """
    if conexion.dialect.name != "postgresql":
        return False
    hay = conexion.execute(text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")).first()
    if not hay:
        logger.info("pgvector no esta disponible en este Postgres: la KB busca en Python")
        return False
    conexion.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conexion.execute(text(f"ALTER TABLE {TABLA} ADD COLUMN IF NOT EXISTS {COLUMNA} vector"))
    # `embedding` guarda el vector como JSON («[0.1, 0.2, ...]»), que es tambien
    # el formato de texto de pgvector.
    conexion.execute(text(f"UPDATE {TABLA} SET {COLUMNA} = CAST(embedding AS vector) "
                          f"WHERE embedding IS NOT NULL AND {COLUMNA} IS NULL"))
    return True


def _asegurar_indice(db: Session, dimension: int) -> None:
    clave = (_clave(db), dimension)
    if clave in _indices:
        return
    db.execute(text(
        f"CREATE INDEX IF NOT EXISTS ix_sd_kb_embedding_vec_{dimension} ON {TABLA} "
        f"USING hnsw (({COLUMNA}::vector({dimension})) vector_cosine_ops)"))
    _indices.add(clave)


def guardar(db: Session, article_id: str, vector: Optional[list]) -> None:
    """Copia el vector del articulo a la columna de pgvector (o la vacia)."""
    if not disponible(db):
        return
    db.flush()
    db.execute(text(f"UPDATE {TABLA} SET {COLUMNA} = CAST(:v AS vector) WHERE id = :id"),
               {"v": json.dumps(vector) if vector else None, "id": article_id})
    if vector:
        _asegurar_indice(db, len(vector))


def buscar(db: Session, ids_visibles: list[str], consulta: list, limite: int) -> list[tuple[float, str]]:
    """(similitud, id) de los articulos visibles mas parecidos, ordenados en la base.

    `ids_visibles` sale de la consulta ORM, que ya filtra estado, publico y
    organizacion (solo viajan ids, no vectores). Mismo cast que el indice,
    para que lo use.
    """
    if not ids_visibles:
        return []
    n = len(consulta)
    filas = db.execute(text(
        f"SELECT id, 1 - ({COLUMNA}::vector({n}) <=> CAST(:q AS vector({n}))) AS similitud "
        f"FROM {TABLA} WHERE {COLUMNA} IS NOT NULL AND vector_dims({COLUMNA}) = :n AND id = ANY(:ids) "
        f"ORDER BY {COLUMNA}::vector({n}) <=> CAST(:q AS vector({n})) LIMIT :limite"),
        {"q": json.dumps(consulta), "n": n, "ids": list(ids_visibles), "limite": limite}).all()
    return [(float(s), i) for i, s in filas]
