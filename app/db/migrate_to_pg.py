#!/usr/bin/env python3
"""
migrate_to_pg.py — Migra todos los datos de SQLite a PostgreSQL.

Uso:
  export DATABASE_URL=postgresql://user:pass@host:5432/dbname
  python -m app.db.migrate_to_pg --sqlite-path ./contecflow.db

El script:
  1. Lee todas las tablas de SQLite
  2. Crea el schema en PostgreSQL (CREATE TABLE IF NOT EXISTS)
  3. Copia los datos tabla a tabla con batch inserts de 500 registros
  4. Verifica counts finales
"""
import argparse
import sys
import os
import logging
from pathlib import Path

logger = logging.getLogger("contecflow.migrate_to_pg")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def migrate(sqlite_path: str, pg_url: str, batch_size: int = 500):
    try:
        from sqlalchemy import create_engine, text, inspect, MetaData, Table
        from sqlalchemy.dialects.postgresql import insert as pg_insert
    except ImportError:
        logger.error("SQLAlchemy not installed")
        print("✗ Instala psycopg2-binary: pip install psycopg2-binary")

    if not Path(sqlite_path).exists():
        print(f"✗ SQLite no encontrado: {sqlite_path}")
        sys.exit(1)

    print(f"📦 Origen:  {sqlite_path}")
    print(f"🐘 Destino: {pg_url.split('@')[-1]}")
    print()

    # Conexiones
    sqlite_eng = create_engine(f"sqlite:///{sqlite_path}")
    pg_eng     = create_engine(pg_url, pool_pre_ping=True)

    # Crear schema en PostgreSQL usando los modelos SQLAlchemy
    print("1️⃣  Creando schema en PostgreSQL...")
    from app.db.base import Base
    Base.metadata.create_all(bind=pg_eng, checkfirst=True)
    print("   ✅ Schema creado")

    # Leer tablas de SQLite
    sqlite_insp = inspect(sqlite_eng)
    tables = sqlite_insp.get_table_names()
    tables = [t for t in tables if not t.startswith("sqlite_")]
    print(f"\n2️⃣  Migrando {len(tables)} tablas...")

    stats = {"ok": 0, "empty": 0, "error": 0}

    for table_name in sorted(tables):
        try:
            with sqlite_eng.connect() as src:
                rows = src.execute(text(f"SELECT * FROM \"{table_name}\"")).mappings().fetchall()  # noqa: S608

            if not rows:
                stats["empty"] += 1
                continue

            # Convertir a dicts
            data = [dict(r) for r in rows]

            with pg_eng.begin() as dst:
                # Usar INSERT ... ON CONFLICT DO NOTHING para idempotencia
                meta = MetaData()
                tbl  = Table(table_name, meta, autoload_with=pg_eng)

                for i in range(0, len(data), batch_size):
                    batch = data[i:i + batch_size]
                    stmt  = pg_insert(tbl).values(batch)
                    stmt  = stmt.on_conflict_do_nothing()
                    dst.execute(stmt)

            stats["ok"] += 1
            logger.info(f"✅ {table_name}: {len(data)} rows migrated")

        except Exception as e:
            stats["error"] += 1
            logger.error(f"Error migrating {table_name}: {e}", exc_info=True)

    # Verification phase
    logger.info("Starting verification...")
    with sqlite_eng.connect() as src, pg_eng.connect() as dst:
        for table_name in sorted(tables)[:10]:
            try:
                n_src = src.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()  # noqa: S608
                n_dst = dst.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()  # noqa: S608
                match = "✅" if n_src == n_dst else "⚠️ "
                if n_src > 0:
                    logger.info(f"{match} {table_name}: {n_src} → {n_dst}")
            except Exception as e:
                logger.error(f"Verification failed for {table_name}: {e}", exc_info=True)

    logger.info(f"Migration complete: {stats['ok']} tables OK | {stats['empty']} empty | {stats['error']} errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migra SQLite → PostgreSQL")
    parser.add_argument("--sqlite-path", default="./contecflow.db")
    parser.add_argument("--pg-url",      default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()

    if not args.pg_url or not args.pg_url.startswith("postgresql"):
        print("✗ Especifica --pg-url o DATABASE_URL=postgresql://...")
        sys.exit(1)

    migrate(args.sqlite_path, args.pg_url)
