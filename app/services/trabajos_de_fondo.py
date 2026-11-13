"""Lo que hacen las tareas programadas del worker, organizacion a organizacion.

Segunda auditoria 2026-11.

(#33) 36 de las 45 tareas de Celery abrian `worker_db_session()` sin contexto
de tenant: una sesion «no inicializada» lee TODAS las organizaciones y lo que
crea queda con `organization_id` NULL (que ninguna organizacion ve). Medido en
`compliance_check`: un unico informe con las metricas de todas las empresas,
guardado sin empresa. Y la IA llamada desde ahi (`auto_rca` de
`problem_auto_detect`) no aplicaba el tope de gasto ni el proveedor de nadie.

`en_cada_organizacion` corre un trabajo una vez por organizacion activa, cada
una con su sesion y su contexto publicado (`como_organizacion`): el filtro de
tenant acota las lecturas y el sellado pone la organizacion a lo que se crea.

(#37) Una tarea que fallaba devolvia `{"error": ...}`: Celery la marcaba
SUCCESS, sin reintento ni traza. Aqui un fallo se registra con su traza
(`exc_info`), no impide al resto de organizaciones y al final se relanza
(`FalloEnOrganizaciones`) para que la tarea quede en FAILURE.

Las sesiones se piden a `app.db.session.worker_db_session` en el momento de
usarlas (no se importa el nombre): las pruebas lo sustituyen ahi.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

Trabajo = Callable[[Session, str], Any]


class FalloEnOrganizaciones(RuntimeError):
    """Una o mas organizaciones fallaron; las demas si se procesaron."""

    def __init__(self, tarea: str, fallos: dict, resultados: dict):
        self.tarea, self.fallos, self.resultados = tarea, fallos, resultados
        super().__init__(f"{tarea}: fallo en {len(fallos)} organizacion(es): {fallos}")


class FalloParcial(RuntimeError):
    """Dentro de una organizacion fallaron elementos sueltos (lo demas quedo guardado)."""

    def __init__(self, que: str, errores: list, hecho: Any = None):
        self.errores, self.hecho = errores, hecho
        super().__init__(f"{que}: {len(errores)} error(es): {errores[:5]}")


def organizaciones_activas(db: Session) -> list[str]:
    from app.db.session import sin_filtro_de_tenant
    from app.models.mfa import Organization

    with sin_filtro_de_tenant(db):
        return [o for (o,) in db.query(Organization.id)
                .filter(Organization.is_active.is_(True)).order_by(Organization.id)]


def en_cada_organizacion(tarea: str, trabajo: Trabajo, *,
                         organizaciones: Optional[Iterable[str]] = None) -> dict:
    """Corre `trabajo(db, org_id)` en cada organizacion, con su contexto publicado.

    Confirma tras cada organizacion. Si alguna falla se deshace solo lo suyo, se
    sigue con las demas y al final se lanza `FalloEnOrganizaciones`.
    """
    from app.db import session as _sesion
    from app.services.service_desk.ticket_events import como_organizacion

    if organizaciones is None:
        with _sesion.worker_db_session() as db:
            organizaciones = organizaciones_activas(db)
    organizaciones = list(organizaciones)

    resultados: dict = {}
    fallos: dict = {}
    primera: Optional[BaseException] = None
    for org_id in organizaciones:
        with _sesion.worker_db_session() as db, como_organizacion(db, org_id):
            try:
                resultados[org_id] = trabajo(db, org_id)
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.error("%s: fallo en la organizacion %s", tarea, org_id, exc_info=True)
                fallos[org_id] = f"{type(exc).__name__}: {exc}"[:300]
                primera = primera or exc
    if fallos:
        # `__cause__` lleva la primera excepcion: su tipo y su traza.
        raise FalloEnOrganizaciones(tarea, fallos, resultados) from primera
    logger.info("%s: %d organizacion(es) procesadas", tarea, len(organizaciones))
    return {"organizaciones": len(organizaciones), "por_organizacion": resultados}


# ── Cuerpos que vivian dentro de `app/worker.py` (#37) ───────────────────────


def imputaciones_pendientes_de_hoy(db: Session, org_id: str) -> dict:
    """Empleados de la organizacion que no han imputado su capacidad de hoy.

    «Hoy» es el dia de CADA empleado, no el del servidor (auditoria 2026-08,
    P2-14), y el fin de semana tambien: en el sabado del servidor puede ser
    viernes por la tarde para alguien.
    """
    from sqlalchemy import func

    from app.core import timeutil
    from app.core.config import settings
    from app.core.timeutil import using_zone, zone_for_user
    from app.models.imputation import Imputation
    from app.models.mfa import Organization
    from app.models.user import User, UserRole, UserStatus

    org = db.get(Organization, org_id)
    empleados = db.query(User).filter(
        User.is_active.is_(True), User.status == UserStatus.active, User.role == UserRole.employee,
    ).all()
    faltan = []
    for emp in empleados:
        with using_zone(zone_for_user(emp, org)):
            hoy = timeutil.today()
            if hoy.weekday() >= 5:
                continue
            capacidad = (emp.weekly_capacity_hours or settings.DEFAULT_WEEKLY_CAPACITY_HOURS) / 5
            horas = db.query(func.sum(Imputation.hours)).filter(
                Imputation.user_id == emp.id, Imputation.date == hoy,
            ).scalar() or 0.0
            if horas < capacidad:
                faltan.append(emp.email)
    return {"missing_today": len(faltan), "users": faltan}


def generar_facturas_de_retainer(db: Session, org_id: str) -> dict:
    """Factura mensual en borrador de los proyectos `recurring_retainer` cuyo dia es hoy.

    El dia se resuelve en la zona del CLIENTE (auditoria 2026-08, P2-14). Una
    factura por proyecto y mes. Cada factura se confirma sola: un proyecto que
    falla no deshace las de los demas, y el fallo sale al final (`FalloParcial`).
    """
    import uuid
    from datetime import date

    from app.core import timeutil
    from app.core.config import settings
    from app.core.timeutil import using_zone, zone_for_client
    from app.models.billing_reports import Invoice, InvoiceStatus
    from app.models.clients import Client
    from app.models.mfa import Organization
    from app.models.project import Project
    from app.services.numbering import next_numbered_code

    org = db.get(Organization, org_id)
    proyectos = db.query(Project).filter(
        Project.billing_type == "recurring_retainer",
        Project.retainer_amount.isnot(None),
        Project.retainer_day.isnot(None),
        Project.is_billable.is_(True),
    ).all()
    clientes: dict = {}

    def _cliente(cid):
        if cid and cid not in clientes:
            clientes[cid] = db.query(Client).filter(Client.id == cid).first()
        return clientes.get(cid)

    generadas, errores = [], []
    for proj in proyectos:
        # Solo el dia depende de la zona; el año de la numeracion sigue en UTC
        # a proposito (cambiarlo desplazaria secuencias ya emitidas).
        with using_zone(zone_for_client(_cliente(proj.client_id), org)):
            hoy = timeutil.today()
        if proj.retainer_day != hoy.day:
            continue
        try:
            inicio_de_mes = date(hoy.year, hoy.month, 1)
            if db.query(Invoice).filter(Invoice.project_id == proj.id,
                                        Invoice.period_from >= inicio_de_mes).first():
                continue
            numero = next_numbered_code(db, "invoice", prefix="INV", padding=4, include_year=True,
                                        reset_yearly=True, year_separator="-")
            nombre = getattr(proj, "client_name", None)
            correo = getattr(proj, "client_email", None)
            direccion = getattr(proj, "client_address", None)
            cliente = _cliente(proj.client_id)
            if cliente is not None:
                nombre = nombre or getattr(cliente, "name", None)
                correo = correo or getattr(cliente, "email", None)
                direccion = direccion or getattr(cliente, "address", None)
            db.add(Invoice(
                id=str(uuid.uuid4()), number=numero, project_id=proj.id, client_id=proj.client_id,
                client_name=nombre, client_email=correo, client_address=direccion,
                total=proj.retainer_amount, currency=proj.currency or settings.DEFAULT_CURRENCY,
                issue_date=hoy, period_from=inicio_de_mes, period_to=hoy, status=InvoiceStatus.draft,
                notes=f"Retainer mensual automático — {hoy.strftime('%B %Y')}",
            ))
            db.commit()
            generadas.append(proj.code)
        except Exception as exc:
            db.rollback()
            logger.error("Retainer: no se pudo facturar el proyecto %s", proj.code, exc_info=True)
            errores.append(f"{proj.code}: {exc}"[:200])
    hecho = {"generated": generadas, "count": len(generadas)}
    if errores:
        raise FalloParcial("facturas de retainer", errores, hecho)
    return hecho


def crear_problemas_recurrentes(db: Session, org_id: str) -> dict:
    """Un Problem (con RCA de IA) por cada grupo de incidentes repetidos."""
    from app.services.service_desk.incident_intelligence_service import detect_recurring_incidents
    from app.services.service_desk.problem_service import create_problem_from_correlation

    grupos = detect_recurring_incidents(db)
    creados, errores = 0, []
    for grupo in grupos:
        try:
            problema = create_problem_from_correlation(
                db=db, ticket_ids=grupo["ticket_ids"], category=grupo["category"],
                priority=grupo["priority"], auto_rca=True,
            )
            db.commit()
            creados += 1
            logger.info("Auto-created problem %s for category=%s priority=%s (%d tickets)",
                        problema.number, grupo["category"], grupo["priority"], len(grupo["ticket_ids"]))
        except Exception as exc:
            db.rollback()
            logger.error("No se pudo crear el problema del grupo %s", grupo, exc_info=True)
            errores.append(f"{grupo.get('category')}/{grupo.get('priority')}: {exc}"[:200])
    hecho = {"clusters_found": len(grupos), "problems_created": creados}
    if errores:
        raise FalloParcial("problemas recurrentes", errores, hecho)
    return hecho


def puntuar_cambios_pendientes(db: Session, org_id: str, limite: int = 50) -> dict:
    """Riesgo de los cambios pendientes de CAB sin puntuar; aprueba los estandar de bajo riesgo."""
    from app.models.service_desk import ITSMChangeRequest
    from app.services.service_desk.change_impact_service import ESTADOS_PENDIENTES_DE_CAB, score_and_persist
    from app.services.service_desk.change_service import _maybe_auto_approve

    pendientes = (
        db.query(ITSMChangeRequest)
        .filter(ITSMChangeRequest.status.in_(ESTADOS_PENDIENTES_DE_CAB),
                ITSMChangeRequest.auto_risk_score.is_(None))
        .limit(limite)
        .all()
    )
    puntuados = aprobados = 0
    errores = []
    for cambio in pendientes:
        try:
            score_and_persist(db, cambio.id)
            if _maybe_auto_approve(db, cambio, system_user_id="system-batch-score"):
                aprobados += 1
            db.commit()
            puntuados += 1
        except Exception as exc:
            db.rollback()
            logger.error("change_impact_batch_score: fallo en %s", cambio.id, exc_info=True)
            errores.append(f"{cambio.id}: {exc}"[:200])
    hecho = {"scored": puntuados, "auto_approved": aprobados, "errors": len(errores)}
    if errores:
        raise FalloParcial("puntuacion de cambios", errores, hecho)
    return hecho


def reconocer_ingresos_si_es_dia_1(db: Session, org_id: str) -> dict:
    """ASC 606: reconoce el mes anterior cuando es dia 1 EN LA ZONA de la organizacion.

    La tarea corre a diario a proposito (auditoria 2026-08): con un unico
    disparo a las 02:00 del dia 1, una organizacion en UTC-6 estaba aun en el
    dia 31 y su periodo salia desplazado. El lote es idempotente.
    """
    from app.core.timeutil import resolve_zone, today_in
    from app.models.mfa import Organization
    from app.services.revenue_service import run_monthly_recognition

    org = db.get(Organization, org_id)
    hoy = today_in(resolve_zone(getattr(org, "timezone", None)))
    if hoy.day != 1:
        return {"omitido": "no es dia 1 en su zona"}
    year, month = (hoy.year - 1, 12) if hoy.month == 1 else (hoy.year, hoy.month - 1)
    return run_monthly_recognition(db, year, month, organization_id=org_id)


def instantanea_itsm(db: Session, org_id: str) -> dict:
    """Instantanea horaria de KPIs ITSM de la organizacion (solo si tiene tickets)."""
    from app.models.service_desk import Ticket
    from app.services.service_desk.analytics_service import _snapshot_de_empresa

    if db.query(Ticket.id).filter(Ticket.organization_id == org_id).first() is None:
        return {"omitido": "sin tickets"}
    return _snapshot_de_empresa(db, org_id)


def publicar_kpis_de_bi(db: Session, org_id: str) -> dict:
    """KPIs de BI al canal de Redis de la organizacion (WebSocket sin sondeo)."""
    from app.services.bi_intelligence_service import instantanea_kpi, publish_kpi_snapshot

    publish_kpi_snapshot(org_id, instantanea_kpi(db, org_id))
    return {"publicado": True}


def calentar_modelos_de_bi(db: Session, org_id: str) -> dict:
    """Ejercita el entrenamiento de IsolationForest con la serie de la organizacion."""
    from app.services.bi_intelligence_service import ml_detect_anomalies_multivariate

    ml_detect_anomalies_multivariate(db, organization_id=org_id, contamination=0.1)
    return {"calentado": True}
