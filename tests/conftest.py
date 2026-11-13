import os
import secrets
from contextlib import contextmanager
# Forzar modo 'plain' para claves JWT en tests (no KMS)
os.environ["KMS_PROVIDER"] = ""
os.environ["AWS_KMS_KEY_ID"] = ""

"""
conftest.py — Fixtures compartidos para toda la suite de tests de Contecflow.
Usa SQLite en memoria para aislamiento total.
"""
import pytest
from fastapi.testclient import TestClient

# Disable rate limiting for the entire test suite
os.environ["TESTING"] = "1"
# El valor por defecto de ENVIRONMENT es production (cierra por defecto); la
# suite se escribio contra development.
os.environ.setdefault("ENVIRONMENT", "development")
from sqlalchemy import create_engine
from sqlalchemy import event as _sa_event
from sqlalchemy import inspect as _sa_inspect
from sqlalchemy import text as _sa_text
from sqlalchemy.orm import sessionmaker

# Variables de entorno necesarias para pydantic-settings en tests.
#
# Auditoría 2026-09: este bloque estaba **después** de
# `from app.db.session import TenantSession`, que arrastra `app.core.config` y
# por tanto construye `settings` con los valores que hubiera **antes** de que
# estas líneas se ejecutaran. Consecuencia real:
# `test_scim_user_provisioning` fallaba —`settings.SCIM_BEARER_TOKEN` vacío—
# salvo que algo anterior en la suite hubiera dejado el valor puesto, así que
# pasaba o no según el orden de los tests. Un test que depende del orden no
# prueba lo que dice probar.
#
# Va aquí, antes del primer import de `app`, y es el sitio: `pydantic-settings`
# lee el entorno una sola vez, al construir el objeto.
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-not-production-use")
os.environ.setdefault("CLIENT_PORTAL_SECRET", "test-client-portal-secret-unit-tests-only")
os.environ.setdefault("SCIM_BEARER_TOKEN", "test-scim-token-unit-tests-only")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret-for-unit-tests")
os.environ.setdefault("JIRA_WEBHOOK_SECRET", "test-jira-webhook-secret-unit-tests")
os.environ.setdefault("INBOUND_EMAIL_SECRET", "test-inbound-email-secret-for-unit-tests")
os.environ.setdefault("ANTHROPIC_API_URL", "https://api.anthropic.test")
os.environ.setdefault("OPENAI_API_URL", "https://api.openai.test")
os.environ.setdefault("GEMINI_API_URL", "https://api.gemini.test")
os.environ.setdefault("DEEPSEEK_API_URL", "https://api.deepseek.test")
os.environ.setdefault("GROQ_API_URL", "https://api.groq.test")
os.environ.setdefault("MISTRAL_API_URL", "https://api.mistral.test")
os.environ.setdefault("MISTRAL_DOCS_URL", "https://docs.mistral.ai")
os.environ.setdefault("XERO_API_BASE", "https://api.xero.test")
os.environ.setdefault("ANTHROPIC_DOCS_URL", "https://www.anthropic.com/docs")
os.environ.setdefault("OPENAI_DOCS_URL", "https://platform.openai.com/docs")
os.environ.setdefault("GEMINI_DOCS_URL", "https://developers.google.com/ai")
os.environ.setdefault("QB_API_BASE", "https://api.quickbooks.test")
os.environ.setdefault("BASE_URL", "http://localhost:8000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("BACKEND_URL", "http://localhost:8000")
os.environ.setdefault("OLLAMA_BASE_URL", "https://api.ollama.test")
os.environ.setdefault("OLLAMA_DOCS_URL", "https://ollama.com/docs")
os.environ.setdefault("PDF_STORAGE_PATH", "/tmp")
os.environ.setdefault("SUPERADMIN_EMAIL", "admin@contecflow.com")
# Generate a strong random test password once per session — not committed to source.
_TEST_PASSWORD = secrets.token_urlsafe(20)
os.environ.setdefault("SUPERADMIN_PASSWORD", _TEST_PASSWORD)
os.environ.setdefault("DEFAULT_USER_PASSWORD", _TEST_PASSWORD)
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.db.session import TenantSession

# Los dos escuchadores de aislamiento. Estan detras de sus perillas
# (`TENANT_AUTO_FILTER_GLOBAL` y `TENANT_AUTO_STAMP_ON_INSERT`), asi que pueden
# no existir: si estan apagados en el entorno, la suite corre sin ellos, igual
# que produccion.
try:
    from app.db.session import _enforce_tenant_isolation
except ImportError:  # pragma: no cover — la perilla esta apagada
    _enforce_tenant_isolation = None
try:
    from app.db.session import _sellar_organizacion
except ImportError:  # pragma: no cover
    _sellar_organizacion = None


from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.core.security import get_password_hash
from app.models.user import User, UserRole, UserStatus
from app.models.mfa import Organization

# ── BD en memoria para tests ───────────────────────────────────────────────────
TEST_DB_URL = "sqlite://"  # In-memory — totalmente aislado entre tests
engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    # Para SQLite in-memory: mantener una sola conexión durante todo el test
    poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
)
# ── La semantica de tenant, la misma que en produccion ──────────────────────
#
# Auditoria 2026-08. Durante toda la auditoria esta factoria fue un
# `sessionmaker` plano, y los tres mecanismos de aislamiento se registran sobre
# `SessionLocal`, asi que **ninguno se disparaba en ningun test**. Eso es lo que
# dejo vivir dos defectos graves sin que nadie los viera:
#
#   · el «apagon» del filtro (§3.bis): el criterio con la organizacion cocida en
#     un argumento por defecto dejaba a cero a toda organizacion que no fuera la
#     primera atendida por el proceso;
#   · y el `TypeError` de la rama «usuario sin organizacion», que reventaba
#     cualquier consulta ORM de esa sesion con un 500.
#
# Los dos se verificaron enganchando el escuchador **a mano** en un test. Eso
# funciona para un caso concreto y no protege del siguiente.
#
# Registrarlo aqui es seguro por construccion, y conviene entender por que: las
# tres capas —`query()`, `execute()` y el escuchador `do_orm_execute`— salen por
# la puerta de atras cuando `info` no trae `is_superadmin` («sesion no
# inicializada»). Un test que no autentica no cambia de comportamiento. **Lo que
# si cambia** es el test que pasa por `get_current_user`, que si publica el
# contexto: ese corre ahora con el filtro puesto, que es exactamente lo que hace
# produccion.
TestSession = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=TenantSession,
)

if _enforce_tenant_isolation is not None:
    _sa_event.listen(TestSession, "do_orm_execute", _enforce_tenant_isolation)

if _sellar_organizacion is not None:

    @_sa_event.listens_for(TestSession, "before_flush")
    def _sellar_en_los_tests(session, flush_context, instances) -> None:
        """El mismo sellado de organizacion que corre en produccion.

        Sin esto, un test que crea una fila con la sesion autenticada la deja
        con `organization_id` a NULL y despues no la ve — que es precisamente el
        defecto de §3.quater, y hay que poder reproducirlo en la suite.
        """
        _sellar_organizacion(session)


@contextmanager
def fila_global(sesion):
    """Dentro de este bloque, las filas nuevas NO reciben organización.

    Auditoría 2026-08. Desde que la suite corre con la semántica de producción,
    la sesión del fixture `db` publica organización y `_sellar_organizacion`
    rellena el `organization_id` de toda fila nueva que venga con `None`. Eso es
    lo correcto para el 99 % de los tests —crean datos de su propio tenant— y es
    exactamente lo contrario de lo que quiere el 1 % restante: los que
    comprueban qué pasa con una fila **global**, esa que tiene la columna a NULL
    a propósito y que todas las organizaciones ven.

    Pasar el valor «None» no sirve, porque el sellado rellena precisamente los
    None. Hay que quitarle el contexto a la sesión mientras se crea la fila, y
    eso es lo que hace esto:

        with fila_global(db):
            db.add(WorkflowBlueprint(name="BP", organization_id=None))
            db.commit()

    Al salir devuelve el contexto, así que el resto del test sigue viendo lo que
    veía. Y se lee como lo que es —una declaración de intención— en vez de como
    un apaño: si mañana el sellado cambia, estos son los sitios que hay que
    mirar, y están marcados.

    Ojo: los modelos con `_tenant_filter_include_global` (como `AppSetting`) ya
    los salta el sellado, así que esos no lo necesitan.
    """
    previo = sesion.info.pop("organization_id", None)
    # Auditoria 2026-11: sin organizacion en la sesion el sellado la deriva del
    # proyecto o del usuario de la fila; esta marca lo impide aqui.
    sesion.info["fila_global"] = True
    try:
        yield sesion
    finally:
        sesion.info.pop("fila_global", None)
        if previo is not None:
            sesion.info["organization_id"] = previo


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db



#: El hash de `_TEST_PASSWORD`, calculado UNA vez para toda la sesión.
#:
#: Auditoría 2026-09: la fixture `db` —que es `autouse` y de ámbito de función—
#: llamaba a `get_password_hash` **cuatro veces por test**. Con bcrypt a 12
#: rondas eso son 0,297 s por hash: **1,19 s de cada test** dedicados a cifrar
#: cuatro veces la misma contraseña. Sobre 3818 tests son **75 minutos** de
#: reloj de CPU, más que todo lo demás junto.
#:
#: Calcularlo una vez es equivalente: los cuatro sitios cifraban la MISMA
#: cadena. Que los cuatro usuarios de prueba compartan el hash no cambia nada
#: —sigue siendo un bcrypt válido de esa contraseña— y ningún test depende de
#: que sean distintos.
#:
#: Lo que NO se hace es bajar las rondas de bcrypt en tests: eso cambiaría el
#: comportamiento de lo que se está probando.
HASH_DE_PRUEBA = get_password_hash(_TEST_PASSWORD)


#: Se crea el esquema una sola vez y entre tests se vacían las filas.
#:
#: La fixture hacía `create_all` + `drop_all` en **cada test**, y este proyecto
#: tiene **392 tablas**: 0,735 s en crear y 0,101 s en destruir, otros 53
#: minutos sobre la suite entera. Vaciar las mismas 392 tablas cuesta 0,042 s
#: —veinte veces menos— y deja la base igual de limpia para el test siguiente.
#:
#: Se vacía al PRINCIPIO y no al final: si un test se interrumpe a medias, el
#: siguiente sigue empezando con la base limpia.
_esquema_creado = False


def _preparar_base_limpia() -> None:
    """Esquema listo y sin datos, al coste más bajo posible."""
    global _esquema_creado
    from app import models as _models  # noqa: F401 — registra los modelos en Base.metadata

    if not _esquema_creado:
        Base.metadata.create_all(bind=engine)
        _esquema_creado = True
        return

    # Hay tests que BORRAN una tabla a propósito —`DROP TABLE IF EXISTS
    # dashboard_comments`, para ejercitar el respaldo a JSON de
    # `bi_collaboration_service`—. Con `create_all` por test eso se recreaba
    # solo; vaciando, no. Comprobar qué existe cuesta 1,1 ms y recrear sólo lo
    # que falta cuesta cero el 99,9 % de las veces.
    #
    # Sin esta comprobación, los 679 tests que van detrás de uno de esos dos
    # revientan en el `setup` con «no such table». Lo cazó la suite completa.
    existentes = set(_sa_inspect(engine).get_table_names())
    faltan = [t for t in Base.metadata.sorted_tables if t.name not in existentes]
    if faltan:
        Base.metadata.create_all(bind=engine, tables=faltan, checkfirst=True)

    with engine.begin() as conexion:
        # Sin esto el borrado tendría que respetar el orden de dependencias
        # entre 392 tablas; apagarlas un instante es más simple y más rápido.
        conexion.execute(_sa_text("PRAGMA foreign_keys=OFF"))
        for tabla in reversed(Base.metadata.sorted_tables):
            conexion.execute(tabla.delete())
        conexion.execute(_sa_text("PRAGMA foreign_keys=ON"))


# ── Fixtures ───────────────────────────────────────────────────────────────────
@pytest.fixture(scope="function", autouse=True)

def db():
    """Deja la base vacía y con los datos base antes de cada test."""
    _preparar_base_limpia()
    # Revisión 2026-11: la caché de ajustes en vivo sobrevivía a la base: un
    # ajuste puesto por una prueba (p. ej. el tope de gasto) lo heredaba la
    # siguiente del mismo proceso, y fallaba según el orden de xdist.
    from app.services.settings_service import invalidate_cache
    invalidate_cache()
    session = TestSession()

    # Admin
    admin_hashed = HASH_DE_PRUEBA
    admin = User(
        id="admin-test-id",
        username="admin",
        email="admin@contecflow.com",
        full_name="Admin Test",
        role=UserRole.admin,
        status=UserStatus.active,
        is_active=True,
        hashed_password=admin_hashed,
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    # PM
    pm = User(
        id="pm-test-id",
        username="pm_test",
        email="pm@contecflow.com",
        full_name="PM Test",
        role=UserRole.pm,
        status=UserStatus.active,
        is_active=True,
        hashed_password=HASH_DE_PRUEBA,
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    # Employee (anteriormente developer)
    dev = User(
        id="dev-test-id",
        username="dev_test",
        email="dev@contecflow.com",
        full_name="Dev Test",
        role=UserRole.employee,
        status=UserStatus.active,
        is_active=True,
        hourly_rate=50.0,
        hashed_password=HASH_DE_PRUEBA,
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    # HR user
    hr = User(
        id="hr-test-id",
        username="hr_test",
        email="hr@contecflow.com",
        full_name="HR Test",
        role=UserRole.hr,
        status=UserStatus.active,
        is_active=True,
        hashed_password=HASH_DE_PRUEBA,
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    # Subcontratado: el unico rol que `require_internal_user` deja fuera.
    #
    # Hace falta para poder PROBAR esa guarda. Sin un usuario de este rol, el
    # unico token con el que se podia sondear `require_internal_user` era el de
    # un empleado, que la guarda deja pasar — y un test que no puede ver el 403
    # no prueba nada. Ver `test_las_guardas_deniegan_de_verdad`.
    sub = User(
        id="sub-test-id",
        username="sub_test",
        email="sub@contecflow.com",
        full_name="Subcontratado Test",
        role=UserRole.subcontractor,
        status=UserStatus.active,
        is_active=True,
        hashed_password=HASH_DE_PRUEBA,
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    org = Organization(
        id=1,
        name="Test Organization",
        slug="test-org",
        is_active=True,
    )
    session.add(org)
    # Associate admin user with org
    admin.organization_id = 1
    pm.organization_id = 1
    dev.organization_id = 1
    hr.organization_id = 1
    sub.organization_id = 1
    session.add_all([admin, pm, dev, hr, sub])
    session.commit()
    session.close()

    # --- Inicializar el cache global de claves JWT para la app ---
    from app.services.key_management import refresh_caches
    db_session = TestSession()

    # ── El contexto de tenant de la sesion del fixture ───────────────────────
    #
    # Auditoria 2026-08. Desde que `TestSession` registra los escuchadores de
    # produccion, esta sesion necesita contexto — y no por capricho, por una
    # razon medible: `_sellar_organizacion` sale por la puerta de atras cuando
    # `info` no trae `organization_id`, asi que **toda fila creada por un test
    # con `db.add(...)` se quedaba con `organization_id` a NULL**, y despues la
    # peticion HTTP —que si tiene contexto— la buscaba con el filtro puesto y no
    # la encontraba. Sintoma real:
    # `test_imputation_rejects_closed_task_status` esperaba el 400 de «tarea
    # cerrada» y recibia un 404, porque su `Task` era invisible.
    #
    # `is_superadmin=True` es deliberado y es la otra mitad del arreglo: esta
    # sesion es la del *operador del test*, que inspecciona y prepara datos de
    # cualquier organizacion. Con superadmin el filtro de lectura se salta y el
    # sellado de escritura no —`_sellar_organizacion` solo mira
    # `organization_id`—, que es exactamente el reparto que hace falta:
    #
    #   · escribir  → las filas caen en la organizacion de los usuarios de test,
    #                 asi que la API las ve;
    #   · leer      → sin filtrar, para poder comprobar lo que la API deberia
    #                 haber escondido.
    #
    # Y quien quiera comprobar el aislamiento **de verdad** no usa esta sesion:
    # lo hace por HTTP con dos tokens, o se monta su propia sesion (ver
    # `tests/test_sesiones_a_mano_con_contexto.py`). Un valor explicito aqui no
    # afloja nada, porque las filas que ya traen `organization_id` puesto —las
    # de `org_b` en las pruebas de dos tenants— no se tocan: el sellado solo
    # rellena los NULL.
    #
    # El orden respecto a `refresh_caches` da igual, y merece quedar dicho
    # porque parece que no: esa llamada escribe el llavero JWT en
    # `app_settings`, una fila que tiene que ser **global** (`organization_id`
    # NULL) o los tests de la segunda organizacion no podrian ni autenticarse.
    # No se sella porque `AppSetting` lleva `_tenant_filter_include_global` y el
    # sellado salta esos modelos — igual que en produccion.
    db_session.info["organization_id"] = 1
    db_session.info["is_superadmin"] = True

    refresh_caches(db_session)
    yield db_session
    db_session.close()
    # Ya no se destruye el esquema: lo vacía `_preparar_base_limpia` al empezar
    # el siguiente test, que es veinte veces más barato.


@pytest.fixture(scope="session", autouse=True)
def _sin_proveedor_de_ia_del_entorno():
    """La suite no hereda el proveedor de IA del `.env` de quien la ejecuta.

    Con `AI_PROVIDER=gemini` en el `.env` local, las pruebas que esperan «sin
    proveedor» fallaban solo en esa maquina. Las que prueban el proveedor del
    entorno lo ponen ellas con `monkeypatch`.
    """
    from app.core.config import settings as _s
    antes = {k: getattr(_s, k) for k in ("AI_PROVIDER", "AI_API_KEY", "AI_MODEL", "AI_BASE_URL", "ANTHROPIC_API_KEY")}
    for k in antes:
        setattr(_s, k, "")
    try:
        yield
    finally:
        for k, v in antes.items():
            setattr(_s, k, v)


@pytest.fixture(scope="session", autouse=True)
def _force_tfidf_embeddings():
    """Keep the semantic engine on the pure-Python TF-IDF encoder for the whole
    test suite.

    The production `SemConfig.local_model_name` column defaults to
    "all-MiniLM-L6-v2", and `SemanticAssigner._resolve_embeddings_runtime`
    prioritises that value over the `SEMANTIC_EMBEDDINGS_BACKEND=tfidf` env
    flag. So any test that constructs a `SemanticAssigner` (directly or via an
    endpoint) would trigger a real `SentenceTransformer(...)` download from
    huggingface — which fails offline / behind the corporate SSL proxy and
    surfaces as a misleading "Cannot send a request, as the client has been
    closed." RuntimeError from huggingface_hub's shared httpx client.

    Pinning `_get_model` to the TF-IDF encoder makes the engine fully offline
    and deterministic in tests without touching production resolution logic.
    """
    import app.services.semantic_classifier as sc

    def _tfidf_only(model_name="all-MiniLM-L6-v2", backend_override=None):
        return _ENCODER_DEL_TEST[0], False

    original = sc._get_model
    sc._get_model_real = original  # para probar la carga de verdad
    sc._get_model = _tfidf_only
    try:
        yield
    finally:
        sc._get_model = original


#: El encoder TF-IDF del test en curso. Segunda auditoría 2026-11 (#27a): era
#: uno por sesión, y el vocabulario que fijaba un test (`fit_global` / el
#: primer `encode`) lo heredaba el siguiente del mismo proceso: un texto con
#: palabras fuera de ese vocabulario daba un vector nulo y el test fallaba
#: según el orden de xdist.
_ENCODER_DEL_TEST: list = [None]


@pytest.fixture(autouse=True)
def _estado_de_modulo_limpio():
    """Estado de módulo que sobrevivía entre tests (#27a): encoder TF-IDF,
    caché de la política de bloqueo de login y su respaldo en memoria."""
    import sys
    import app.services.semantic_classifier as sc
    _ENCODER_DEL_TEST[0] = sc.TFIDFEncoder()
    ee = sys.modules.get("app.services.auth_service.estado_efimero")
    if ee is not None:
        ee._POLITICA_CACHE.clear()
        ee._POLITICA_CACHE.update(hasta=0.0, valor=None)
        with ee._sso_states_lock:
            ee._login_fail_fallback.clear()
    yield


@pytest.fixture(scope="function")
def client():
    return TestClient(app)


@pytest.fixture(scope="function")
def admin_token(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "admin", "password": _TEST_PASSWORD})
    assert res.status_code == 200, f"Login admin falló: {res.text}"
    token = res.cookies.get("access_token")
    assert token
    return token


@pytest.fixture(scope="function")
def superadmin_token(client, db):
    """Token de un superadministrador DE PLATAFORMA (is_superadmin=True).

    Distinto de `admin_token`: ese es un administrador *de tenant*
    (UserRole.admin), que no tiene ni debe tener alcance entre organizaciones.
    Los endpoints de `/organizations` operan sobre el único modelo que
    TenantSession no puede filtrar, así que exigen este actor.

    Se crea un usuario aparte en lugar de poner is_superadmin=True al `admin`
    del fixture: ese flag desactiva TODOS los filtros de tenant, y aplicarlo al
    admin genérico enmascararía fallos de aislamiento en el resto de la suite.
    """
    from app.models.user import User, UserRole, UserStatus

    existing = db.query(User).filter(User.username == "superadmin_test").first()
    if not existing:
        db.add(User(
            id="superadmin-test-id",
            username="superadmin_test",
            email="superadmin@contecflow.com",
            full_name="Superadmin Test",
            role=UserRole.admin,
            status=UserStatus.active,
            is_active=True,
            is_superadmin=True,
            # users.organization_id es NOT NULL. Pertenecer a la org de test no
            # limita nada: is_superadmin=True desactiva los filtros de tenant.
            organization_id="1",
            hashed_password=HASH_DE_PRUEBA,
            weekly_capacity_hours=40.0,
            currency="EUR",
        ))
        db.commit()

    res = client.post(
        "/api/v1/auth/login",
        json={"username": "superadmin_test", "password": _TEST_PASSWORD},
    )
    assert res.status_code == 200, f"Login superadmin falló: {res.text}"
    token = res.cookies.get("access_token")
    assert token
    return token


@pytest.fixture(scope="function")
def pm_token(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "pm_test", "password": _TEST_PASSWORD})
    assert res.status_code == 200
    token = res.cookies.get("access_token")
    assert token
    return token


@pytest.fixture(scope="function")
def dev_token(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "dev_test", "password": _TEST_PASSWORD})
    assert res.status_code == 200
    token = res.cookies.get("access_token")
    assert token
    return token


@pytest.fixture(scope="function")
def hr_token(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "hr_test", "password": _TEST_PASSWORD})
    assert res.status_code == 200
    token = res.cookies.get("access_token")
    assert token
    return token


@pytest.fixture(scope="function")
def sub_token(client, db):
    """Token de un subcontratado: el único rol que `require_internal_user` rechaza.

    Es la sonda de `test_guardas_deniegan.py`. Con un token de empleado no se
    puede comprobar esa guarda —el empleado pasa— y un test que nunca puede ver
    el 403 no demuestra nada.
    """
    res = client.post("/api/v1/auth/login", json={"username": "sub_test", "password": _TEST_PASSWORD})
    assert res.status_code == 200
    token = res.cookies.get("access_token")
    assert token
    return token


def auth(token):
    return {"Authorization": f"Bearer {token}"}

# Export the test password so individual test modules can use it for direct login calls
TEST_PASSWORD = _TEST_PASSWORD

@pytest.fixture(scope="function")
def seed_multitenant(db):
    """
    Inicializa datos multi-tenant limpios para pruebas de aislamiento:
    - Crea dos organizaciones (ORG_A, ORG_B)
    - Asocia admin, pm, dev, hr a ORG_A
    - Crea un usuario outsider en ORG_B
    - Crea proyectos y tareas en ambas organizaciones
    """
    from app.models.mfa import Organization
    from app.models.project import Project, ProjectStatus, ProjectType
    from app.models.task import Task, TaskPriority, TaskStatus
    from app.models.user import User, UserRole, UserStatus
    from app.core.security import get_password_hash

    ORG_A_ID = "org-a-test"
    ORG_B_ID = "org-b-test"
    PROJECT_A_ID = "project-a-test"
    PROJECT_B_ID = "project-b-test"
    TASK_A_ID = "task-a-test"
    TASK_B_ID = "task-b-test"
    OUTSIDER_ID = "outsider-test-id"

    # Limpiar tablas relevantes
    db.query(Task).delete()
    db.query(Project).delete()
    db.query(Organization).delete()
    db.query(User).filter(User.id == OUTSIDER_ID).delete()
    db.commit()

    org_a = Organization(id=ORG_A_ID, name="Org A", slug="org-a")
    org_b = Organization(id=ORG_B_ID, name="Org B", slug="org-b")
    db.add_all([org_a, org_b])
    db.flush()

    admin = db.query(User).filter(User.id == "admin-test-id").first()
    pm = db.query(User).filter(User.id == "pm-test-id").first()
    dev = db.query(User).filter(User.id == "dev-test-id").first()
    hr = db.query(User).filter(User.id == "hr-test-id").first()
    for user in (admin, pm, dev, hr):
        user.organization_id = ORG_A_ID

    outsider = User(
        id=OUTSIDER_ID,
        username="outsider",
        email="outsider@example.com",
        full_name="Outsider User",
        role=UserRole.employee,
        status=UserStatus.active,
        is_active=True,
        organization_id=ORG_B_ID,
        hourly_rate=999.0,
        hashed_password=get_password_hash(TEST_PASSWORD),
    )
    db.add(outsider)
    db.flush()

    project_a = Project(
        id=PROJECT_A_ID,
        organization_id=ORG_A_ID,
        code="PRJ-TA",
        name="Tenant Project A",
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        pm_id=pm.id,
        created_by=admin.id,
    )
    project_b = Project(
        id=PROJECT_B_ID,
        organization_id=ORG_B_ID,
        code="PRJ-TB",
        name="Tenant Project B",
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        created_by=OUTSIDER_ID,
    )
    db.add_all([project_a, project_b])
    db.flush()

    # Auditoria 2026-08: las dos tareas llevan `organization_id` **explicito**,
    # como ya lo llevaban sus proyectos. Antes no lo llevaban y funcionaba de
    # casualidad, porque nada sellaba ni filtraba en la suite; desde que corre
    # con la semantica de produccion, una tarea sin organizacion recibe la de la
    # sesion del fixture —que no es ni ORG_A ni ORG_B— y las pruebas de
    # aislamiento dejan de probar lo que dicen: no es que la tarea ajena se
    # esconda, es que **ninguna de las dos aparece**.
    task_a = Task(
        id=TASK_A_ID,
        organization_id=ORG_A_ID,
        code="TSK-TA001",
        project_id=PROJECT_A_ID,
        title="Task tenant A",
        assignee_id=dev.id,
        reporter_id=admin.id,
        created_by=admin.id,
        status=TaskStatus.todo,
        priority=TaskPriority.medium,
    )
    task_b = Task(
        id=TASK_B_ID,
        organization_id=ORG_B_ID,
        code="TSK-TB001",
        project_id=PROJECT_B_ID,
        title="Task tenant B",
        assignee_id=OUTSIDER_ID,
        reporter_id=OUTSIDER_ID,
        created_by=OUTSIDER_ID,
        status=TaskStatus.todo,
        priority=TaskPriority.high,
    )
    db.add_all([task_a, task_b])
    db.commit()
    yield
