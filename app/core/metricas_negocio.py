"""Métricas de negocio por empresa, leídas de la base con caché (22-11-2026).

Un colector de Prometheus (`ColectorDeNegocio`) que en cada scrape devuelve
GAUGES calculados con unas pocas consultas agregadas (`COUNT`/`SUM ... GROUP BY
organization_id`) sobre columnas indexadas. El resultado se guarda
`METRICS_BUSINESS_CACHE_SECONDS` (60 s por defecto) por proceso: con un scrape
cada 15 s, la base recibe una tanda de consultas por minuto y worker de la API,
no una por scrape.

Cada bloque va en su propio `try`: una tabla que no exista en esta base (SQLite
de desarrollo a medio migrar) deja ese bloque sin datos y suma
`contecflow_negocio_colector_errores_total{bloque}`, pero no tumba el resto ni
el `/metrics`.

Las etiquetas son solo de catálogo: `empresa` (acotada, ver
`app/core/metricas_empresa.py`), estados, prioridades, severidades, módulos y
fases. Nada de ids de usuario, nombres, correos ni texto libre.

La sesión es de fondo (sin empresa en `info`), así que ni el filtro del ORM ni
la RLS de Postgres restringen: es una lectura legítima entre empresas, de solo
lectura, y lo que sale de ella son recuentos agregados.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from app.core.metricas_empresa import OTRAS, SIN_EMPRESA, mapa_de_empresas

logger = logging.getLogger("contecflow.metrics")

#: Tope de valores distintos de etiquetas abiertas (fase de demanda, módulo de IA).
_TOPE_VALORES = 25
_VALOR = re.compile(r"[^a-z0-9_.-]+")


def _v(valor) -> str:
    """Valor de etiqueta de catálogo: Enum → su valor; texto → [a-z0-9_.-]."""
    valor = getattr(valor, "value", valor)
    return (_VALOR.sub("_", str(valor if valor is not None else "desconocido").lower())[:40]) or "desconocido"


class _Familia:
    """Acumula muestras {etiquetas: valor} y suma las que caen en la misma etiqueta
    (p. ej. todas las empresas que se agregan en `otras`)."""

    def __init__(self, nombre: str, ayuda: str, etiquetas: tuple):
        self.nombre, self.ayuda, self.etiquetas = nombre, ayuda, etiquetas
        self.valores: dict = defaultdict(float)

    def sumar(self, valores: Iterable[str], cantidad) -> None:
        self.valores[tuple(valores)] += float(cantidad or 0)

    def metrica(self) -> GaugeMetricFamily:
        g = GaugeMetricFamily(self.nombre, self.ayuda, labels=list(self.etiquetas))
        for clave, valor in sorted(self.valores.items()):
            g.add_metric(list(clave), valor)
        return g


class _Contexto:
    def __init__(self, db, mapa: dict):
        self.db = db
        self.mapa = mapa
        self.ahora = datetime.now(timezone.utc)
        self.ahora_naive = self.ahora.replace(tzinfo=None)
        self.hoy = self.ahora.date()

    def empresa(self, org_id) -> str:
        if not org_id:
            return SIN_EMPRESA
        return self.mapa.get(str(org_id), OTRAS)


# ── Bloques ──────────────────────────────────────────────────────────────────
# Cada uno recibe el contexto y devuelve sus familias. Orden = orden en /metrics.

def _tickets(c: _Contexto):
    from sqlalchemy import func, or_
    from app.models.service_desk._enums import SLAStatus, TicketStatus
    from app.models.service_desk.tickets import Ticket

    cerrados = (TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled)
    abiertos = _Familia("contecflow_negocio_tickets_abiertos",
                        "Tickets abiertos (no resueltos/cerrados/cancelados) por empresa y prioridad.",
                        ("empresa", "prioridad"))
    for org, prio, n in (c.db.query(Ticket.organization_id, Ticket.priority, func.count(Ticket.id))
                         .filter(Ticket.status.notin_(cerrados))
                         .group_by(Ticket.organization_id, Ticket.priority)):
        abiertos.sumar((c.empresa(org), _v(prio)), n)

    desde = c.ahora - timedelta(hours=24)
    creados = _Familia("contecflow_negocio_tickets_creados_24h",
                       "Tickets creados en las últimas 24 h por empresa y tipo.", ("empresa", "tipo"))
    for org, tipo, n in (c.db.query(Ticket.organization_id, Ticket.ticket_type, func.count(Ticket.id))
                         .filter(Ticket.created_at >= desde)
                         .group_by(Ticket.organization_id, Ticket.ticket_type)):
        creados.sumar((c.empresa(org), _v(tipo)), n)

    resueltos = _Familia("contecflow_negocio_tickets_resueltos_24h",
                         "Tickets resueltos en las últimas 24 h por empresa.", ("empresa",))
    for org, n in (c.db.query(Ticket.organization_id, func.count(Ticket.id))
                   .filter(Ticket.resolved_at >= desde).group_by(Ticket.organization_id)):
        resueltos.sumar((c.empresa(org),), n)

    sla = _Familia("contecflow_negocio_sla",
                   "Elementos abiertos con el SLA en riesgo o incumplido, por empresa y ámbito.",
                   ("empresa", "ambito", "estado"))
    for org, n in (c.db.query(Ticket.organization_id, func.count(Ticket.id))
                   .filter(Ticket.status.notin_(cerrados),
                           or_(Ticket.sla_resolution_status == SLAStatus.breached,
                               Ticket.sla_response_status == SLAStatus.breached,
                               Ticket.sla_resolution_breached.is_(True)))
                   .group_by(Ticket.organization_id)):
        sla.sumar((c.empresa(org), "tickets", "incumplido"), n)
    for org, n in (c.db.query(Ticket.organization_id, func.count(Ticket.id))
                   .filter(Ticket.status.notin_(cerrados),
                           or_(Ticket.sla_resolution_status == SLAStatus.at_risk,
                               Ticket.sla_response_status == SLAStatus.at_risk),
                           Ticket.sla_resolution_status != SLAStatus.breached)
                   .group_by(Ticket.organization_id)):
        sla.sumar((c.empresa(org), "tickets", "en_riesgo"), n)
    c.sla = sla  # demanda y vulnerabilidades suman en la misma familia
    return [abiertos, creados, resueltos]


def _proyectos(c: _Contexto):
    from sqlalchemy import func
    from app.models.project import Project

    f = _Familia("contecflow_negocio_proyectos", "Proyectos vigentes por empresa y estado.", ("empresa", "estado"))
    for org, estado, n in (c.db.query(Project.organization_id, Project.status, func.count(Project.id))
                           .filter(Project.is_active.is_(True))
                           .group_by(Project.organization_id, Project.status)):
        f.sumar((c.empresa(org), _v(estado)), n)
    return [f]


def _horas(c: _Contexto):
    from sqlalchemy import func
    from app.models.imputation import Imputation

    f = _Familia("contecflow_negocio_horas_imputadas_7d",
                 "Horas imputadas con fecha en los últimos 7 días, por empresa.", ("empresa",))
    for org, h in (c.db.query(Imputation.organization_id, func.sum(Imputation.hours))
                   .filter(Imputation.date >= c.hoy - timedelta(days=7))
                   .group_by(Imputation.organization_id)):
        f.sumar((c.empresa(org),), h)
    return [f]


def _horas_extra(c: _Contexto):
    from sqlalchemy import func
    from app.models.horas_extra import PeticionDeHorasExtra

    f = _Familia("contecflow_negocio_horas_extra_30d",
                 "Horas extra con fecha en los últimos 30 días, por empresa y estado.", ("empresa", "estado"))
    for org, estado, h in (c.db.query(PeticionDeHorasExtra.organization_id, PeticionDeHorasExtra.estado,
                                      func.sum(PeticionDeHorasExtra.horas))
                           .filter(PeticionDeHorasExtra.fecha >= c.hoy - timedelta(days=30))
                           .group_by(PeticionDeHorasExtra.organization_id, PeticionDeHorasExtra.estado)):
        f.sumar((c.empresa(org), _v(estado)), h)
    return [f]


def _ausencias(c: _Contexto):
    from sqlalchemy import func
    from app.models.resources import Absence, AbsenceStatus

    f = _Familia("contecflow_negocio_ausencias",
                 "Ausencias por empresa: aprobadas que cubren hoy (hoy) y solicitudes pendientes (pendientes).",
                 ("empresa", "estado"))
    for org, n in (c.db.query(Absence.organization_id, func.count(Absence.id))
                   .filter(Absence.status == AbsenceStatus.approved, Absence.start_date <= c.hoy,
                           Absence.end_date >= c.hoy)
                   .group_by(Absence.organization_id)):
        f.sumar((c.empresa(org), "hoy"), n)
    for org, n in (c.db.query(Absence.organization_id, func.count(Absence.id))
                   .filter(Absence.status == AbsenceStatus.pending).group_by(Absence.organization_id)):
        f.sumar((c.empresa(org), "pendientes"), n)
    return [f]


def _demanda(c: _Contexto):
    from sqlalchemy import func
    from app.models.demanda import DemandRequest

    filas = (c.db.query(DemandRequest.organization_id, DemandRequest.current_phase_key,
                        func.count(DemandRequest.id))
             .filter(DemandRequest.closed_at.is_(None))
             .group_by(DemandRequest.organization_id, DemandRequest.current_phase_key).all())
    # Las fases las configura cada empresa: solo las _TOPE_VALORES más pobladas
    # tienen etiqueta propia.
    totales: dict = defaultdict(float)
    for _, fase, n in filas:
        totales[_v(fase or "sin_fase")] += n
    propias = {k for k, _ in sorted(totales.items(), key=lambda kv: -kv[1])[:_TOPE_VALORES]}
    f = _Familia("contecflow_negocio_demanda_abiertas",
                 "Solicitudes de demanda abiertas por empresa y fase.", ("empresa", "fase"))
    for org, fase, n in filas:
        fase = _v(fase or "sin_fase")
        f.sumar((c.empresa(org), fase if fase in propias else "otras"), n)

    sla = getattr(c, "sla", None)
    if sla is not None:
        for org, n in (c.db.query(DemandRequest.organization_id, func.count(DemandRequest.id))
                       .filter(DemandRequest.closed_at.is_(None), DemandRequest.sla_breached.is_(True))
                       .group_by(DemandRequest.organization_id)):
            sla.sumar((c.empresa(org), "demanda", "incumplido"), n)
        for org, n in (c.db.query(DemandRequest.organization_id, func.count(DemandRequest.id))
                       .filter(DemandRequest.closed_at.is_(None), DemandRequest.sla_warned.is_(True),
                               DemandRequest.sla_breached.is_(False))
                       .group_by(DemandRequest.organization_id)):
            sla.sumar((c.empresa(org), "demanda", "en_riesgo"), n)
    return [f]


_HALLAZGO_ABIERTO = ("open", "triaged", "in_progress")


def _vulnerabilidades(c: _Contexto):
    from sqlalchemy import func
    from app.models.cmdb_software import VulnerabilityFinding as F

    f = _Familia("contecflow_negocio_vulnerabilidades_abiertas",
                 "Hallazgos de vulnerabilidad abiertos por empresa y severidad.", ("empresa", "severidad"))
    for org, sev, n in (c.db.query(F.organization_id, F.severity, func.count(F.id))
                        .filter(F.status.in_(_HALLAZGO_ABIERTO))
                        .group_by(F.organization_id, F.severity)):
        f.sumar((c.empresa(org), _v(sev)), n)

    sla = getattr(c, "sla", None)
    if sla is not None:
        for org, n in (c.db.query(F.organization_id, func.count(F.id))
                       .filter(F.status.in_(_HALLAZGO_ABIERTO), F.sla_due_at < c.ahora)
                       .group_by(F.organization_id)):
            sla.sumar((c.empresa(org), "vulnerabilidades", "incumplido"), n)
        for org, n in (c.db.query(F.organization_id, func.count(F.id))
                       .filter(F.status.in_(_HALLAZGO_ABIERTO), F.sla_due_at >= c.ahora,
                               F.sla_due_at < c.ahora + timedelta(days=3))
                       .group_by(F.organization_id)):
            sla.sumar((c.empresa(org), "vulnerabilidades", "en_riesgo"), n)
    return [f]


def _riesgo(c: _Contexto):
    from sqlalchemy import func
    from app.models.cmdb_riesgo import RiskSnapshot as R

    ultimo = (c.db.query(R.organization_id, func.max(R.day).label("dia"))
              .filter(R.scope_type == "org").group_by(R.organization_id).subquery())
    f = _Familia("contecflow_negocio_indice_riesgo",
                 "Índice de riesgo (0-100) de la última foto diaria de cada empresa.", ("empresa", "tipo"))
    filas = (c.db.query(R.organization_id, R.score, R.accepted_score)
             .join(ultimo, (R.organization_id == ultimo.c.organization_id) & (R.day == ultimo.c.dia))
             .filter(R.scope_type == "org"))
    vistos: dict = {}
    for org, score, aceptado in filas:
        etiqueta = c.empresa(org)
        # Varias empresas en `otras`: el índice no se suma, vale el peor.
        clave = (etiqueta, "bruto")
        vistos[clave] = max(vistos.get(clave, 0.0), float(score or 0))
        clave = (etiqueta, "aceptado")
        vistos[clave] = max(vistos.get(clave, 0.0), float(aceptado or 0))
    for clave, valor in vistos.items():
        f.valores[clave] = valor
    return [f]


def _licencias_y_equipos(c: _Contexto):
    from sqlalchemy import func
    from app.models.alm import ALMAsignacion, ALMAsset, ALMLicense

    lic = _Familia("contecflow_negocio_licencias", "Licencias de software por empresa y estado.",
                   ("empresa", "estado"))
    for org, estado, n in (c.db.query(ALMLicense.organization_id, ALMLicense.status, func.count(ALMLicense.id))
                           .filter(ALMLicense.is_active.is_(True))
                           .group_by(ALMLicense.organization_id, ALMLicense.status)):
        lic.sumar((c.empresa(org), _v(estado)), n)

    puestos = _Familia("contecflow_negocio_licencias_puestos",
                       "Puestos de licencia por empresa: contratados (totales) y asignados en vigor (asignados).",
                       ("empresa", "tipo"))
    for org, n in (c.db.query(ALMLicense.organization_id, func.sum(ALMLicense.total_seats))
                   .filter(ALMLicense.is_active.is_(True)).group_by(ALMLicense.organization_id)):
        puestos.sumar((c.empresa(org), "totales"), n)
    for org, n in (c.db.query(ALMAsignacion.organization_id, func.count(ALMAsignacion.id))
                   .filter(ALMAsignacion.resource_type == "license", ALMAsignacion.status == "active")
                   .group_by(ALMAsignacion.organization_id)):
        puestos.sumar((c.empresa(org), "asignados"), n)

    equipos = _Familia("contecflow_negocio_equipos", "Equipos (hardware) por empresa y estado.",
                       ("empresa", "estado"))
    for org, estado, n in (c.db.query(ALMAsset.organization_id, ALMAsset.status, func.count(ALMAsset.id))
                           .filter(ALMAsset.is_active.is_(True))
                           .group_by(ALMAsset.organization_id, ALMAsset.status)):
        equipos.sumar((c.empresa(org), _v(estado)), n)
    return [lic, puestos, equipos]


def _ia(c: _Contexto):
    from sqlalchemy import func
    from app.models.ai_providers import AIUsageLog as L

    filas = (c.db.query(L.organization_id, L.module, L.success, func.count(L.id),
                        func.sum(L.tokens_in), func.sum(L.tokens_out), func.sum(L.cost_usd))
             .filter(L.created_at >= c.ahora - timedelta(hours=24))
             .group_by(L.organization_id, L.module, L.success).all())
    totales: dict = defaultdict(float)
    for _, mod, _, n, *_ in filas:
        totales[_v(mod)] += n
    propios = {k for k, _ in sorted(totales.items(), key=lambda kv: -kv[1])[:_TOPE_VALORES]}

    pet = _Familia("contecflow_negocio_ia_peticiones_24h",
                   "Llamadas a IA en las últimas 24 h por empresa, módulo y resultado.",
                   ("empresa", "modulo", "resultado"))
    tok = _Familia("contecflow_negocio_ia_tokens_24h",
                   "Tokens de IA en las últimas 24 h por empresa, módulo y sentido.", ("empresa", "modulo", "sentido"))
    coste = _Familia("contecflow_negocio_ia_coste_usd_24h",
                     "Coste estimado de IA (USD) en las últimas 24 h por empresa y módulo.", ("empresa", "modulo"))
    for org, mod, ok, n, t_in, t_out, usd in filas:
        e, m = c.empresa(org), _v(mod)
        m = m if m in propios else "otros"
        pet.sumar((e, m, "ok" if ok else "error"), n)
        tok.sumar((e, m, "entrada"), t_in)
        tok.sumar((e, m, "salida"), t_out)
        coste.sumar((e, m), usd)
    return [pet, tok, coste]


def _accesos(c: _Contexto):
    from sqlalchemy import func
    from app.models.security_observability import SecurityEvent as S

    f = _Familia("contecflow_negocio_logins_24h",
                 "Logins registrados por el SOC en las últimas 24 h por empresa y resultado.",
                 ("empresa", "resultado"))
    for org, tipo, n in (c.db.query(S.org_id, S.event_type, func.count(S.id))
                         .filter(S.event_type.in_(("login_success", "login_failed")),
                                 S.occurred_at >= c.ahora_naive - timedelta(hours=24))
                         .group_by(S.org_id, S.event_type)):
        f.sumar((c.empresa(org), "correcto" if tipo == "login_success" else "fallido"), n)
    return [f]


def _usuarios(c: _Contexto):
    from sqlalchemy import func
    from app.models.sessions import UserSession
    from app.models.user import User

    f = _Familia("contecflow_negocio_usuarios_activos",
                 "Usuarios distintos activos por empresa: sesión vista en 15 min (15m), "
                 "último login en 24 h (24h) o en 30 días (30d).", ("empresa", "ventana"))
    for org, n in (c.db.query(UserSession.organization_id, func.count(func.distinct(UserSession.user_id)))
                   .filter(UserSession.revoked_at.is_(None),
                           UserSession.last_seen_at >= c.ahora - timedelta(minutes=15))
                   .group_by(UserSession.organization_id)):
        f.sumar((c.empresa(org), "15m"), n)
    for ventana, delta in (("24h", timedelta(hours=24)), ("30d", timedelta(days=30))):
        for org, n in (c.db.query(User.organization_id, func.count(User.id))
                       .filter(User.is_active.is_(True), User.last_login >= c.ahora - delta)
                       .group_by(User.organization_id)):
            f.sumar((c.empresa(org), ventana), n)
    return [f]


#: (nombre del bloque, función). `tickets` va primero: crea la familia de SLA.
BLOQUES: list[tuple[str, Callable]] = [
    ("tickets", _tickets),
    ("proyectos", _proyectos),
    ("horas", _horas),
    ("horas_extra", _horas_extra),
    ("ausencias", _ausencias),
    ("demanda", _demanda),
    ("vulnerabilidades", _vulnerabilidades),
    ("riesgo", _riesgo),
    ("licencias_equipos", _licencias_y_equipos),
    ("ia", _ia),
    ("accesos", _accesos),
    ("usuarios", _usuarios),
]


def _cola_de_celery() -> list:
    """Longitud de la cola de Celery en Redis (LLEN de la cola por defecto)."""
    from app.core.config import settings

    g = GaugeMetricFamily("contecflow_celery_cola_longitud",
                          "Tareas de Celery esperando en la cola de Redis.", labels=["cola"])
    url = settings.REDIS_URL or ""
    if not url.startswith(("redis://", "rediss://")):
        return []
    import redis

    cliente = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
    try:
        g.add_metric(["celery"], float(cliente.llen("celery")))
    finally:
        try:
            cliente.close()
        except Exception:
            logger.debug("_cola_de_celery: cierre best-effort", exc_info=True)
    return [g]


class ColectorDeNegocio:
    """Colector con caché. `describe()` vacío: así se puede registrar en el
    registro nuevo de cada scrape (modo multiproceso) sin que el registro lo
    ejecute al registrarlo."""

    def __init__(self, bloques=None, ttl: float | None = None, sesion=None):
        self._bloques = list(bloques or BLOQUES)
        self._ttl = ttl
        self._sesion = sesion  # fábrica de sesiones (pruebas); por defecto SessionLocal
        self._cache: list = []
        self._hasta = 0.0
        self._cerrojo = threading.Lock()
        self._errores: dict = defaultdict(float)
        self._ultima_ok = 0.0
        self._duracion = 0.0

    def describe(self):
        return []

    def _ttl_efectivo(self) -> float:
        if self._ttl is not None:
            return float(self._ttl)
        from app.core.config import settings
        return float(max(5, int(settings.METRICS_BUSINESS_CACHE_SECONDS or 60)))

    def _calcular(self) -> list:
        fabrica = self._sesion
        if fabrica is None:
            from app.db.session import SessionLocal
            fabrica = SessionLocal
        inicio = time.perf_counter()
        familias: list = []
        db = fabrica()
        try:
            from app.db.session import sin_filtro_de_tenant
            with sin_filtro_de_tenant(db):
                c = _Contexto(db, mapa_de_empresas(db))
                for nombre, bloque in self._bloques:
                    try:
                        familias.extend(f.metrica() for f in bloque(c))
                    except Exception:
                        self._errores[nombre] += 1
                        logger.warning("Métricas de negocio: falló el bloque %s", nombre, exc_info=True)
                        try:
                            db.rollback()
                        except Exception:
                            logger.debug("rollback best-effort", exc_info=True)
                if getattr(c, "sla", None) is not None:
                    familias.append(c.sla.metrica())
        finally:
            try:
                db.rollback()
            finally:
                db.close()
        try:
            familias.extend(_cola_de_celery())
        except Exception:
            self._errores["cola_celery"] += 1
            logger.debug("Métricas: no se pudo leer la cola de Celery", exc_info=True)
        self._duracion = time.perf_counter() - inicio
        self._ultima_ok = time.time()
        return familias

    def _propias(self) -> list:
        err = CounterMetricFamily("contecflow_negocio_colector_errores",
                                  "Bloques del colector de negocio que fallaron.", labels=["bloque"])
        for bloque, n in sorted(self._errores.items()):
            err.add_metric([bloque], n)
        dur = GaugeMetricFamily("contecflow_negocio_colector_duracion_seconds",
                                "Duración del último cálculo del colector de negocio.")
        dur.add_metric([], self._duracion)
        ult = GaugeMetricFamily("contecflow_negocio_colector_ultimo_calculo_timestamp_seconds",
                                "Momento (epoch) del último cálculo del colector de negocio.")
        ult.add_metric([], self._ultima_ok)
        return [err, dur, ult]

    def collect(self):
        try:
            ahora = time.monotonic()
            if ahora >= self._hasta:
                with self._cerrojo:
                    if time.monotonic() >= self._hasta:
                        try:
                            self._cache = self._calcular()
                        except Exception:
                            self._errores["sesion"] += 1
                            logger.warning("Métricas de negocio: no se pudo calcular", exc_info=True)
                        self._hasta = time.monotonic() + self._ttl_efectivo()
            yield from self._cache
            yield from self._propias()
        except Exception:
            logger.debug("ColectorDeNegocio.collect: fallo best-effort", exc_info=True)


_colector: ColectorDeNegocio | None = None


def colector() -> ColectorDeNegocio:
    """El colector del proceso (uno: su caché es por proceso)."""
    global _colector
    if _colector is None:
        _colector = ColectorDeNegocio()
    return _colector


__all__ = ["ColectorDeNegocio", "colector", "BLOQUES"]
