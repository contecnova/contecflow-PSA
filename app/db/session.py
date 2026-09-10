"""
session.py — Configuración de base de datos con soporte dual SQLite / PostgreSQL.

- SQLite:     DATABASE_URL no definida, o empieza por sqlite:///  → desarrollo local
- PostgreSQL: DATABASE_URL=postgresql://user:pass@host:5432/dbname → producción

Para migrar datos de SQLite a PostgreSQL:
  python -m app.db.migrate_to_pg
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def _extract_model_class(entity):
    """Return the ORM mapped class from an entity (class, InstrumentedAttribute, etc.)."""
    if isinstance(entity, type):
        return entity
    # InstrumentedAttribute e.g. Project.id, Project.name
    if hasattr(entity, "class_"):
        return entity.class_
    # Label / AnnotatedColumn
    if hasattr(entity, "property") and hasattr(entity.property, "parent"):
        try:
            return entity.property.parent.class_
        except Exception:
            logger.debug("_extract_model_class: fallo best-effort ignorado", exc_info=True)
    return None


class TenantIsolationError(RuntimeError):
    """No se puede demostrar el aislamiento de tenant para una consulta.

    Se lanza en vez de devolver la consulta sin filtrar. Un 500 es un incidente
    que se investiga; una consulta sin filtro de tenant es una fuga silenciosa
    entre clientes que nadie ve (auditoría 2026-08, P1-7).
    """


def _is_tenant_exempt(model) -> bool:
    """¿Está el modelo exento del filtro automático, de forma declarada?

    La exención se declara en el propio modelo con ``_tenant_exempt = True`` (ver
    app/models/mfa.py::Organization), no aquí, para que se vea al leerlo. Un
    modelo al que simplemente le falte la columna de tenant NO está exento: eso
    era el fail-open que este cambio elimina.
    """
    return getattr(model, "_tenant_exempt", False) is True


def _tenant_filter_for_model(query, model, org_id):
    """Inject tenant isolation filter into *query* for the given *model*.

    Precedence:
    1. Model has ``organization_id`` column directly → filter by it.
    2. Model has ``org_id`` column → filter by it.
    3. Model has a ``project_id`` FK column → use a subquery against projects.
    4. Model has a direct FK to users → use a subquery against users.
    5. Model has ``actor_id`` → use a subquery against users.
    6. Model declares ``_tenant_exempt = True`` → pasa sin filtrar, con motivo.
    7. Nada de lo anterior → ``TenantIsolationError`` (fail-closed).

    El paso 7 antes era "devolver la consulta sin filtrar, más seguro que
    petar". No lo era: convertía cada modelo nuevo sin columna de tenant en una
    fuga entre clientes que ninguna prueba detectaba.
    """
    if org_id is None:
        return query

    if hasattr(model, "organization_id"):
        # Some models (e.g. AppSetting) mark themselves to also include
        # global (org_id IS NULL) rows alongside tenant-specific ones.
        if getattr(model, "_tenant_filter_include_global", False):
            from sqlalchemy import or_
            return query.filter(
                or_(model.organization_id == org_id, model.organization_id.is_(None))
            )
        return query.filter(model.organization_id == org_id)

    if hasattr(model, "org_id"):
        return query.filter(model.org_id == org_id)

    # Subquery route — avoids JOIN conflicts on already-joined queries.
    if hasattr(model, "project_id"):
        from sqlalchemy import select as sa_select
        from app.models.project import Project
        project_ids_sq = (
            sa_select(Project.id)
            .where(Project.organization_id == org_id)
            .scalar_subquery()
        )
        return query.filter(model.project_id.in_(project_ids_sq))

    if hasattr(model, "user_id"):
        from sqlalchemy import select as sa_select
        from app.models.user import User
        user_ids_sq = (
            sa_select(User.id)
            .where(User.organization_id == org_id)
            .scalar_subquery()
        )
        return query.filter(model.user_id.in_(user_ids_sq))

    # Fallback: models (e.g. ActivityEvent) that link to users via actor_id
    if hasattr(model, "actor_id"):
        from sqlalchemy import select as sa_select
        from app.models.user import User
        user_ids_sq = (
            sa_select(User.id)
            .where(User.organization_id == org_id)
            .scalar_subquery()
        )
        return query.filter(model.actor_id.in_(user_ids_sq))

    if _is_tenant_exempt(model):
        return query

    raise TenantIsolationError(
        f"{getattr(model, '__name__', model)} no tiene columna de tenant "
        "(organization_id / org_id / project_id / user_id / actor_id) ni declara "
        "_tenant_exempt = True. No se puede aislar por organización: revisa el "
        "modelo antes de consultarlo desde una petición de usuario."
    )


def _extract_models_from_select(stmt):
    """Return ORM model classes referenced by a SA 2.0 Select statement.

    Resolves Table objects from stmt.froms back to their mapped class via
    SA 2.0's public registry API (Base.registry.mappers).
    """
    from sqlalchemy import Table

    models: list = []
    seen: set = set()
    try:
        froms = list(stmt.froms)
    except Exception:
        return models

    if not froms:
        return models

    try:
        from app.db.base import Base
        table_to_class = {
            mapper.persist_selectable: mapper.class_
            for mapper in Base.registry.mappers
        }
    except Exception:
        return models

    for from_clause in froms:
        if isinstance(from_clause, Table):
            cls = table_to_class.get(from_clause)
            if cls is not None and cls not in seen:
                seen.add(cls)
                models.append(cls)

    return models


def _tenant_where_for_model(stmt, model, org_id):
    """Inject tenant isolation into a SA 2.0 Select statement via .where().

    Mirrors _tenant_filter_for_model but operates on Select objects instead
    of legacy Query objects — incluida la misma política fail-closed.
    """
    if org_id is None:
        return stmt

    if hasattr(model, "organization_id"):
        if getattr(model, "_tenant_filter_include_global", False):
            from sqlalchemy import or_
            return stmt.where(or_(model.organization_id == org_id, model.organization_id.is_(None)))
        return stmt.where(model.organization_id == org_id)

    if hasattr(model, "org_id"):
        return stmt.where(model.org_id == org_id)

    if hasattr(model, "project_id"):
        from sqlalchemy import select as sa_select
        from app.models.project import Project
        project_ids_sq = (
            sa_select(Project.id)
            .where(Project.organization_id == org_id)
            .scalar_subquery()
        )
        return stmt.where(model.project_id.in_(project_ids_sq))

    if hasattr(model, "user_id"):
        from sqlalchemy import select as sa_select
        from app.models.user import User
        user_ids_sq = (
            sa_select(User.id)
            .where(User.organization_id == org_id)
            .scalar_subquery()
        )
        return stmt.where(model.user_id.in_(user_ids_sq))

    if hasattr(model, "actor_id"):
        from sqlalchemy import select as sa_select
        from app.models.user import User
        user_ids_sq = (
            sa_select(User.id)
            .where(User.organization_id == org_id)
            .scalar_subquery()
        )
        return stmt.where(model.actor_id.in_(user_ids_sq))

    if _is_tenant_exempt(model):
        return stmt

    raise TenantIsolationError(
        f"{getattr(model, '__name__', model)} no tiene columna de tenant ni declara "
        "_tenant_exempt = True. No se puede aislar por organización."
    )


class TenantSession(Session):
    """SQLAlchemy session that transparently injects tenant (org) isolation.

    When ``db.info["organization_id"]`` is set the session automatically adds
    WHERE clauses so that every ORM query is scoped to the current tenant.
    Superadmin requests set the value to *None*, which disables filtering and
    allows full cross-tenant visibility.
    """

    def query(self, *entities, **kwargs):
        q = super().query(*entities, **kwargs)

        # Auditoria 2026-08. `bypass_tenant_filter` estaba documentado en la
        # cabecera de `do_orm_execute` como «escape hatch por sesion», y **de las
        # tres capas de aislamiento solo lo respetaba esa**. Es decir: un script
        # de migracion o un trabajo de analitica entre tenants que lo pusiera
        # seguia filtrado por `query()` y por `execute()`, que son justo las dos
        # que usa el codigo normal. Una bandera documentada que no hace lo que
        # dice es peor que no tenerla, porque quien la usa cree que ya esta.
        #
        # Salio arreglando un 500 real: mover un usuario a otra organizacion y
        # releerlo despues. Ver `sin_filtro_de_tenant`, que es la unica forma
        # recomendada de encenderla.
        if self.info.get("bypass_tenant_filter") is True:
            return q

        # is_superadmin is explicitly set by deps.get_current_user:
        #   True  → superadmin, bypass all tenant filters
        #   False → regular user, enforce tenant isolation
        #   None  → session not initialised by a request (background job / test)
        #           → bypass for backward compatibility
        is_superadmin = self.info.get("is_superadmin", None)
        if is_superadmin is None or is_superadmin is True:
            return q

        org_id = self.info.get("organization_id")
        if org_id is None:
            # Regular user with no organisation assigned — block cross-tenant leakage
            # by returning an empty result set instead of bypassing all filters.
            from sqlalchemy import false as sql_false
            return q.filter(sql_false())

        # Resolve all entities to mapped model classes (handles both class
        # and InstrumentedAttribute patterns, e.g. db.query(Project.id)).
        # Deduplicate so a model appearing multiple times (e.g. self-join) only
        # gets one filter clause, preserving query correctness and performance.
        seen: set = set()
        models: list = []
        for e in entities:
            candidate = _extract_model_class(e)
            if candidate is not None and candidate not in seen:
                seen.add(candidate)
                models.append(candidate)

        if not models:
            return q

        # Apply tenant isolation for every resolved model so that all tables
        # in a multi-entity JOIN are scoped to the current tenant, not just
        # the first one.
        # Fail-closed (auditoría 2026-08, P1-7). Antes esto era
        # `except Exception: logger.debug(...)`, así que si el filtro fallaba para
        # un modelo la consulta seguía SIN filtro de tenant y solo quedaba rastro
        # en un log de nivel debug. Un error propagado es un incidente que se
        # investiga; una consulta sin filtrar es una fuga que nadie ve.
        for model in models:
            q = _tenant_filter_for_model(q, model, org_id)

        return q

    def execute(self, statement, *args, **kwargs):
        """SA 2.0 execute() override — applies tenant isolation to ORM Select statements.

        db.query() intercepts the legacy SA 1.x API; this method covers the
        modern SA 2.0 pattern: db.execute(select(Model).where(...)).
        Non-Select statements (INSERT, UPDATE, DELETE, raw SQL) pass through
        unchanged — they carry explicit WHERE clauses by design.
        """
        from sqlalchemy.sql import Select
        if isinstance(statement, Select) and self.info.get("bypass_tenant_filter") is not True:
            is_superadmin = self.info.get("is_superadmin", None)
            if is_superadmin is False:
                org_id = self.info.get("organization_id")
                if org_id is None:
                    from sqlalchemy import false as sql_false
                    statement = statement.where(sql_false())
                else:
                    # Fail-closed, igual que en query(). Ver el comentario de allí.
                    for model in _extract_models_from_select(statement):
                        statement = _tenant_where_for_model(statement, model, org_id)
        return super().execute(statement, *args, **kwargs)

_url = settings.DATABASE_URL
_is_sqlite = _url.startswith("sqlite")

# ── Opciones según motor ───────────────────────────────────────────────────────
if _is_sqlite:
    engine = create_engine(
        _url,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA cache_size=-64000")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA mmap_size=268435456")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.close()

else:
    # PostgreSQL — pool optimizado para producción
    engine = create_engine(
        _url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,       # reconecta automáticamente si la conexión muere
        pool_recycle=3600,        # recicla conexiones cada hora
        echo=False,
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=TenantSession)


# ── Audit #C5: global tenant isolation via do_orm_execute ─────────────────────
#
# `TenantSession.query()` and `.execute(Select)` already inject org filters for
# the common code paths. The remaining gap is lazy-loaded relationships and any
# raw `session.execute(select(Model))` that bypasses our overrides at runtime
# (e.g. SA internals during refresh).
#
# `do_orm_execute` is SA 2.0's canonical hook for this: it fires for every ORM
# statement and lets us attach `with_loader_criteria` clauses that the SA
# planner applies wherever the model appears (including eager/lazy joins).
#
# Bypass options:
#   • `session.info["is_superadmin"] = True` — already used for superadmin paths.
#   • `session.info["bypass_tenant_filter"] = True` — explicit per-session escape
#     hatch for migration scripts / cross-tenant analytics jobs. Auditoria
#     2026-08: lo respetan **las tres** capas desde entonces; antes solo esta, y
#     `query()`/`execute()` —las que usa el codigo normal— lo ignoraban. Usalo
#     via `sin_filtro_de_tenant(session)`, que lo devuelve al salir.
#   • Set env `TENANT_AUTO_FILTER_GLOBAL=0` to disable the event entirely.

import os as _os
from contextlib import contextmanager as _contextmanager
from sqlalchemy import event as _sa_event
from sqlalchemy import false as _sql_false_expr
from sqlalchemy.orm import with_loader_criteria as _with_loader_criteria

_TENANT_AUTO_FILTER_GLOBAL = _os.getenv("TENANT_AUTO_FILTER_GLOBAL", "1") == "1"


def _iter_tenant_scoped_models():
    """Yield mapped ORM classes that carry an `organization_id` column."""
    try:
        from app.db.base import Base
    except Exception:
        return
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if hasattr(cls, "organization_id"):
            yield cls


if _TENANT_AUTO_FILTER_GLOBAL:

    @_sa_event.listens_for(SessionLocal, "do_orm_execute")
    def _enforce_tenant_isolation(execute_state) -> None:
        # Only filter ORM SELECT statements; INSERT/UPDATE/DELETE carry their
        # own WHERE clauses and would be incorrectly narrowed otherwise.
        if not execute_state.is_select:
            return
        if execute_state.is_relationship_load:
            # Relationship loads already inherit their parent's tenant scope
            # (parent row was filtered when loaded). Skipping avoids double
            # filtering joined-eager loads where the cross-table FK is the
            # legitimate access path.
            return

        session = execute_state.session
        info = getattr(session, "info", {}) or {}

        if info.get("bypass_tenant_filter") is True:
            return
        is_superadmin = info.get("is_superadmin", None)
        if is_superadmin is None or is_superadmin is True:
            # Uninitialised session (background job, test) or superadmin: skip.
            return
        org_id = info.get("organization_id")
        sin_organizacion = org_id is None
        # Regular user with no org → block any data return.
        #
        # Auditoria 2026-08: esta rama NO bloqueaba, reventaba. Pasaba `object`
        # como objetivo de `with_loader_criteria`, y SA recorre
        # `object.__subclasses__()` hasta llamar a `type.__subclasses__()` sin
        # instancia: `TypeError: unbound method type.__subclasses__() needs an
        # argument`. Es decir, un usuario normal sin organizacion —o un simple
        # refresco de atributos antes de que la sesion tenga su
        # `organization_id`— daba un 500 en CUALQUIER consulta ORM en vez de no
        # devolver filas.
        #
        # El bloqueo se hace ahora con el MISMO mecanismo que el filtro normal,
        # un criterio por modelo, y no tocando `execute_state.statement` con un
        # `.where(false())`: las opciones de criterio entran en la clave de la
        # cache de sentencias compiladas de SA y una modificacion directa de la
        # sentencia no, asi que la SQL con `WHERE false` se reutilizaba despues
        # para la misma consulta con organizacion valida y devolvia cero filas.

        # Attach a loader_criteria for every tenant-scoped model. SA filters out
        # criteria whose target class is not in the statement, so the cost is
        # mostly evaluation at plan time, not execution.
        #
        # Auditoria 2026-08 — FUGA ENTRE TENANTS. El criterio se escribia como
        # `lambda cls, _org=org_id: cls.organization_id == _org`, metiendo la
        # organizacion en un ARGUMENTO POR DEFECTO. El sistema de lambdas de
        # SQLAlchemy analiza las **variables de cierre** para convertirlas en
        # parametros ligados, pero no los argumentos por defecto: esos se
        # evaluan al crear la lambda y quedan cocidos en la sentencia compilada
        # que se guarda en la cache del engine, que es de proceso. Resultado
        # comprobado: la primera organizacion que pasaba por aqui fijaba el
        # filtro, y la SIGUIENTE organizacion recibia las filas de la primera.
        #
        #   sesion 1 (ORG-A) -> ['ORG-A']
        #   sesion 2 (ORG-B) -> ['ORG-A']   <-- datos de otro tenant
        #
        # Con `org_id` como variable de cierre, SA lo extrae como parametro y
        # cada sesion filtra por la suya. No es un detalle de estilo: es la
        # diferencia entre que este control aisle o no.
        criteria_options = []
        for model in _iter_tenant_scoped_models():
            if sin_organizacion:
                criteria_options.append(
                    _with_loader_criteria(
                        model,
                        lambda cls: _sql_false_expr(),
                        include_aliases=True,
                    )
                )
                continue
            include_global = getattr(model, "_tenant_filter_include_global", False)
            if include_global:
                from sqlalchemy import or_ as _or
                criteria_options.append(
                    _with_loader_criteria(
                        model,
                        lambda cls: _or(
                            cls.organization_id == org_id,
                            cls.organization_id.is_(None),
                        ),
                        include_aliases=True,
                    )
                )
            else:
                criteria_options.append(
                    _with_loader_criteria(
                        model,
                        lambda cls: cls.organization_id == org_id,
                        include_aliases=True,
                    )
                )
        if criteria_options:
            execute_state.statement = execute_state.statement.options(*criteria_options)


def get_db() -> Generator[Session, None, None]:
    """
    Yield a synchronous SQLAlchemy session for request-scoped DB access.

    Contecflow uses synchronous SQLAlchemy ORM as its default persistence layer.
    Any endpoint that needs database access must be declared as a regular
    synchronous function (`def`) so that database work runs safely in FastAPI's
    threadpool. Async endpoints are allowed only for non-blocking I/O / event
    streaming; they must not call `get_db()` directly.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from contextlib import contextmanager


@contextmanager
def worker_db_session() -> Generator[Session, None, None]:
    """Context manager para Celery workers / scripts CLI.

    Garantiza el `db.close()` incluso si la task lanza una excepción no
    capturada (a diferencia de `db = SessionLocal()` + try/finally manual).
    Resuelve audit #29 ("SessionLocal sin context manager en worker.py").

    Uso::

        with worker_db_session() as db:
            do_work(db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def is_postgres() -> bool:
    return not _is_sqlite


def get_db_type() -> str:
    return "postgresql" if not _is_sqlite else "sqlite"


# ── Auditoria 2026-08: sellar la organizacion al insertar ─────────────────────
#
# El filtro de tenant es `organization_id == org`, asi que una fila guardada con
# NULL **no la ve su propia organizacion**: solo un superadmin. Y al barrer el
# codigo por AST resulto que **195 de los 376 modelos con esa columna no se
# construyen NUNCA con ella**, en 611 sitios. No es un descuido aislado: es que
# nadie la sella.
#
# Comprobado de punta a punta con dos casos:
#
#   - `performance_service.create_cycle()` -> ciclo con organization_id NULL,
#     y `GET /performance/cycles` devolvia CERO a su propio creador.
#   - `activity_service.notify()` -> notificacion con NULL, y
#     `GET /enterprise/notifications` devolvia CERO al usuario.
#
# En los dos casos sin un solo error en los logs: solo listas vacias, que es
# exactamente lo que no se investiga.
#
# Arreglar 611 construcciones una a una seria perseguir el sintoma. La causa es
# que la organizacion del sujeto de la peticion no llega a la fila, y el sitio
# donde eso se arregla de una vez es el flush.
#
# Lo que este escuchador hace y lo que NO hace:
#
#   · Sella solo objetos NUEVOS cuya `organization_id` sea None. Un valor ya
#     puesto no se toca nunca — un superadmin que crea a proposito en otra
#     organizacion sigue pudiendo.
#   · Solo si la sesion tiene organizacion en `info`, que es lo que pone
#     `get_current_user`. Un job de fondo o un script no la tiene, asi que su
#     comportamiento no cambia: siguen creando NULL como hoy.
#   · NO toca los modelos exentos (`_tenant_exempt`) ni los que declaran
#     `_tenant_filter_include_global`. En estos ultimos —`AppSetting` y los
#     ajustes de proveedor de IA— un NULL significa «valor global del
#     despliegue», y sellarlo lo convertiria en un ajuste de un solo cliente.
#
# Se puede desactivar con `TENANT_AUTO_STAMP_ON_INSERT=0`, igual que el filtro,
# para poder aislar un problema sin tocar codigo.

_TENANT_AUTO_STAMP = _os.getenv("TENANT_AUTO_STAMP_ON_INSERT", "1") == "1"


@_contextmanager
def sin_filtro_de_tenant(session):
    """Dentro de este bloque, la sesion lee sin el filtro de organizacion.

    Auditoria 2026-08. La cabecera de `do_orm_execute` ya declaraba
    `bypass_tenant_filter` como «escape hatch para scripts de migracion y
    trabajos de analitica entre tenants». Falta un caso que no es ninguno de
    esos dos y que **da un 500 en produccion**:

        PATCH /users/{id}  con `organization_id` de otra organizacion
        -> `db.commit()` mueve al usuario
        -> `db.refresh(user)` no lo encuentra: la sesion sigue en la
           organizacion de quien llamo, y la fila ya no esta ahi
        -> InvalidRequestError: Could not refresh instance '<User>'

    El cambio **queda hecho** —el `commit` ya paso— y quien lo pidio recibe un
    error del servidor. Es el peor final posible: la operacion tuvo efecto y la
    respuesta dice que no.

    No se arregla aflojando el filtro ni quitando el `refresh`: se arregla
    diciendo que **esta lectura concreta es legitimamente de otra
    organizacion**, que es justo lo que este bloque declara. Alcance minimo, y
    se devuelve el valor anterior al salir por si alguien ya lo habia puesto.

    No usarlo para «que no me moleste el filtro». Si una consulta necesita esto
    y no es releer una fila que uno mismo acaba de mover, casi seguro que lo que
    falta es acotar mejor, no saltarse el acotado.
    """
    previo = session.info.get("bypass_tenant_filter")
    session.info["bypass_tenant_filter"] = True
    try:
        yield session
    finally:
        if previo is None:
            session.info.pop("bypass_tenant_filter", None)
        else:
            session.info["bypass_tenant_filter"] = previo


def publicar_contexto_de_tenant(session, sujeto, *, es_cliente=False) -> None:
    """Pone en `session.info` la organizacion del sujeto de esta peticion.

    Las tres capas de aislamiento de `TenantSession` —`query()`, `execute()` y
    el escuchador `do_orm_execute`— salen por la puerta de atras cuando `info`
    no trae `is_superadmin`. Esa rama existe para los trabajos de fondo y los
    tests («sesion no inicializada»), **no** para una peticion autenticada.

    Auditoria 2026-08 (hallazgo 22). El mismo defecto aparecio tres veces, y
    siempre en el mismo sitio: una sesion creada a mano con `SessionLocal()`
    que nadie inicializaba.

      · el WebSocket del chat de colaboracion;
      · `get_current_client`, de la que cuelgan **41 dependencias** del portal;
      · y las de este arreglo: los dos WebSocket de BI, los dos generadores de
        SSE del chat de IA y los tres WebSocket de notificaciones.

    Tres veces el mismo arreglo escrito a mano es una senal: existe este
    ayudante para que sea **una linea** y para que un test pueda buscarla.

    **Se llama DESPUES de resolver al sujeto**, y eso no es un detalle: la
    consulta que lo busca por id todavia no sabe de que organizacion es, asi
    que tiene que correr sin filtrar. Publicar el contexto antes la dejaria sin
    resultados.
    """
    session.info["organization_id"] = getattr(sujeto, "organization_id", None)
    # Un usuario del portal nunca es superadmin de la plataforma, y su modelo no
    # tiene ese atributo: por eso el parametro, en vez de un `getattr` que
    # devolveria `False` por casualidad y no por decision.
    session.info["is_superadmin"] = (
        False if es_cliente
        else bool(getattr(sujeto, "is_superadmin", False))
    )
    session.info["current_client" if es_cliente else "current_user"] = sujeto


def _sellar_organizacion(session) -> None:
    """Pone la organizacion de la sesion en las filas nuevas que no la traigan."""
    info = getattr(session, "info", {}) or {}
    org_id = info.get("organization_id")
    if org_id is None:
        return
    for obj in session.new:
        cls = type(obj)
        if getattr(cls, "_tenant_exempt", False):
            continue
        if getattr(cls, "_tenant_filter_include_global", False):
            continue
        if not hasattr(cls, "organization_id"):
            continue
        try:
            if getattr(obj, "organization_id", None) is None:
                obj.organization_id = org_id
        except Exception:
            # Un modelo con `organization_id` como propiedad de solo lectura no
            # debe romper el flush entero.
            logging.getLogger(__name__).debug(
                "no se pudo sellar la organizacion en %s", cls.__name__,
                exc_info=True)


if _TENANT_AUTO_STAMP:

    @_sa_event.listens_for(SessionLocal, "before_flush")
    def _sellar_organizacion_al_insertar(session, flush_context, instances) -> None:
        _sellar_organizacion(session)
