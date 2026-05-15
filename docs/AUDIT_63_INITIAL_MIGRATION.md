# Audit #63 — Migración inicial monolítica (NO ACCIONABLE)

## Hallazgo

`alembic/versions/001_initial_tables_initial_tables.py` tiene **7979 líneas**
y crea ~90 tablas en una sola migración. El audit señaló esto como
"migración inicial monolítica" — difícil de debuggear y no reversible
de forma segura.

## Por qué NO es accionable retroactivamente

**Partir una migración Alembic ya aplicada en producción es destructivo**:

1. La migración 001 ya está en el alembic_version de cada deploy real (dev,
   staging, prod). Romperla en commits posteriores significa que el sistema
   no puede determinar consistentemente el head.
2. SQLite y PostgreSQL han ejecutado las DDL statements; el estado de la
   BD no cambia por reorganizar el código de la migración.
3. Cambiar el `revision` o el `down_revision` de 001 rompe el chain en
   todos los deploys que ya pasaron por ese punto.
4. Crear "001a", "001b" como migraciones posteriores que dropean y
   recrean tablas es masivamente destructivo y borraría datos en prod.

## Mitigaciones aplicadas en migraciones POST-001

Para las próximas migraciones (002+) sí se aplica buena práctica:

- **Granularidad por dominio**: cada migración toca 1-3 tablas
  relacionadas (ej. `074_org_require_mfa`, `075_user_org_memberships`).
- **Defensive helpers**: nuevas migraciones usan `_table_exists()`,
  `_column_exists()`, `_find_unique_constraint()` para ser idempotentes
  ante estado parcial (ver `076_multitenancy_org_id_columns.py`,
  `077_soft_delete_and_constraints.py`).
- **Backfill antes de constraints**: las migraciones que añaden NOT NULL
  hacen `UPDATE table SET column = default WHERE column IS NULL` antes
  de aplicar el constraint (ej. `077`).
- **batch_alter_table para SQLite**: en operaciones que SQLite no soporta
  natívamente (ALTER COLUMN, DROP CONSTRAINT), las migraciones usan
  el wrapper batch.

## Recomendación de futuro

Si en algún momento se hace una migración mayor de schema reset (ej.
nueva arquitectura de modelos en un fork/v2 del proyecto), entonces SÍ
se puede partir la migración inicial en su nueva versión, manteniendo
la 001 actual como histórica. Mientras tanto, **el item #63 queda
como descripción de hecho histórico, no como bug accionable**.

## Estado

- Audit item: **#63 Migración inicial monolítica**
- Estado: ❌ Irrecuperable retroactivamente / ✅ Mitigado en migraciones futuras
- Fecha de revisión: 2026-05-15
