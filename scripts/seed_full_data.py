#!/usr/bin/env python3
"""
seed_full_data.py — Seed masivo de datos 2025-2027 para Contecflow-PSA.

Genera datos realistas para:
  - Usuarios adicionales (15 nuevos)
  - Clientes (8 nuevos)
  - Proyectos (15) con fases y tareas
  - Imputaciones diarias (~2500 registros, ene 2025 – mar 2027)
  - Gastos (~80)
  - Facturas (~35)
  - Tickets de soporte (~150)
  - Ausencias (~45)
    - Épicas y dependencias
    - Sprints (proyectos ágiles, sprints bi-semanales 2025-2026)
    - Milestones y entregables
    - UAT interno (casos) y UAT portal (sesiones/test cases/issues)
    - Problemas ITSM y enlaces incidente→problema

Uso:
  cd /path/to/contecflow-PSA
  source venv/bin/activate
  python scripts/seed_full_data.py

El script es IDEMPOTENTE: omite registros con code/number ya existente.
"""

import sys
import os
import uuid
import random
from datetime import date, timedelta, datetime
from typing import Optional

# ── Ajustar path para imports de la app ───────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.models.clients import Client, ClientStatus, ClientIndustry
from app.models.project import (
    Project, ProjectPhase, ProjectMember, ProjectMemberRole,
    ProjectType, ProjectStatus, ProjectRisk,
)
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.imputation import Imputation
from app.models.expenses import Expense, ExpenseCategory, ExpenseStatus
from app.models.billing_reports import Invoice, InvoiceLine, InvoiceStatus
from app.models.service_desk import (
    Ticket, TicketType, TicketStatus, TicketPriority,
    TicketUrgency, TicketImpact,
)
from app.models.resources import Absence, AbsenceType, AbsenceStatus
from app.models.sprints import Sprint, SprintTask, SprintStatus
from app.models.financial import ProjectMilestone
from app.models.resources import Deliverable, DeliverableStatus
from app.models.epics import Epic, EpicTask, EpicDependency, Mention, ThreadedComment
from app.models.service_desk import Problem, ProblemStatus, IncidentToProblem
from app.models.raci import UATCase, UATStatus as UATCaseStatus
from app.models.okrs import Objective, KeyResult, KRCheckin, OKRPeriod, OKRStatus, KRType
from app.models.performance import ReviewCycle, PerformanceReview, ReviewCycleStatus, ReviewStatus
from app.models.documents import (
    Document,
    DocumentVersion,
    DocumentPermission,
    DocumentTag,
    DocumentAccessLog,
    DocumentCategory,
    DocumentAccessLevel,
    ApprovalStatus,
)
from app.models.client_portal import (
    ClientUser,
    UATSession,
    UATTestCase,
    UATIssue,
    UATStatus as PortalUATStatus,
)

random.seed(42)  # reproducible

TODAY = date.today()
TWO_YEARS_AGO = TODAY - timedelta(days=730)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def uid() -> str:
    return str(uuid.uuid4())


def workdays_in_range(start: date, end: date):
    """Yield every working day (Mon–Fri) between start and end inclusive."""
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))


def random_datetime(start: date, end: date) -> datetime:
    d = random_date(start, end)
    return datetime.combine(d, datetime.min.time()) + timedelta(
        hours=random.randint(8, 20),
        minutes=random.randint(0, 59),
    )


def exists(db, model, **kwargs):
    """Return True if a record matching kwargs already exists."""
    return db.query(model).filter_by(**kwargs).first() is not None


def next_counter_from_codes(codes: list[str], prefix: str, floor: int = 0) -> int:
    """Return next integer suffix for codes like PREFIX-0001."""
    max_n = floor
    for code in codes:
        if not code or not str(code).startswith(prefix):
            continue
        tail = str(code).replace(prefix, "", 1)
        digits = "".join(ch for ch in tail if ch.isdigit())
        if digits:
            max_n = max(max_n, int(digits))
    return max_n + 1


def month_start_iterator(start: date, end_exclusive: date):
    """Yield first day of each month in [start, end_exclusive)."""
    d = date(start.year, start.month, 1)
    while d < end_exclusive:
        yield d
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)


def enum_or_default(enum_cls, value, default_value):
    try:
        return enum_cls(value)
    except Exception:
        return default_value


# ─────────────────────────────────────────────────────────────────────────────
# 1. USUARIOS ADICIONALES
# ─────────────────────────────────────────────────────────────────────────────

NEW_USERS = [
    # username, email, full_name, role, department, job_title, hourly_rate, weekly_h
    ("jorge.sanz",    "jorge.sanz@company.com",    "Jorge Sanz",        "employee", "Backend",        "Senior Developer",         72.0, 40),
    ("patricia.vidal","patricia.vidal@company.com","Patricia Vidal",    "employee", "QA",             "QA Engineer",              60.0, 40),
    ("roberto.leal",  "roberto.leal@company.com",  "Roberto Leal",      "employee", "Frontend",       "Frontend Developer",       58.0, 40),
    ("nuria.campo",   "nuria.campo@company.com",   "Nuria Campo",       "pm",       "Gestion",        "Senior PM",                80.0, 40),
    ("ivan.mora",     "ivan.mora@company.com",     "Iván Mora",         "employee", "IA / Data",      "ML Engineer",              85.0, 40),
    ("silvia.rios",   "silvia.rios@company.com",   "Silvia Ríos",       "employee", "Infraestructura","Cloud Engineer",           78.0, 40),
    ("tomas.ferrer",  "tomas.ferrer@company.com",  "Tomás Ferrer",      "employee", "Backend",        "Mid Developer",            55.0, 40),
    ("laura.mendez",  "laura.mendez@company.com",  "Laura Méndez",      "employee", "Diseno UX",      "Product Designer",         67.0, 40),
    ("miguel.puig",   "miguel.puig@company.com",   "Miguel Puig",       "employee", "QA",             "QA Automation Engineer",   62.0, 40),
    ("beatriz.sole",  "beatriz.sole@company.com",  "Beatriz Solé",      "employee", "Backend",        "Junior Developer",         45.0, 40),
    ("andres.gil",    "andres.gil@company.com",    "Andrés Gil",        "pm",       "Gestion",        "Project Manager",          75.0, 40),
    ("carmen.valls",  "carmen.valls@company.com",  "Carmen Valls",      "employee", "Frontend",       "React Developer",          60.0, 40),
    ("pau.costa",     "pau.costa@company.com",     "Pau Costa",         "employee", "Infraestructura","SRE / DevOps",             80.0, 40),
    ("andrea.font",   "andrea.font@company.com",   "Andrea Font",       "employee", "IA / Data",      "Data Analyst",             70.0, 40),
    ("raul.domingo",  "raul.domingo@company.com",  "Raúl Domingo",      "employee", "Backend",        "Tech Lead",                88.0, 40),
]

# ─────────────────────────────────────────────────────────────────────────────
# 2. CLIENTES ADICIONALES
# ─────────────────────────────────────────────────────────────────────────────

NEW_CLIENTS = [
    # short_name, name, industry, contact_name, contact_email, city, country, payment_terms, annual_rev_eur
    ("GlobalFinance",  "GlobalFinance Europa SA",        "finance",       "Ana Blanco",   "ana@globalfinance.eu",     "Madrid",    "ES", "30 dias"),
    ("HealthPlus",     "HealthPlus Medical SL",          "healthcare",    "Marc Ribas",   "marc@healthplus.es",       "Barcelona", "ES", "15 dias"),
    ("RetailNow",      "RetailNow Group SA",             "retail",        "Irene Pons",   "irene@retailnow.com",      "Valencia",  "ES", "30 dias"),
    ("LogisTech",      "LogisTech Iberia SL",            "other",         "Daniel Cruz",  "daniel@logistech.io",      "Zaragoza",  "ES", "45 dias"),
    ("EduFuture",      "EduFuture Plataforma SL",        "education",     "Marta Soler",  "marta@edufuture.es",       "Bilbao",    "ES", "30 dias"),
    ("ConstruSmart",   "ConstruSmart Technologies SL",   "other",         "Jordi Fuster", "jordi@construsmart.com",   "Girona",    "ES", "60 dias"),
    ("MediaGroup",     "MediaGroup Digital SA",          "media",         "Laia Tort",    "laia@mediagroup.digital",  "Madrid",    "ES", "15 dias"),
    ("AgroData",       "AgroData Systems SL",            "other",         "Ferran Mas",   "ferran@agrodata.es",       "Lleida",    "ES", "30 dias"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 3. PROYECTOS (15)  — mix de estados, facturación, fechas
# ─────────────────────────────────────────────────────────────────────────────

# Each tuple: (code, name, type, status, risk, client_short, billing_type, contract_amt,
#              billing_rate, budget_h, start, end_planned, end_real, is_billable, tags, pm_username)
PROJECTS_DEF = [
    # ─── Proyectos COMPLETADOS 2025 ──────────────────────────────────────────
    ("PRJ-050", "Migración ERP a SAP S/4HANA",
         "consulting", "completed", "medium", "GlobalFinance",
     "fixed_price", 280_000, 120.0, 2200,
     date(2025, 1, 15), date(2025, 9, 30), date(2025, 10, 10), True,
     "SAP,ERP,migración", "nuria.campo"),

    ("PRJ-051", "App móvil HealthPlus Patient",
         "development", "completed", "low", "HealthPlus",
     "time_material", 95_000, 85.0, 1100,
     date(2025, 2, 1), date(2025, 7, 31), date(2025, 8, 5), True,
     "mobile,react-native,salud", "carlos.ruiz"),

    ("PRJ-052", "Plataforma Analytics RetailNow",
         "development", "completed", "high", "RetailNow",
     "time_material", None, 95.0, 800,
     date(2025, 3, 1), date(2025, 11, 30), date(2025, 12, 1), True,
     "BI,analytics,retail", "ana.torres"),

    ("PRJ-053", "Portal Logístico B2B LogisTech",
         "development", "completed", "medium", "LogisTech",
     "fixed_price", 150_000, 80.0, 1800,
     date(2025, 4, 1), date(2025, 12, 31), date(2026, 1, 15), True,
     "portal,B2B,logistics", "andres.gil"),

    # ─── Proyectos EN CURSO 2025–2026 ────────────────────────────────────────
    ("PRJ-054", "LMS EduFuture V2",
         "development", "active", "medium", "EduFuture",
     "fixed_price", 200_000, 90.0, 2100,
     date(2025, 6, 1), date(2026, 6, 30), None, True,
     "LMS,education,e-learning", "nuria.campo"),

    ("PRJ-055", "Smart Building ConstruSmart",
         "development", "active", "high", "ConstruSmart",
     "time_material", None, 95.0, 1500,
     date(2025, 9, 1), date(2026, 9, 30), None, True,
     "IoT,smart-building,construction", "carlos.ruiz"),

    ("PRJ-056", "Rediseño Digital MediaGroup",
         "consulting", "active", "low", "MediaGroup",
     "time_material", None, 85.0, 900,
     date(2025, 10, 1), date(2026, 4, 30), None, True,
     "design,web,media", "ana.torres"),

    ("PRJ-057", "IA Predicción Cosechas AgroData",
         "rd", "active", "high", "AgroData",
     "fixed_price", 130_000, 100.0, 1300,
     date(2026, 1, 1), date(2026, 12, 31), None, True,
     "IA,ML,agro,forecasting", "andres.gil"),

    ("PRJ-058", "Retainer Soporte GlobalFinance",
         "maintenance", "active", "low", "GlobalFinance",
     "recurring_retainer", None, 120.0, None,
     date(2025, 1, 1), date(2027, 12, 31), None, True,
     "soporte,retainer,finance", "nuria.campo"),

    ("PRJ-059", "Retainer Soporte HealthPlus",
         "maintenance", "active", "low", "HealthPlus",
     "recurring_retainer", None, 90.0, None,
     date(2025, 3, 1), date(2027, 3, 31), None, True,
     "soporte,retainer,salud", "carlos.ruiz"),

    # ─── Proyectos INTERNOS ───────────────────────────────────────────────────
    ("PRJ-060", "Modernización Infraestructura Cloud",
         "internal", "active", "medium", None,
     "time_material", None, None, 600,
     date(2025, 7, 1), date(2026, 6, 30), None, False,
     "cloud,AWS,infra,interno", "ana.torres"),

    ("PRJ-061", "I+D Motor IA Copilot",
         "rd", "active", "high", None,
     "time_material", None, None, 1200,
     date(2025, 1, 1), date(2026, 12, 31), None, False,
     "IA,R&D,copilot,interno", "andres.gil"),

    # ─── Proyectos PLANIFICADOS 2026–2027 ─────────────────────────────────────
    ("PRJ-062", "Plataforma Omnicanal RetailNow V2",
         "development", "planning", "medium", "RetailNow",
     "fixed_price", 320_000, 110.0, 2800,
     date(2026, 7, 1), date(2027, 6, 30), None, True,
     "omnicanal,ecommerce,retail", "nuria.campo"),

    ("PRJ-063", "Auditoría Ciberseguridad MediaGroup",
         "consulting", "planning", "low", "MediaGroup",
     "fixed_price", 45_000, 130.0, 320,
     date(2026, 9, 1), date(2026, 12, 31), None, True,
     "seguridad,audit,media", "carlos.ruiz"),

    ("PRJ-064", "Data Warehouse LogisTech 2.0",
         "development", "planning", "medium", "LogisTech",
     "time_material", None, 100.0, 900,
     date(2027, 1, 1), date(2027, 9, 30), None, True,
     "datawarehouse,ETL,logistica", "andres.gil"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 4. TAREAS por proyecto (plantillas, se instancian con numeración)
# ─────────────────────────────────────────────────────────────────────────────

TASK_TEMPLATES = {
    "PRJ-050": [  # SAP ERP migration
        ("Análisis de procesos AS-IS", "high", 40, "in_progress→done"),
        ("Diseño arquitectura SAP", "critical", 60, "done"),
        ("Migración módulo FI/CO", "critical", 120, "done"),
        ("Migración módulo MM/SD", "high", 100, "done"),
        ("Migración módulo HR", "high", 80, "done"),
        ("Integración APIs externas", "high", 60, "done"),
        ("Testing unitario SAP", "medium", 80, "done"),
        ("UAT con cliente", "high", 40, "done"),
        ("Formación usuarios clave", "medium", 30, "done"),
        ("Go-Live y soporte 2 semanas", "critical", 80, "done"),
        ("Documentación técnica", "low", 20, "done"),
        ("Cierre proyecto y acta", "medium", 10, "done"),
    ],
    "PRJ-051": [  # App móvil HealthPlus
        ("Definición de requisitos funcionales", "high", 20, "done"),
        ("Wireframes y prototipo UX", "medium", 30, "done"),
        ("Setup CI/CD y entornos", "high", 15, "done"),
        ("Módulo autenticación paciente", "high", 25, "done"),
        ("Módulo citas médicas", "critical", 40, "done"),
        ("Módulo historial clínico", "high", 50, "done"),
        ("Módulo notificaciones push", "medium", 20, "done"),
        ("Integración HL7 FHIR", "critical", 35, "done"),
        ("Testing en dispositivos iOS/Android", "high", 30, "done"),
        ("Publicación App Store / Play Store", "medium", 10, "done"),
        ("Monitorización post-lanzamiento", "low", 15, "done"),
    ],
    "PRJ-052": [  # Analytics RetailNow
        ("Inventario fuentes de datos", "high", 15, "done"),
        ("Diseño modelo dimensional (DWH)", "critical", 40, "done"),
        ("ETL ventas y stock", "high", 60, "done"),
        ("ETL CRM y marketing", "high", 50, "done"),
        ("Dashboards ejecutivos Power BI", "high", 40, "done"),
        ("Dashboard operacional tiendas", "medium", 30, "done"),
        ("Modelo forecasting demanda", "critical", 80, "done"),
        ("Alertas automáticas stock", "high", 25, "done"),
        ("QA datos y validación", "medium", 30, "done"),
        ("Formación equipo analítica", "low", 20, "done"),
    ],
    "PRJ-053": [  # Portal LogisTech
        ("Diseño sistema de roles", "high", 20, "done"),
        ("API gateway REST", "critical", 40, "done"),
        ("Módulo gestión pedidos", "critical", 50, "done"),
        ("Módulo tracking envíos", "high", 40, "done"),
        ("Módulo facturación automática", "high", 35, "done"),
        ("Integración ERP cliente", "critical", 60, "done"),
        ("Portal web React", "high", 80, "done"),
        ("App móvil conductores", "high", 60, "done"),
        ("Testing E2E", "medium", 40, "done"),
        ("Despliegue producción AWS", "high", 20, "done"),
    ],
    "PRJ-054": [  # LMS EduFuture
        ("Análisis pedagógico plataforma actual", "medium", 25, "done"),
        ("Arquitectura microservicios LMS", "critical", 45, "done"),
        ("Módulo gestión cursos", "high", 55, "done"),
        ("Módulo alumnos y matrículas", "high", 40, "in_progress"),
        ("Motor de evaluaciones", "critical", 70, "in_progress"),
        ("Gamificación y badges", "medium", 30, "todo"),
        ("Integración videoconferencia (Zoom/Teams)", "high", 25, "todo"),
        ("App móvil alumnos", "high", 60, "todo"),
        ("Analytics de aprendizaje", "medium", 35, "todo"),
        ("Testing y QA global", "high", 50, "todo"),
        ("Migración contenidos plataforma vieja", "medium", 40, "backlog"),
        ("Formación profesores", "low", 20, "backlog"),
    ],
    "PRJ-055": [  # Smart Building
        ("Inventario sensores IoT", "high", 20, "done"),
        ("Plataforma IoT Hub AWS", "critical", 50, "done"),
        ("Dashboard tiempo real edificio", "high", 40, "in_progress"),
        ("Módulo HVAC inteligente", "critical", 60, "in_progress"),
        ("Módulo control accesos", "high", 45, "in_progress"),
        ("Algoritmos eficiencia energética", "high", 70, "todo"),
        ("Alertas mantenimiento predictivo", "medium", 40, "todo"),
        ("App facility manager", "medium", 50, "todo"),
        ("Integración BMS legacy", "critical", 55, "todo"),
        ("Testing integración end-to-end", "high", 40, "backlog"),
    ],
    "PRJ-056": [  # MediaGroup rediseño
        ("Auditoría UX plataforma actual", "medium", 15, "done"),
        ("Nuevo Design System", "high", 40, "done"),
        ("Landing page corporativa", "high", 30, "done"),
        ("Portal periodistas", "high", 40, "in_progress"),
        ("CMS headless (Contentful)", "high", 35, "in_progress"),
        ("Optimización SEO técnico", "medium", 25, "todo"),
        ("Integración redes sociales", "low", 15, "todo"),
        ("Testing A/B y analítica", "medium", 20, "backlog"),
    ],
    "PRJ-057": [  # IA AgroData
        ("Recolección y limpieza datos históricos", "critical", 40, "done"),
        ("Feature engineering agrícola", "high", 50, "done"),
        ("Modelo baseline predicción cosechas", "critical", 60, "in_progress"),
        ("Modelo LSTM series temporales", "critical", 80, "in_progress"),
        ("API REST servicio predicción", "high", 30, "todo"),
        ("Dashboard agricultores", "high", 40, "todo"),
        ("Integración datos meteorológicos", "medium", 25, "todo"),
        ("Evaluación y validación campo", "high", 30, "backlog"),
        ("Documentación modelo", "low", 15, "backlog"),
    ],
    "PRJ-058": [  # Retainer GlobalFinance
        ("Soporte correctivo mensual", "high", 20, "in_progress"),
        ("Evolutivos dashboard financiero", "medium", 15, "in_progress"),
        ("Revisión seguridad trimestral", "high", 10, "todo"),
    ],
    "PRJ-059": [  # Retainer HealthPlus
        ("Soporte nivel 1 incidencias", "high", 20, "in_progress"),
        ("Actualizaciones menores app", "medium", 10, "in_progress"),
        ("Revisión compliance GDPR", "high", 8, "todo"),
    ],
    "PRJ-060": [  # Infra Cloud interna
        ("Migración VMs a contenedores Docker", "high", 40, "done"),
        ("Setup Kubernetes cluster", "critical", 60, "done"),
        ("Implementación GitOps (ArgoCD)", "high", 30, "in_progress"),
        ("Optimización costes cloud", "medium", 25, "in_progress"),
        ("Observabilidad Grafana + Prometheus", "high", 35, "todo"),
        ("Disaster recovery plan", "critical", 30, "todo"),
    ],
    "PRJ-061": [  # I+D IA
        ("Investigación LLMs open source", "high", 60, "done"),
        ("PoC agente IA con LangChain", "critical", 80, "done"),
        ("Integración modelo embeddings", "high", 50, "in_progress"),
        ("Motor RAG documentación técnica", "critical", 90, "in_progress"),
        ("Evaluación y benchmarking modelos", "high", 40, "todo"),
        ("API pública NexusAssist", "medium", 35, "todo"),
        ("Tests calidad respuestas IA", "high", 30, "backlog"),
    ],
    "PRJ-062": [  # Omnicanal RetailNow V2
        ("Análisis requisitos omnicanal", "high", 30, "todo"),
        ("Arquitectura plataforma nueva", "critical", 50, "todo"),
        ("Módulo unificación inventario", "critical", 70, "backlog"),
        ("Módulo pedidos unificados", "high", 60, "backlog"),
        ("App vendedor en tienda", "high", 55, "backlog"),
        ("Integración marketplaces externos", "medium", 45, "backlog"),
    ],
    "PRJ-063": [  # Auditoría seguridad
        ("Reconocimiento y footprinting", "high", 20, "todo"),
        ("Análisis vulnerabilidades (OWASP)", "critical", 40, "todo"),
        ("Pruebas de penetración", "critical", 50, "backlog"),
        ("Informe ejecutivo", "high", 15, "backlog"),
    ],
    "PRJ-064": [  # DWH LogisTech 2.0
        ("Diseño modelo estrella DWH", "high", 35, "backlog"),
        ("ETL rutas y entregas", "high", 50, "backlog"),
        ("Cuadros de mando operativos", "medium", 40, "backlog"),
        ("Modelo ML predicción retrasos", "critical", 60, "backlog"),
    ],
}

# Mapeo status string a enum (simplificado)
TASK_STATUS_MAP = {
    "backlog":     TaskStatus.backlog,
    "todo":        TaskStatus.todo,
    "in_progress": TaskStatus.in_progress,
    "done":        TaskStatus.done,
    "cancelled":   TaskStatus.cancelled,
    "in_review":   TaskStatus.in_review,
    "done":        TaskStatus.done,
}

TICKET_TITLES_INCIDENTS = [
    "Error crítico: sistema no responde tras despliegue",
    "Caída del servicio de autenticación",
    "Timeout en integración con ERP externo",
    "Pérdida de datos en módulo de facturación",
    "Error 500 intermitente en portal cliente",
    "Fallo en cron de generación de informes nocturnos",
    "Problemas de rendimiento en dashboard principal",
    "Certificado SSL expirado en entorno de pruebas",
    "Error en sincronización con Jira",
    "Bloqueo de usuarios por política de contraseñas",
    "Base de datos sin espacio en disco",
    "Servicio de notificaciones email caído",
    "Rollback fallido tras actualización",
    "Latencia elevada en API de búsqueda",
    "Error en módulo de aprobaciones",
    "Fallo en backup automático de BD",
    "Problemas de acceso VPN usuarios remotos",
    "Error al generar PDF de facturas",
    "Caída de microservicio de IA",
    "Inconsistencia de datos entre módulos",
]

TICKET_TITLES_REQUESTS = [
    "Solicitud alta nuevo usuario administrador",
    "Crear grupo de soporte nivel 2",
    "Ampliar cuota almacenamiento proyecto",
    "Configurar integración con Slack",
    "Actualizar permisos rol Project Manager",
    "Crear plantilla email corporativa",
    "Exportar datos históricos a CSV",
    "Habilitar módulo de BI para cliente",
    "Migrar proyecto de entorno test a producción",
    "Solicitud formación usuarios finales",
    "Configurar nuevo tenant organización",
    "Actualizar logo y branding corporativo",
    "Añadir campo personalizado en tickets",
    "Configurar alertas de capacidad",
    "Habilitar autenticación SSO",
    "Aumentar límite de tareas por sprint",
    "Configurar política SLA nueva",
    "Crear dashboard ejecutivo personalizado",
    "Solicitud backup manual urgente",
    "Configurar webhook con sistema externo",
]

TICKET_TITLES_PROBLEMS = [
    "Análisis causa raíz: caídas recurrentes API",
    "Investigación degradación rendimiento módulo finanzas",
    "Problema subyacente: memory leak en worker",
    "Análisis fallos intermitentes sincronización",
    "Problema crónico de timeouts en base de datos",
    "Revisión arquitectura autenticación multi-tenant",
]

TICKET_TITLES_CHANGES = [
    "Actualización versión Node.js 20 LTS",
    "Upgrade PostgreSQL 14 → 16",
    "Despliegue hotfix seguridad parche crítico",
    "Migración base de datos a nueva región AWS",
    "Actualización certificados SSL producción",
    "Cambio de configuración límites API rate",
    "Actualización dependencias críticas npm",
    "Despliegue versión 2.5.0 plataforma",
    "Rotación de claves API servicios externos",
    "Actualización política de backups",
]

EXPENSE_DESCRIPTIONS = {
    "travel": [
        "Vuelo Barcelona–Madrid cliente GlobalFinance",
        "Vuelo Madrid–Frankfurt conferencia SAP",
        "Tren AVE reunión cliente RetailNow",
        "Vuelo Madrid–Londres formación AWS",
        "Vuelo Barcelona–Lisboa partner meeting",
        "Tren Valencia–Barcelona kick-off proyecto",
    ],
    "accommodation": [
        "Hotel NH Madrid 3 noches cliente GlobalFinance",
        "Hotel Barceló 2 noches reunión HealthPlus",
        "Apartamento Airbnb Frankfurt 4 noches",
        "Hotel Meliá 1 noche formación interna",
        "Hostal económico 2 noches visita cliente",
    ],
    "meals": [
        "Comida de equipo kick-off proyecto",
        "Cena con cliente GlobalFinance",
        "Almuerzo reunión mensual equipo",
        "Catering reunión retrospectiva",
        "Dietas viaje cliente HealthPlus",
    ],
    "software": [
        "Licencia Figma anual equipo diseño",
        "Suscripción GitHub Copilot equipo",
        "Licencia JetBrains All Products Pack",
        "Renovación licencia AWS DevTools",
        "Herramienta monitorización DataDog mensual",
        "Licencia Jira Software 10 usuarios",
        "Suscripción Notion equipo",
    ],
    "hardware": [
        "MacBook Pro M3 dev backend",
        "Monitor 4K LG 27\" para diseñadora",
        "Dock USB-C Thunderbolt x2",
        "Teclado mecánico ergonómico",
        "Servidor rack desarrollo local",
    ],
    "training": [
        "Curso AWS Solutions Architect (Udemy)",
        "Certificación PMP - formación PMI",
        "Curso React Advanced (Frontend Masters)",
        "Formación LLMs y RAG (Coursera)",
        "Certificación Kubernetes CKA",
        "Seminario Agile / Scrum avanzado",
    ],
    "subcontract": [
        "Diseño visual marca identidad cliente",
        "Consultoría especialista SAP FICO",
        "Traducción documentación técnica EN/DE",
        "Revisión legal contrato SaaS",
        "Subcontrata fotógrafo materiales marketing",
    ],
    "other": [
        "Material oficina equipo",
        "Gastos envío documentación cliente",
        "Sello notarial poderes empresa",
    ],
}

EPIC_BLUEPRINTS = {
    "PRJ-054": [
        ("SEED Epic LMS Core", "Núcleo funcional LMS: cursos, matrículas y evaluaciones", "in_progress", "high", "#2563eb"),
        ("SEED Epic Mobile Learning", "Experiencia móvil para alumnado", "open", "medium", "#0ea5e9"),
        ("SEED Epic Analytics Educativo", "Métricas de progreso y rendimiento", "open", "medium", "#14b8a6"),
    ],
    "PRJ-055": [
        ("SEED Epic IoT Captura", "Captura y normalización de señales IoT", "in_progress", "critical", "#f97316"),
        ("SEED Epic Control Inteligente", "Automatización de HVAC y accesos", "open", "high", "#ef4444"),
        ("SEED Epic Predictivo", "Mantenimiento predictivo y alertas", "open", "high", "#a855f7"),
    ],
    "PRJ-057": [
        ("SEED Epic Data Pipeline Agro", "Preparación y calidad de datos de cultivo", "in_progress", "high", "#22c55e"),
        ("SEED Epic Modelado Forecast", "Modelos de predicción temporal", "in_progress", "critical", "#16a34a"),
        ("SEED Epic Explotación Producto", "APIs y dashboard para cliente final", "open", "medium", "#0f766e"),
    ],
    "PRJ-062": [
        ("SEED Epic Omnicanal Inventario", "Unificación stock canales tienda/ecommerce", "open", "high", "#eab308"),
        ("SEED Epic Omnicanal Pedidos", "Orquestación de pedidos y fulfillment", "open", "high", "#f59e0b"),
    ],
}

DELIVERABLE_FORMATS = [
    "Documento funcional PDF",
    "Paquete código fuente",
    "Manual de operación",
    "Informe técnico",
    "Presentación ejecutiva",
    "Paquete despliegue",
]

UAT_TEST_STATES = ["pending", "passed", "failed", "blocked", "skipped"]

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("  SEED FULL DATA — Contecflow-PSA 2025-2027")
        print("=" * 60)

        # ── 1. Usuarios ──────────────────────────────────────────────────────
        print("\n[1/9] Creando usuarios adicionales...")
        user_map: dict[str, str] = {}  # username → id

        # Cargar existentes
        for u in db.query(User).all():
            user_map[u.username] = u.id

        hashed_pw = get_password_hash("Contec2026!")
        created_users = 0
        for (uname, email, fname, role, dept, title, rate, wh) in NEW_USERS:
            if uname not in user_map:
                u = User(
                    id=uid(), username=uname, email=email, full_name=fname,
                    role=UserRole(role), department=dept, job_title=title,
                    hourly_rate=rate, weekly_capacity_hours=wh,
                    hashed_password=hashed_pw, is_active=True,
                )
                db.add(u)
                user_map[uname] = u.id
                created_users += 1
        db.commit()
        print(f"   ✓ {created_users} usuarios creados ({len(user_map)} total)")

        # ── 2. Clientes ───────────────────────────────────────────────────────
        print("\n[2/9] Creando clientes adicionales...")
        client_map: dict[str, str] = {}  # short_name → id

        for c in db.query(Client).all():
            client_map[c.short_name] = c.id

        created_clients = 0
        for (sname, name, industry, cname, cemail, city, country, terms) in NEW_CLIENTS:
            if sname not in client_map:
                cid = uid()
                c = Client(
                    id=cid, name=name, short_name=sname,
                    industry=ClientIndustry(industry) if industry in [e.value for e in ClientIndustry] else ClientIndustry.other,
                    status=ClientStatus.active,
                    contact_name=cname, contact_email=cemail,
                    city=city, country=country, payment_terms=terms,
                    currency="EUR",
                )
                db.add(c)
                client_map[sname] = cid
                created_clients += 1
        db.commit()
        print(f"   ✓ {created_clients} clientes creados ({len(client_map)} total)")

        # ── 3. Proyectos ──────────────────────────────────────────────────────
        print("\n[3/9] Creando proyectos...")
        project_map: dict[str, str] = {}  # code → id

        for p in db.query(Project).all():
            project_map[p.code] = p.id

        created_projects = 0
        for row in PROJECTS_DEF:
            (code, name, ptype, pstatus, risk, client_sname, billing_type,
             contract_amt, billing_rate, budget_h, start, end_plan, end_real,
             is_billable, tags, pm_uname) = row

            if code in project_map:
                continue

            client_id = client_map.get(client_sname) if client_sname else None
            pm_id = user_map.get(pm_uname)
            ptype_map = {
                "development": ProjectType.development,
                "maintenance": ProjectType.maintenance,
                "rd": ProjectType.rd,
                "internal": ProjectType.internal,
                "consulting": ProjectType.consulting,
            }
            pstatus_map = {
                "planning": ProjectStatus.planning,
                    "active": ProjectStatus.active,
                "completed": ProjectStatus.completed,
                "on_hold": ProjectStatus.on_hold,
            }
            prisk_map = {
                "low": ProjectRisk.low,
                "medium": ProjectRisk.medium,
                "high": ProjectRisk.high,
            }

            prj = Project(
                id=uid(), code=code, name=name,
                project_type=ptype_map.get(ptype, ProjectType.development),
                status=pstatus_map.get(pstatus, ProjectStatus.active),
                risk_level=prisk_map.get(risk, ProjectRisk.medium),
                client_id=client_id,
                client_name=client_sname,
                billing_type=billing_type,
                contract_amount=contract_amt,
                billing_rate=billing_rate,
                budget_hours=budget_h,
                is_billable=is_billable,
                start_date=start,
                end_date_planned=end_plan,
                end_date_real=end_real,
                pm_id=pm_id,
                tags=tags,
                currency="EUR",
            )
            db.add(prj)
            project_map[code] = prj.id
            created_projects += 1

            # Fases del proyecto (3 genéricas)
            phase_names = ["Inicio y planificación", "Desarrollo y ejecución", "Cierre y entrega"]
            for i, pname in enumerate(phase_names):
                db.add(ProjectPhase(
                    id=uid(), project_id=prj.id, name=pname, order=i + 1,
                ))

        db.commit()
        print(f"   ✓ {created_projects} proyectos creados ({len(project_map)} total)")

        # ── 4. Tareas ─────────────────────────────────────────────────────────
        print("\n[4/9] Creando tareas...")
        # Counter de tasks: buscar max numérico actual
        from sqlalchemy import func as sqlfunc
        max_task_code_row = db.execute(
            __import__("sqlalchemy").text(
                "SELECT MAX(CAST(REPLACE(code,'TSK-','') AS INTEGER)) FROM tasks WHERE code LIKE 'TSK-%'"
            )
        ).scalar()
        task_counter = max(int(max_task_code_row or 0), 999) + 1

        task_map: dict[str, str] = {}  # code → id (for sprint assignment)
        project_tasks: dict[str, list[str]] = {}  # project_code → [task_ids]

        # Available devs/employees for assignment
        dev_usernames = [
            "luis.vega", "marta.gil", "sara.lope", "diego.mora", "elena.pardo",
            "jorge.sanz", "patricia.vidal", "roberto.leal", "ivan.mora", "silvia.rios",
            "tomas.ferrer", "laura.mendez", "miguel.puig", "beatriz.sole",
            "carmen.valls", "pau.costa", "andrea.font", "raul.domingo",
        ]
        dev_ids = [user_map[u] for u in dev_usernames if u in user_map]

        created_tasks = 0
        for proj_code, task_defs in TASK_TEMPLATES.items():
            if proj_code not in project_map:
                continue
            prj_id = project_map[proj_code]
            project_tasks[proj_code] = []

            # Find project start for date spread
            prj = db.query(Project).filter_by(id=prj_id).first()
            prj_start = prj.start_date or date(2025, 1, 1)

            for i, (title, priority_str, est_h, status_hint) in enumerate(task_defs):
                tcode = f"TSK-{task_counter:04d}"
                if exists(db, Task, code=tcode):
                    task_counter += 1
                    continue

                prio_map = {
                    "critical": TaskPriority.critical,
                    "high":     TaskPriority.high,
                    "medium":   TaskPriority.medium,
                    "low":      TaskPriority.low,
                }

                # Derive status
                status_key = status_hint.split("→")[-1].strip()
                status = TASK_STATUS_MAP.get(status_key, TaskStatus.todo)

                task_start = prj_start + timedelta(weeks=i * 2)
                task_due = task_start + timedelta(weeks=3)
                completed_at = None
                if status == TaskStatus.done:
                    completed_at = datetime.combine(task_due, datetime.min.time())

                assignee_id = random.choice(dev_ids) if dev_ids else None
                reporter_id = prj.pm_id

                t = Task(
                    id=uid(), code=tcode, project_id=prj_id,
                    title=title,
                    description=f"Descripción detallada: {title}. Criterios de aceptación definidos en la especificación funcional.",
                    status=status,
                    priority=prio_map.get(priority_str, TaskPriority.medium),
                    estimated_hours=float(est_h),
                    assignee_id=assignee_id,
                    reporter_id=reporter_id,
                    start_date=task_start,
                    due_date=task_due,
                    completed_at=completed_at,
                    issue_type="task",
                )
                db.add(t)
                task_map[tcode] = t.id
                project_tasks[proj_code].append(t.id)
                task_counter += 1
                created_tasks += 1

        db.commit()
        print(f"   ✓ {created_tasks} tareas creadas")

        # Reruns: hydrate mapping with already existing tasks as well
        for proj_code, proj_id in project_map.items():
            task_ids_existing = [
                t.id for t in db.query(Task.id).filter(Task.project_id == proj_id).all()
            ]
            if task_ids_existing:
                project_tasks.setdefault(proj_code, [])
                # Preserve insertion order while deduplicating
                merged = list(dict.fromkeys(project_tasks[proj_code] + task_ids_existing))
                project_tasks[proj_code] = merged

        # ── 5. Imputaciones ───────────────────────────────────────────────────
        print("\n[5/9] Generando imputaciones (enero 2025 – marzo 2027)...")
        # Assign developers to projects (realistic allocation)
        project_teams = {
            "PRJ-050": ["luis.vega", "jorge.sanz", "tomas.ferrer", "patricia.vidal", "raul.domingo"],
            "PRJ-051": ["roberto.leal", "laura.mendez", "miguel.puig", "carmen.valls", "beatriz.sole"],
            "PRJ-052": ["marta.gil", "andrea.font", "ivan.mora", "patricia.vidal"],
            "PRJ-053": ["luis.vega", "roberto.leal", "tomas.ferrer", "carmen.valls", "silvia.rios"],
            "PRJ-054": ["jorge.sanz", "roberto.leal", "beatriz.sole", "laura.mendez", "miguel.puig", "raul.domingo"],
            "PRJ-055": ["silvia.rios", "pau.costa", "ivan.mora", "jorge.sanz"],
            "PRJ-056": ["elena.pardo", "laura.mendez", "roberto.leal", "diego.mora"],
            "PRJ-057": ["marta.gil", "ivan.mora", "andrea.font", "raul.domingo"],
            "PRJ-058": ["luis.vega", "raul.domingo", "patricia.vidal"],
            "PRJ-059": ["roberto.leal", "miguel.puig", "beatriz.sole"],
            "PRJ-060": ["silvia.rios", "pau.costa", "sara.lope"],
            "PRJ-061": ["marta.gil", "ivan.mora", "andrea.font", "raul.domingo", "jorge.sanz"],
        }

        # Seasonal patterns: month → multiplier (August/Dec lower)
        SEASONAL = {1: 1.0, 2: 1.0, 3: 1.05, 4: 1.0, 5: 1.05,
                    6: 0.9, 7: 0.85, 8: 0.5, 9: 1.0, 10: 1.0,
                    11: 1.0, 12: 0.7}

        imp_start = date(2025, 1, 1)
        imp_end = date(2027, 3, 31)

        # Pre-fetch project data
        prj_obj_map: dict[str, "Project"] = {}
        for code in project_teams:
            if code in project_map:
                prj_obj_map[code] = db.query(Project).filter_by(id=project_map[code]).first()

        # Check how many imputations already exist (avoid re-seeding)
        existing_imp_count = db.query(Imputation).count()
        if existing_imp_count > 500:
            print(f"   ⚠ Ya existen {existing_imp_count} imputaciones, saltando generación masiva.")
        else:
            created_imps = 0
            batch = []

            for day in workdays_in_range(imp_start, imp_end):
                month_mult = SEASONAL.get(day.month, 1.0)

                for proj_code, team in project_teams.items():
                    if proj_code not in prj_obj_map:
                        continue
                    prj_obj = prj_obj_map[proj_code]

                    # Check project active on this day
                    if prj_obj.start_date and day < prj_obj.start_date:
                        continue
                    if prj_obj.end_date_real and day > prj_obj.end_date_real:
                        continue
                    if prj_obj.end_date_planned and day > prj_obj.end_date_planned + timedelta(days=30):
                        continue

                    # Only a subset of team works each day
                    active_devs = [u for u in team if u in user_map]
                    if not active_devs:
                        continue
                    working_today = random.sample(active_devs, k=min(random.randint(1, len(active_devs)), len(active_devs)))

                    for uname in working_today:
                        uid_val = user_map[uname]
                        base_hours = random.uniform(3.0, 8.0) * month_mult
                        # Weekday variation: Mon/Fri slightly less
                        if day.weekday() in (0, 4):
                            base_hours *= 0.8
                        hours = round(max(0.5, min(base_hours, 8.0)), 1)

                        # Pick a task from the project
                        task_ids = project_tasks.get(proj_code, [])
                        task_id = random.choice(task_ids) if task_ids else None

                        # Rate snapshot
                        for u_row in NEW_USERS:
                            if u_row[0] == uname:
                                rate = u_row[6] or 0.0
                                break
                        else:
                            # Existing users
                            rates = {
                                "ana.torres": 85.0, "luis.vega": 70.0, "marta.gil": 80.0,
                                "carlos.ruiz": 75.0, "sara.lope": 72.0, "diego.mora": 55.0,
                                "elena.pardo": 65.0,
                            }
                            rate = rates.get(uname, 60.0)

                        cost = round(hours * rate, 2)

                        imp = Imputation(
                            id=uid(), user_id=uid_val, project_id=project_map[proj_code],
                            task_id=task_id, date=day, hours=hours,
                            hourly_rate_snapshot=rate, cost_amount=cost,
                            is_billable=prj_obj.is_billable,
                            is_approved=(day < date(2026, 10, 1)),  # older imps are approved
                            description=f"Trabajo en {prj_obj.name} – {day.strftime('%B %Y')}",
                        )
                        batch.append(imp)
                        created_imps += 1

                        if len(batch) >= 500:
                            db.bulk_save_objects(batch)
                            db.commit()
                            batch.clear()
                            print(f"   ... {created_imps} imputaciones insertadas", end="\r")

            if batch:
                db.bulk_save_objects(batch)
                db.commit()
                batch.clear()

            print(f"\n   ✓ {created_imps} imputaciones creadas")

        # ── 6. Gastos ─────────────────────────────────────────────────────────
        print("\n[6/9] Creando gastos...")
        max_exp_row = db.execute(
            __import__("sqlalchemy").text(
                "SELECT MAX(CAST(REPLACE(code,'EXP-','') AS INTEGER)) FROM expenses WHERE code LIKE 'EXP-%'"
            )
        ).scalar()
        exp_counter = max(int(max_exp_row or 0), 999) + 1

        created_expenses = 0
        billable_projects = [c for c in ["PRJ-050","PRJ-051","PRJ-052","PRJ-053","PRJ-054","PRJ-055","PRJ-056","PRJ-057"] if c in project_map]

        for _ in range(80):
            ecode = f"EXP-{exp_counter:04d}"
            if exists(db, Expense, code=ecode):
                exp_counter += 1
                continue

            cat = random.choice(list(ExpenseCategory))
            descriptions = EXPENSE_DESCRIPTIONS.get(cat.value, ["Gasto operativo"])
            desc = random.choice(descriptions)

            amt_ranges = {
                "travel": (80, 600), "accommodation": (60, 400), "meals": (15, 120),
                "software": (20, 800), "hardware": (200, 2500), "training": (50, 1500),
                "subcontract": (500, 8000), "other": (10, 200),
            }
            lo, hi = amt_ranges.get(cat.value, (50, 500))
            amount = round(random.uniform(lo, hi), 2)

            exp_date = random_date(date(2025, 1, 1), date(2026, 12, 31))
            proj_code = random.choice(billable_projects) if random.random() < 0.8 else None
            prj_id_exp = project_map.get(proj_code) if proj_code else None
            user_exp = random.choice(list(user_map.values()))

            statuses = [ExpenseStatus.approved, ExpenseStatus.approved, ExpenseStatus.approved,
                        ExpenseStatus.submitted, ExpenseStatus.reimbursed, ExpenseStatus.rejected]
            status = random.choice(statuses) if exp_date < date(2026, 6, 1) else ExpenseStatus.submitted

            e = Expense(
                id=uid(), code=ecode, user_id=user_exp, project_id=prj_id_exp,
                category=cat, description=desc, amount=amount, currency="EUR",
                expense_date=exp_date, is_billable=(prj_id_exp is not None),
                status=status,
            )
            db.add(e)
            exp_counter += 1
            created_expenses += 1

        db.commit()
        print(f"   ✓ {created_expenses} gastos creados")

        # ── 7. Facturas ───────────────────────────────────────────────────────
        print("\n[7/9] Creando facturas...")
        inv_counter = 1
        # Find max existing
        existing_invs = db.query(Invoice).count()
        inv_base = existing_invs + 1

        created_invoices = 0
        billable_prjs_for_inv = [
            ("PRJ-050", "GlobalFinance", 30_000, date(2025,1,1), date(2025,10,1), "paid"),
            ("PRJ-051", "HealthPlus",    10_000, date(2025,2,1), date(2025,8,1),  "paid"),
            ("PRJ-052", "RetailNow",      8_000, date(2025,3,1), date(2025,12,1), "paid"),
            ("PRJ-053", "LogisTech",     12_000, date(2025,4,1), date(2026,2,1),  "paid"),
            ("PRJ-054", "EduFuture",     15_000, date(2025,6,1), date(2026,5,1),  "sent"),
            ("PRJ-055", "ConstruSmart",  10_000, date(2025,9,1), date(2026,10,1), "sent"),
            ("PRJ-056", "MediaGroup",     7_000, date(2025,10,1),date(2026,5,1),  "sent"),
            ("PRJ-057", "AgroData",       9_000, date(2026,1,1), date(2026,12,1), "sent"),
            ("PRJ-058", "GlobalFinance",  4_500, date(2025,1,1), date(2027,1,1),  "mixed"),  # retainer mensual
            ("PRJ-059", "HealthPlus",     3_000, date(2025,3,1), date(2027,3,1),  "mixed"),
        ]

        admin_id = user_map.get("admin")
        TAX_RATE = 21.0

        for (proj_code, client_sname, monthly_amount, inv_start, inv_end, inv_scenario) in billable_prjs_for_inv:
            if proj_code not in project_map:
                continue
            prj_id_inv = project_map[proj_code]
            cli_id = client_map.get(client_sname)

            # Generate monthly invoices
            d = date(inv_start.year, inv_start.month, 1)
            while d < inv_end:
                inv_num = f"INV-{d.year}-{inv_base + created_invoices:04d}"
                if not exists(db, Invoice, number=inv_num):
                    subtotal = monthly_amount * random.uniform(0.85, 1.15)
                    subtotal = round(subtotal, 2)
                    tax_amt = round(subtotal * TAX_RATE / 100, 2)
                    total = round(subtotal + tax_amt, 2)

                    issue = d
                    due = d + timedelta(days=30)

                    if inv_scenario == "paid" and d < date(2026, 1, 1):
                        status = InvoiceStatus.paid
                        paid_date = d + timedelta(days=random.randint(5, 35))
                    elif inv_scenario == "mixed":
                        if d < date(2026, 3, 1):
                            status = InvoiceStatus.paid
                            paid_date = d + timedelta(days=random.randint(5, 30))
                        elif d < date(2026, 9, 1):
                            status = InvoiceStatus.sent
                            paid_date = None
                        else:
                            status = InvoiceStatus.draft
                            paid_date = None
                    else:
                        if d < date(2025, 12, 1):
                            status = InvoiceStatus.paid
                            paid_date = d + timedelta(days=random.randint(5, 35))
                        elif d < date(2026, 6, 1):
                            status = InvoiceStatus.sent
                            paid_date = None
                        else:
                            status = InvoiceStatus.draft
                            paid_date = None

                    inv = Invoice(
                        id=uid(), number=inv_num,
                        project_id=prj_id_inv, client_id=cli_id,
                        client_name=client_sname,
                        subtotal=subtotal, tax_rate=TAX_RATE,
                        tax_amount=tax_amt, total=total, currency="EUR",
                        issue_date=issue, due_date=due,
                        paid_date=paid_date if status == InvoiceStatus.paid else None,
                        status=status,
                        notes=f"Factura mensual {d.strftime('%B %Y')} – {proj_code}",
                        period_from=d,
                        period_to=date(d.year, d.month, 28),
                        created_by=admin_id,
                    )
                    db.add(inv)
                    created_invoices += 1

                    # Add invoice line
                    db.flush()
                    line = InvoiceLine(
                        id=uid(), invoice_id=inv.id, order=1,
                        description=f"Servicios profesionales {d.strftime('%B %Y')}",
                            quantity=1.0, unit_price=subtotal, amount=subtotal,
                    )
                    db.add(line)

                # Next month
                if d.month == 12:
                    d = date(d.year + 1, 1, 1)
                else:
                    d = date(d.year, d.month + 1, 1)

        db.commit()
        print(f"   ✓ {created_invoices} facturas creadas")

        # ── 8. Tickets de soporte ─────────────────────────────────────────────
        print("\n[8/9] Creando tickets de soporte...")
        max_tick_row = db.execute(
            __import__("sqlalchemy").text(
                "SELECT MAX(CAST(REPLACE(number,'INC-','') AS INTEGER)) FROM sd_tickets WHERE number LIKE 'INC-%'"
            )
        ).scalar()
        tick_counter = max(int(max_tick_row or 0), 999) + 1

        agent_usernames = ["luis.vega", "patricia.vidal", "miguel.puig", "jorge.sanz", "silvia.rios"]
        agent_ids = [user_map[u] for u in agent_usernames if u in user_map]
        requester_ids = list(user_map.values())

        created_tickets = 0
        all_client_ids = list(client_map.values())

        for i in range(150):
            tick_num = f"INC-{tick_counter:04d}"
            if exists(db, Ticket, number=tick_num):
                tick_counter += 1
                continue

            # Weight: 60% incidents, 25% requests, 10% problems, 5% changes
            rnd = random.random()
            if rnd < 0.60:
                ttype = TicketType.incident
                title = random.choice(TICKET_TITLES_INCIDENTS)
            elif rnd < 0.85:
                ttype = TicketType.service_request
                title = random.choice(TICKET_TITLES_REQUESTS)
            elif rnd < 0.95:
                ttype = TicketType.problem
                title = random.choice(TICKET_TITLES_PROBLEMS)
            else:
                ttype = TicketType.change
                title = random.choice(TICKET_TITLES_CHANGES)

            ticket_date = random_date(date(2025, 1, 1), date(2026, 12, 31))

            # Priority weighted towards medium/low
            prio_rand = random.random()
            if prio_rand < 0.05:
                prio = TicketPriority.p1_critical
            elif prio_rand < 0.20:
                prio = TicketPriority.p2_high
            elif prio_rand < 0.65:
                prio = TicketPriority.p3_medium
            else:
                prio = TicketPriority.p4_low

            # Status weighted by date
            if ticket_date < date(2026, 1, 1):
                status_choices = [TicketStatus.resolved, TicketStatus.resolved, TicketStatus.closed,
                                  TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]
            elif ticket_date < date(2026, 9, 1):
                status_choices = [TicketStatus.resolved, TicketStatus.in_progress,
                                      TicketStatus.pending_client, TicketStatus.closed, TicketStatus.new]
            else:
                status_choices = [TicketStatus.new, TicketStatus.in_progress,
                                      TicketStatus.new, TicketStatus.pending_client]

            tstatus = random.choice(status_choices)

            resolved_at = None
            resolution_min = None
            first_resp_min = None
            first_resp_at = None

            if tstatus in (TicketStatus.resolved, TicketStatus.closed):
                first_resp_min = random.randint(5, 480)
                resolution_min = random.randint(30, 2880)  # 30 min to 48h
                first_resp_at = datetime.combine(ticket_date, datetime.min.time()) + timedelta(minutes=first_resp_min)
                resolved_at = datetime.combine(ticket_date, datetime.min.time()) + timedelta(minutes=resolution_min)

            assigned_id = random.choice(agent_ids) if agent_ids and random.random() > 0.15 else None
            requester_id = random.choice(requester_ids)
            cli_id = random.choice(all_client_ids) if all_client_ids and random.random() > 0.3 else None

            ticket = Ticket(
                id=uid(), number=tick_num,
                ticket_type=ttype, title=title,
                description=f"Descripción detallada del ticket: {title}. El usuario reporta el problema desde el portal de soporte. Se requiere atención en los tiempos establecidos por el SLA.",
                status=tstatus, priority=prio,
                urgency=TicketUrgency.medium, impact=TicketImpact.user,
                requester_user_id=requester_id,
                assigned_to_user_id=assigned_id,
                client_id=cli_id,
                source=random.choice(["portal", "email", "phone", "chat"]),
                first_response_at=first_resp_at,
                resolved_at=resolved_at,
                first_response_minutes=first_resp_min,
                resolution_minutes=resolution_min,
                sla_response_breached=(first_resp_min is not None and first_resp_min > 240),
                sla_resolution_breached=(resolution_min is not None and resolution_min > 1440),
                csat_score=random.randint(3, 5) if tstatus == TicketStatus.closed and random.random() > 0.4 else None,
                time_spent_minutes=resolution_min if resolution_min else random.randint(15, 120),
                tags=random.choice(["soporte,L1", "infra,urgente", "facturación", "accesos", "IA,bugs", ""]),
            )
            db.add(ticket)
            tick_counter += 1
            created_tickets += 1

        db.commit()
        print(f"   ✓ {created_tickets} tickets creados")

        # ── 9. Ausencias ──────────────────────────────────────────────────────
        print("\n[9/9] Creando ausencias...")
        all_user_ids = list(user_map.values())
        created_absences = 0

        absence_patterns = [
            # (type, min_days, max_days, typical_months)
            (AbsenceType.vacation, 5, 20, [7, 8, 12, 1]),
            (AbsenceType.sick, 1, 5, list(range(1, 13))),
            (AbsenceType.personal, 1, 2, list(range(1, 13))),
            (AbsenceType.training, 2, 5, [2, 3, 4, 9, 10, 11]),
            (AbsenceType.paternity, 15, 15, [1, 2, 3, 4, 5, 6]),
        ]

        # 45 absences spread across 2025-2026
        existing_abs = db.query(Absence).count()
        if existing_abs < 20:
            for user_id in random.choices(all_user_ids, k=45):
                atype, min_d, max_d, months = random.choice(absence_patterns)
                month = random.choice(months)
                year = random.choice([2025, 2025, 2026])
                try:
                    start_d = date(year, month, random.randint(1, 20))
                except ValueError:
                    start_d = date(year, month, 1)
                days = random.randint(min_d, max_d)
                end_d = start_d + timedelta(days=days - 1)

                # Status: mostly approved for past, pending for future
                if end_d < date(2026, 6, 1):
                    abs_status = AbsenceStatus.approved
                else:
                    abs_status = random.choice([AbsenceStatus.pending, AbsenceStatus.approved])

                absence = Absence(
                    id=uid(), user_id=user_id,
                    type=atype, status=abs_status,
                    start_date=start_d, end_date=end_d,
                        working_days=float(days),
                    reason=f"Solicitud {atype.value} {start_d.strftime('%B %Y')}",
                )
                db.add(absence)
                created_absences += 1

            db.commit()
        else:
            print(f"   ⚠ Ya existen {existing_abs} ausencias, saltando.")
        print(f"   ✓ {created_absences} ausencias creadas")

        # ── 10. Sprints y SprintTasks ───────────────────────────────────────
        print("\n[10/15] Creando sprints y asignaciones de backlog...")
        agile_project_codes = ["PRJ-054", "PRJ-055", "PRJ-056", "PRJ-057", "PRJ-061"]
        created_sprints = 0
        created_sprint_tasks = 0

        for pcode in agile_project_codes:
            pid = project_map.get(pcode)
            if not pid:
                continue
            proj = db.query(Project).filter(Project.id == pid).first()
            if not proj:
                continue

            sprint_start = proj.start_date or date(2025, 1, 1)
            sprint_end_limit = min(proj.end_date_planned or date(2026, 12, 31), date(2026, 12, 31))
            if sprint_start > sprint_end_limit:
                continue

            # Two-week cadence
            cursor = sprint_start
            sprint_number = 1
            while cursor <= sprint_end_limit and sprint_number <= 18:
                sd = cursor
                ed = min(cursor + timedelta(days=13), sprint_end_limit)
                sprint_name = f"SEED Sprint {sprint_number:02d} {pcode}"

                spr = db.query(Sprint).filter(
                    Sprint.project_id == pid,
                    Sprint.number == sprint_number,
                ).first()

                if not spr:
                    if ed < date.today() - timedelta(days=7):
                        sstatus = SprintStatus.completed
                    elif sd <= date.today() <= ed:
                        sstatus = SprintStatus.active
                    else:
                        sstatus = SprintStatus.planning

                    spr = Sprint(
                        id=uid(), project_id=pid, number=sprint_number,
                        name=sprint_name,
                        goal=f"Entregar incremento funcional del proyecto {pcode} en la iteración {sprint_number}",
                        status=sstatus,
                        start_date=sd,
                        end_date=ed,
                        planned_points=float(random.randint(18, 42)),
                        completed_points=float(random.randint(14, 40)) if sstatus == SprintStatus.completed else 0,
                        velocity=float(round(random.uniform(10.0, 28.0), 1)) if sstatus == SprintStatus.completed else None,
                        went_well="Buena colaboración de equipo y calidad estable.",
                        to_improve="Reducir bloqueos externos y mejorar cobertura de tests.",
                        action_items="Refinar criterios de DoR/DoD y monitorizar ciclo de PRs.",
                        created_by=proj.pm_id,
                    )
                    db.add(spr)
                    db.flush()
                    created_sprints += 1

                # Attach 4-8 tasks per sprint from same project
                p_tasks = db.query(Task).filter(Task.project_id == pid).all()
                if p_tasks:
                    sample_tasks = random.sample(p_tasks, k=min(random.randint(4, 8), len(p_tasks)))
                    for order, t in enumerate(sample_tasks, start=1):
                        if db.query(SprintTask).filter(
                            SprintTask.sprint_id == spr.id,
                            SprintTask.task_id == t.id,
                        ).first():
                            continue
                        db.add(SprintTask(
                            id=uid(), sprint_id=spr.id, task_id=t.id,
                            backlog_order=order,
                        ))
                        created_sprint_tasks += 1

                sprint_number += 1
                cursor = cursor + timedelta(days=14)

        db.commit()
        print(f"   ✓ {created_sprints} sprints creados, {created_sprint_tasks} SprintTasks creados")

        # ── 11. Épicas y dependencias ───────────────────────────────────────
        print("\n[11/15] Creando épicas y dependencias...")
        created_epics = 0
        created_epic_links = 0
        created_epic_deps = 0

        for pcode, blueprints in EPIC_BLUEPRINTS.items():
            pid = project_map.get(pcode)
            if not pid:
                continue

            project_tasks_rows = db.query(Task).filter(Task.project_id == pid).all()
            if not project_tasks_rows:
                continue

            created_epics_for_project = []
            for idx, (title, desc, status, priority, color) in enumerate(blueprints):
                epic = db.query(Epic).filter(Epic.project_id == pid, Epic.title == title).first()
                if not epic:
                    proj = db.query(Project).filter(Project.id == pid).first()
                    sd = (proj.start_date or date(2025, 1, 1)) + timedelta(days=idx * 21)
                    ed = sd + timedelta(days=90)
                    epic = Epic(
                        id=uid(), project_id=pid, title=title,
                        description=desc,
                        color=color,
                        status=status,
                        priority=priority,
                        start_date=sd.isoformat(),
                        end_date=ed.isoformat(),
                        sort_order=idx + 1,
                        created_by=proj.pm_id,
                    )
                    db.add(epic)
                    db.flush()
                    created_epics += 1

                created_epics_for_project.append(epic)

                # Cohesive task mapping by keyword
                key = title.lower()
                if "mobile" in key:
                    candidates = [t for t in project_tasks_rows if "móvil" in (t.title or "").lower() or "app" in (t.title or "").lower()]
                elif "analytics" in key or "forecast" in key or "model" in key:
                    candidates = [t for t in project_tasks_rows if any(k in (t.title or "").lower() for k in ["analytics", "modelo", "predicción", "dashboard", "etl"])]
                elif "iot" in key or "control" in key:
                    candidates = [t for t in project_tasks_rows if any(k in (t.title or "").lower() for k in ["iot", "control", "hvac", "sensor"])]
                else:
                    candidates = project_tasks_rows

                if not candidates:
                    candidates = project_tasks_rows
                chosen = random.sample(candidates, k=min(random.randint(3, 6), len(candidates)))
                for t in chosen:
                    if db.query(EpicTask).filter(EpicTask.epic_id == epic.id, EpicTask.task_id == t.id).first():
                        continue
                    db.add(EpicTask(id=uid(), epic_id=epic.id, task_id=t.id))
                    created_epic_links += 1

            # Chain dependencies E2 depends on E1, E3 depends on E2...
            for i in range(1, len(created_epics_for_project)):
                src = created_epics_for_project[i]
                dep = created_epics_for_project[i - 1]
                if db.query(EpicDependency).filter(
                    EpicDependency.epic_id == src.id,
                    EpicDependency.depends_on_id == dep.id,
                ).first():
                    continue
                db.add(EpicDependency(id=uid(), epic_id=src.id, depends_on_id=dep.id))
                created_epic_deps += 1

        db.commit()
        print(f"   ✓ {created_epics} épicas creadas, {created_epic_links} relaciones épica-tarea, {created_epic_deps} dependencias")

        # ── 12. Milestones y entregables ─────────────────────────────────────
        print("\n[12/15] Creando milestones y entregables...")
        created_milestones = 0
        created_deliverables = 0

        deliverable_codes = [x.code for x in db.query(Deliverable.code).all()]
        deliverable_counter = next_counter_from_codes(deliverable_codes, "DEL-SD-", floor=999)

        delivery_projects = [c for c in ["PRJ-050", "PRJ-051", "PRJ-052", "PRJ-053", "PRJ-054", "PRJ-055", "PRJ-056", "PRJ-057"] if c in project_map]
        for pcode in delivery_projects:
            pid = project_map[pcode]
            proj = db.query(Project).filter(Project.id == pid).first()
            if not proj:
                continue
            p_tasks = db.query(Task).filter(Task.project_id == pid).all()

            # 4 standard milestones per project
            for i, m_name in enumerate([
                "SEED-MILESTONE-01 Descubrimiento",
                "SEED-MILESTONE-02 Construcción",
                "SEED-MILESTONE-03 Validación",
                "SEED-MILESTONE-04 Entrega",
            ]):
                full_name = f"{m_name} {pcode}"
                ms = db.query(ProjectMilestone).filter(
                    ProjectMilestone.project_id == pid,
                    ProjectMilestone.name == full_name,
                ).first()
                if not ms:
                    due = (proj.start_date or date(2025, 1, 1)) + timedelta(days=45 * (i + 1))
                    status = ["completed", "approved", "pending_approval", "pending"][min(i, 3)]
                    ms = ProjectMilestone(
                        id=uid(), project_id=pid,
                        name=full_name,
                        description=f"Hito {i+1} del proyecto {pcode}",
                        due_date=due,
                        sort_order=i + 1,
                        billing_status=status,
                        is_completed=(status in ["completed", "approved", "pending_approval"]),
                        completed_date=due if status in ["completed", "approved", "pending_approval"] else None,
                        completed_by=proj.pm_id,
                        billing_amount=float(random.randint(12000, 50000)),
                        billing_pct=float([20, 30, 30, 20][i]),
                    )
                    db.add(ms)
                    db.flush()
                    created_milestones += 1

                # One deliverable per milestone
                d_name = f"SEED Deliverable {i+1} {pcode}"
                d = db.query(Deliverable).filter(
                    Deliverable.project_id == pid,
                    Deliverable.name == d_name,
                ).first()
                if not d:
                    d_code = f"DEL-SD-{deliverable_counter:04d}"
                    deliverable_counter += 1

                    d_status = [
                        DeliverableStatus.accepted,
                        DeliverableStatus.delivered,
                        DeliverableStatus.in_review,
                        DeliverableStatus.in_progress,
                    ][min(i, 3)]

                    owner_id = random.choice([t.assignee_id for t in p_tasks if t.assignee_id] or [proj.pm_id])
                    planned = ms.due_date
                    delivered = planned if d_status in [DeliverableStatus.accepted, DeliverableStatus.delivered, DeliverableStatus.in_review] else None
                    accepted = planned + timedelta(days=3) if d_status == DeliverableStatus.accepted else None

                    d = Deliverable(
                        id=uid(), code=d_code, project_id=pid,
                        name=d_name,
                        description=f"Entregable coherente con el hito {ms.name}",
                        format=random.choice(DELIVERABLE_FORMATS),
                        status=d_status,
                        planned_date=planned,
                        delivered_date=delivered,
                        accepted_date=accepted,
                        owner_id=owner_id,
                        client_contact=proj.client_name,
                        acceptance_criteria="Cumple requisitos funcionales, rendimiento mínimo y criterios de seguridad.",
                        milestone_id=ms.id,
                        sort_order=i + 1,
                    )
                    db.add(d)
                    created_deliverables += 1

        db.commit()
        print(f"   ✓ {created_milestones} milestones creados, {created_deliverables} entregables creados")

        # ── 13. UAT interno (uat_cases) ─────────────────────────────────────
        print("\n[13/15] Creando casos UAT internos...")
        created_uat_cases = 0

        for pcode in delivery_projects:
            pid = project_map[pcode]
            p_tasks = db.query(Task).filter(Task.project_id == pid).all()
            if not p_tasks:
                continue

            target_tasks = [t for t in p_tasks if t.status in [TaskStatus.done, TaskStatus.in_progress, TaskStatus.in_review]]
            if not target_tasks:
                target_tasks = p_tasks

            selected = target_tasks[: min(10, len(target_tasks))]
            for idx, t in enumerate(selected, start=1):
                title = f"SEED-UAT {pcode}-{idx:02d}: {t.title[:120]}"
                existing_case = db.query(UATCase).filter(
                    UATCase.project_id == pid,
                    UATCase.title == title,
                ).first()
                if existing_case:
                    continue

                status = UATCaseStatus.pending
                actual = None
                executed = None
                if t.status == TaskStatus.done:
                    status = random.choice([UATCaseStatus.passed, UATCaseStatus.passed, UATCaseStatus.failed])
                    executed = datetime.combine((t.completed_at.date() if t.completed_at else date.today()), datetime.min.time())
                    actual = "Comportamiento validado con los datos de prueba definidos." if status == UATCaseStatus.passed else "Se detecta desviación funcional en un flujo secundario."
                elif t.status == TaskStatus.in_progress:
                    status = random.choice([UATCaseStatus.pending, UATCaseStatus.blocked])

                db.add(UATCase(
                    id=uid(), project_id=pid, task_id=t.id,
                    title=title,
                    description=f"Ejecutar flujo UAT para la tarea {t.code}: {t.title}",
                    expected_result="La funcionalidad cumple criterios de aceptación, sin errores bloqueantes.",
                    actual_result=actual,
                    status=status,
                    priority=random.choice(["high", "medium", "critical"]),
                    assigned_to_id=t.assignee_id or t.reporter_id,
                    notes="Caso generado automáticamente para cobertura UAT de regresión.",
                    executed_at=executed,
                ))
                created_uat_cases += 1

        db.commit()
        print(f"   ✓ {created_uat_cases} casos UAT internos creados")

        # ── 14. UAT portal (sesiones, test cases, issues) ───────────────────
        print("\n[14/15] Creando UAT portal con clientes...")
        created_client_users = 0
        created_uat_sessions = 0
        created_uat_test_cases = 0
        created_uat_issues = 0

        # Ensure at least one client user per key client
        key_clients = ["GlobalFinance", "HealthPlus", "RetailNow", "LogisTech", "EduFuture", "MediaGroup"]
        client_user_by_client: dict[str, str] = {}

        for sname in key_clients:
            client_id = client_map.get(sname)
            if not client_id:
                continue
            email = f"qa.{sname.lower()}@client.example.com"
            cu = db.query(ClientUser).filter(ClientUser.email == email).first()
            if not cu:
                # Link to one project from this client when available
                p = db.query(Project).filter(Project.client_id == client_id).order_by(Project.start_date.asc()).first()
                cu = ClientUser(
                    id=uid(),
                    client_org_id=client_id,
                    project_id=(p.id if p else None),
                    full_name=f"QA {sname}",
                    email=email,
                    job_title="UAT Coordinator",
                    company=sname,
                    hashed_password=get_password_hash("ClientUAT2026!"),
                    is_active=True,
                    can_approve_deliverables=True,
                    can_request_changes=True,
                    can_view_budget=True,
                )
                db.add(cu)
                db.flush()
                created_client_users += 1
            client_user_by_client[sname] = cu.id

        # Sessions per project based on deliverables
        for pcode in delivery_projects:
            pid = project_map[pcode]
            proj = db.query(Project).filter(Project.id == pid).first()
            if not proj or not proj.client_name:
                continue

            deliverables = db.query(Deliverable).filter(Deliverable.project_id == pid).order_by(Deliverable.sort_order.asc()).all()
            if not deliverables:
                continue

            session_idx = 1
            for d in deliverables[:2]:
                uat_code = f"UATS-{pcode[-3:]}-{session_idx:02d}"
                title = f"SEED Portal UAT {pcode} #{session_idx}"
                session_idx += 1

                sess = db.query(UATSession).filter(
                    UATSession.project_id == pid,
                    UATSession.code == uat_code,
                ).first()

                if not sess:
                    result = random.choice([
                        PortalUATStatus.passed,
                        PortalUATStatus.passed,
                        PortalUATStatus.failed,
                        PortalUATStatus.conditional,
                    ])
                    available = d.planned_date or (proj.start_date or date(2025, 1, 1))
                    deadline = available + timedelta(days=10)
                    completed = datetime.combine(deadline, datetime.min.time()) if result in [PortalUATStatus.passed, PortalUATStatus.failed, PortalUATStatus.conditional] else None

                    sess = UATSession(
                        id=uid(), code=uat_code,
                        project_id=pid,
                        deliverable_id=d.id,
                        title=title,
                        description=f"Validación cliente del entregable {d.name}",
                        test_environment=f"https://uat-{pcode.lower()}.contecflow.local",
                        test_credentials="usuario_uat / password temporal",
                        test_guide_url="https://docs.contecflow.local/uat-guide",
                        status=PortalUATStatus.in_progress if completed is None else result,
                        available_from=available,
                        deadline=deadline,
                        completed_at=completed,
                        client_result=result if completed else None,
                        client_notes="Validación satisfactoria salvo observaciones menores." if result != PortalUATStatus.failed else "Se reportan defectos críticos en escenarios de borde.",
                        client_signed_by=client_user_by_client.get(proj.client_name),
                        client_signed_at=completed,
                    )
                    db.add(sess)
                    db.flush()
                    created_uat_sessions += 1

                # Test cases
                p_tasks = db.query(Task).filter(Task.project_id == pid).limit(5).all()
                for i, t in enumerate(p_tasks, start=1):
                    tc_title = f"SEED TC {pcode}-{sess.code}-{i:02d}"
                    tc = db.query(UATTestCase).filter(
                        UATTestCase.session_id == sess.id,
                        UATTestCase.title == tc_title,
                    ).first()
                    if tc:
                        continue

                    tc_status = random.choice(UAT_TEST_STATES)
                    db.add(UATTestCase(
                        id=uid(),
                        session_id=sess.id,
                        title=tc_title,
                        steps=f"1) Acceder al módulo de {t.title}. 2) Ejecutar acción principal. 3) Verificar persistencia y trazas.",
                        expected_result="Resultado funcional correcto, sin errores y con datos consistentes.",
                        actual_result="Ejecución correcta." if tc_status in ["passed", "skipped"] else "Se observan incidencias funcionales en validaciones de negocio.",
                        status=tc_status,
                        notes="Caso seed para validación de regresión UAT",
                        order=i,
                        tested_at=datetime.now() if tc_status in ["passed", "failed", "skipped"] else None,
                    ))
                    created_uat_test_cases += 1

                # Issues for failed/conditional sessions
                failed_like = sess.client_result in [PortalUATStatus.failed, PortalUATStatus.conditional]
                if failed_like:
                    for i in range(1, 3):
                        issue_title = f"SEED ISSUE {sess.code}-{i:02d}"
                        if db.query(UATIssue).filter(UATIssue.session_id == sess.id, UATIssue.title == issue_title).first():
                            continue
                        db.add(UATIssue(
                            id=uid(),
                            session_id=sess.id,
                            title=issue_title,
                            description="Defecto detectado en pruebas UAT con impacto funcional.",
                            severity=random.choice(["medium", "high", "blocker"]),
                            status=random.choice(["open", "open", "fixed", "deferred"]),
                            reported_by=sess.client_signed_by,
                            steps_to_reproduce="1) Login 2) Navegar a módulo 3) Ejecutar acción 4) Comprobar error",
                        ))
                        created_uat_issues += 1

        db.commit()
        print(f"   ✓ {created_client_users} client_users, {created_uat_sessions} sesiones UAT portal, {created_uat_test_cases} test cases, {created_uat_issues} incidencias UAT")

        # ── 15. Problem Management + enlaces incidente→problema ─────────────
        print("\n[15/15] Creando problemas y enlazando incidentes...")
        created_problems = 0
        created_incident_links = 0

        all_problem_numbers = [x.number for x in db.query(Problem.number).all()]
        problem_counter = next_counter_from_codes(all_problem_numbers, "PRB-", floor=199)

        incident_tickets = db.query(Ticket).filter(Ticket.ticket_type == TicketType.incident).all()
        if incident_tickets:
            # Group by rough topic to keep coherence
            topics = [
                ("Autenticación", "Fallos recurrentes de autenticación y bloqueo de sesiones", "software"),
                ("Rendimiento API", "Latencia y timeouts en operaciones críticas", "network"),
                ("Facturación", "Errores intermitentes en generación de facturas", "process"),
                ("Integraciones", "Inestabilidad en conectores externos", "software"),
                ("Infraestructura", "Incidencias de capacidad y disponibilidad", "hardware"),
                ("Notificaciones", "Entrega inconsistente de emails/notificaciones", "software"),
            ]

            random.shuffle(incident_tickets)
            chunk_size = max(2, min(5, len(incident_tickets) // len(topics) if len(incident_tickets) >= len(topics) else 2))
            idx = 0

            for topic, desc, rca_type in topics:
                num = f"PRB-{problem_counter:04d}"
                problem_counter += 1

                pb = db.query(Problem).filter(Problem.number == num).first()
                if not pb:
                    pb = Problem(
                        id=uid(),
                        number=num,
                        title=f"SEED Problem {topic}",
                        description=f"Problema raíz identificado: {desc}",
                        status=random.choice([ProblemStatus.investigating, ProblemStatus.known_error, ProblemStatus.resolved]),
                        priority=random.choice([TicketPriority.p1_critical, TicketPriority.p2_high, TicketPriority.p3_medium]),
                        root_cause=f"Causa raíz preliminar en dominio {topic.lower()}.",
                        workaround="Reintento controlado + monitorización reforzada.",
                        fix_description="Aplicar parche progresivo y validación de regresión automatizada.",
                        rca_type=rca_type,
                        rca_template="five_whys",
                        auto_detected=random.choice([True, False]),
                        owner_user_id=random.choice(agent_ids) if agent_ids else None,
                        project_id=random.choice(list(project_map.values())),
                        resolved_at=datetime.now() if random.random() > 0.6 else None,
                    )
                    db.add(pb)
                    db.flush()
                    created_problems += 1

                linked_slice = incident_tickets[idx: idx + chunk_size]
                idx += chunk_size
                if not linked_slice:
                    linked_slice = random.sample(incident_tickets, k=min(3, len(incident_tickets)))

                for j, tic in enumerate(linked_slice):
                    # Keep the direct FK in sync
                    if tic.problem_id != pb.id:
                        tic.problem_id = pb.id

                    if db.query(IncidentToProblem).filter(
                        IncidentToProblem.problem_id == pb.id,
                        IncidentToProblem.ticket_id == tic.id,
                    ).first():
                        continue

                    db.add(IncidentToProblem(
                        id=uid(),
                        problem_id=pb.id,
                        ticket_id=tic.id,
                        is_causal=(j == 0),
                        notes=f"Incidente relacionado al problema {pb.number}",
                        linked_by=random.choice(agent_ids) if agent_ids else None,
                    ))
                    created_incident_links += 1

        db.commit()
        print(f"   ✓ {created_problems} problemas creados, {created_incident_links} enlaces incidente→problema")

        # ── 16. Cobertura total por cliente/proyecto (últimos 2 años) ──────
        print("\n[16/19] Asegurando cobertura total por cliente/proyecto...")
        created_projects_for_clients = 0
        added_project_members = 0
        added_project_imputations = 0
        added_project_expenses = 0
        added_project_tickets = 0
        added_project_sprints = 0
        added_project_epics = 0
        added_project_milestones = 0
        added_project_deliverables = 0

        all_projects = db.query(Project).all()
        all_project_ids = [p.id for p in all_projects]
        all_project_codes = [p.code for p in all_projects]
        all_clients = db.query(Client).all()
        all_exp_codes = [x.code for x in db.query(Expense.code).all()]
        global_exp_counter = next_counter_from_codes(all_exp_codes, "EXP-", floor=999)
        all_del_codes = [x.code for x in db.query(Deliverable.code).all()]
        global_del_counter = next_counter_from_codes(all_del_codes, "DEL-SD-", floor=999)
        max_tick_row = db.execute(
            __import__("sqlalchemy").text(
                "SELECT MAX(CAST(REPLACE(number,'INC-','') AS INTEGER)) FROM sd_tickets WHERE number LIKE 'INC-%'"
            )
        ).scalar()
        global_ticket_counter = max(int(max_tick_row or 0), 999) + 1

        # 16.1 Ensure every client has at least one project
        for cli in all_clients:
            has_project = db.query(Project.id).filter(Project.client_id == cli.id).first() is not None
            if has_project:
                continue

            base_code = f"PRJ-CL-{cli.short_name or cli.name[:8]}".upper().replace(" ", "")
            code = base_code
            suffix = 1
            while code in all_project_codes or db.query(Project.id).filter(Project.code == code).first():
                code = f"{base_code}-{suffix}"
                suffix += 1

            pm = db.query(User).filter(User.role.in_([UserRole.pm, UserRole.admin])).order_by(User.created_at.asc()).first()
            p = Project(
                id=uid(),
                code=code,
                name=f"SEED Proyecto Cliente {cli.short_name or cli.name}",
                description="Proyecto generado para asegurar cobertura integral por cliente.",
                project_type=ProjectType.consulting,
                status=ProjectStatus.active,
                risk_level=ProjectRisk.medium,
                client_id=cli.id,
                client_name=cli.short_name or cli.name,
                billing_type="time_material",
                billing_rate=85.0,
                budget_hours=600,
                is_billable=True,
                start_date=TWO_YEARS_AGO,
                end_date_planned=TODAY + timedelta(days=180),
                pm_id=(pm.id if pm else None),
                currency="EUR",
                tags="seed,cobertura,cliente",
            )
            db.add(p)
            db.flush()
            all_project_ids.append(p.id)
            all_project_codes.append(p.code)
            project_map[p.code] = p.id
            created_projects_for_clients += 1

            for i, pname in enumerate(["Inicio", "Ejecución", "Cierre"], start=1):
                db.add(ProjectPhase(id=uid(), project_id=p.id, name=pname, order=i))

        db.commit()
        all_projects = db.query(Project).all()

        # Candidate users for assignments/memberships
        all_users = db.query(User).filter(User.is_active.is_(True)).all()
        all_user_ids = [u.id for u in all_users]
        user_ids_by_username = {u.username: u.id for u in all_users}

        # 16.2 Ensure each project has members, imputations, expenses, tickets,
        # sprints, epics, milestones, deliverables.
        for proj in all_projects:
            # Members
            existing_member_user_ids = {
                m.user_id
                for m in db.query(ProjectMember.user_id).filter(ProjectMember.project_id == proj.id).all()
            }
            target_member_count = min(8, max(4, len(all_user_ids) // 6 if all_user_ids else 0))
            if target_member_count > 0:
                candidate_user_ids = [uid_val for uid_val in all_user_ids if uid_val not in existing_member_user_ids]
                random.shuffle(candidate_user_ids)
                for uid_val in candidate_user_ids[: max(0, target_member_count - len(existing_member_user_ids))]:
                    db.add(ProjectMember(
                        id=uid(),
                        project_id=proj.id,
                        user_id=uid_val,
                        role=random.choice([
                            ProjectMemberRole.developer,
                            ProjectMemberRole.qa,
                            ProjectMemberRole.analyst,
                            ProjectMemberRole.devops,
                            ProjectMemberRole.designer,
                        ]),
                        allocation_pct=random.choice([25, 50, 75, 100]),
                    ))
                    added_project_members += 1

            # Load project tasks for links
            p_tasks = db.query(Task).filter(Task.project_id == proj.id).all()

            # Imputations (minimum per project over last 2 years)
            current_imp_count = db.query(Imputation).filter(Imputation.project_id == proj.id).count()
            target_imp_count = 60
            if current_imp_count < target_imp_count and all_user_ids:
                assigned_user_ids = list(existing_member_user_ids) or random.sample(all_user_ids, k=min(4, len(all_user_ids)))
                existing_keys = {
                    (row.user_id, row.task_id, row.date)
                    for row in db.query(Imputation.user_id, Imputation.task_id, Imputation.date)
                    .filter(Imputation.project_id == proj.id)
                    .all()
                }
                needed = target_imp_count - current_imp_count
                created_for_project = 0
                attempts = 0
                max_attempts = max(needed * 30, 120)
                while created_for_project < needed and attempts < max_attempts:
                    attempts += 1
                    imp_user = random.choice(assigned_user_ids)
                    imp_day = random_date(max(TWO_YEARS_AGO, proj.start_date or TWO_YEARS_AGO), TODAY)
                    imp_task_id = random.choice(p_tasks).id if p_tasks else None
                    key = (imp_user, imp_task_id, imp_day)
                    if key in existing_keys:
                        continue

                    hours = round(random.uniform(1.0, 7.5), 1)
                    db.add(Imputation(
                        id=uid(),
                        user_id=imp_user,
                        project_id=proj.id,
                        task_id=imp_task_id,
                        date=imp_day,
                        hours=hours,
                        hourly_rate_snapshot=random.uniform(45, 110),
                        cost_amount=round(hours * random.uniform(45, 110), 2),
                        is_billable=bool(proj.is_billable),
                        is_approved=imp_day < TODAY - timedelta(days=20),
                        description=f"SEED trabajo intensivo en {proj.code}",
                    ))
                    existing_keys.add(key)
                    created_for_project += 1
                    added_project_imputations += 1

            # Expenses
            current_exp_count = db.query(Expense).filter(Expense.project_id == proj.id).count()
            target_exp_count = 6
            if current_exp_count < target_exp_count and all_user_ids:
                for _ in range(target_exp_count - current_exp_count):
                    cat = random.choice(list(ExpenseCategory))
                    desc = random.choice(EXPENSE_DESCRIPTIONS.get(cat.value, ["Gasto operativo"]))
                    db.add(Expense(
                        id=uid(),
                        code=f"EXP-{global_exp_counter:04d}",
                        user_id=random.choice(all_user_ids),
                        project_id=proj.id,
                        category=cat,
                        description=f"SEED {desc}",
                        amount=round(random.uniform(40, 1600), 2),
                        currency="EUR",
                        expense_date=random_date(TWO_YEARS_AGO, TODAY),
                        is_billable=bool(proj.is_billable),
                        status=random.choice([
                            ExpenseStatus.approved,
                            ExpenseStatus.submitted,
                            ExpenseStatus.reimbursed,
                        ]),
                    ))
                    global_exp_counter += 1
                    added_project_expenses += 1

            # Tickets per project
            current_proj_tickets = db.query(Ticket).filter(Ticket.project_id == proj.id).count()
            target_proj_tickets = 8
            if current_proj_tickets < target_proj_tickets and all_user_ids:
                for _ in range(target_proj_tickets - current_proj_tickets):
                    t_day = random_date(TWO_YEARS_AGO, TODAY)
                    status_choices = [
                        TicketStatus.new,
                        TicketStatus.in_progress,
                        TicketStatus.pending_client,
                        TicketStatus.resolved,
                        TicketStatus.closed,
                    ]
                    t_status = random.choice(status_choices)
                    resolved_at = None
                    first_response_at = None
                    fr_minutes = None
                    res_minutes = None
                    if t_status in (TicketStatus.resolved, TicketStatus.closed):
                        fr_minutes = random.randint(10, 240)
                        res_minutes = random.randint(60, 2880)
                        first_response_at = datetime.combine(t_day, datetime.min.time()) + timedelta(minutes=fr_minutes)
                        resolved_at = datetime.combine(t_day, datetime.min.time()) + timedelta(minutes=res_minutes)

                    db.add(Ticket(
                        id=uid(),
                        number=f"INC-{global_ticket_counter:04d}",
                        ticket_type=random.choice([TicketType.incident, TicketType.service_request, TicketType.change]),
                        title=f"SEED {proj.code}: {random.choice(TICKET_TITLES_INCIDENTS + TICKET_TITLES_REQUESTS)}",
                        description=f"Ticket generado para cobertura total del proyecto {proj.code}.",
                        status=t_status,
                        priority=random.choice(list(TicketPriority)),
                        urgency=random.choice(list(TicketUrgency)),
                        impact=random.choice(list(TicketImpact)),
                        requester_user_id=random.choice(all_user_ids),
                        assigned_to_user_id=random.choice(all_user_ids),
                        project_id=proj.id,
                        client_id=proj.client_id,
                        source=random.choice(["portal", "email", "phone", "chat"]),
                        first_response_at=first_response_at,
                        resolved_at=resolved_at,
                        first_response_minutes=fr_minutes,
                        resolution_minutes=res_minutes,
                        sla_response_breached=(fr_minutes is not None and fr_minutes > 240),
                        sla_resolution_breached=(res_minutes is not None and res_minutes > 1440),
                        time_spent_minutes=res_minutes if res_minutes else random.randint(15, 300),
                        tags=f"seed,{proj.code.lower()},workload",
                    ))
                    global_ticket_counter += 1
                    added_project_tickets += 1

            # Sprints (at least 4 per project)
            current_sprint_count = db.query(Sprint).filter(Sprint.project_id == proj.id).count()
            if current_sprint_count < 4:
                start = max(TWO_YEARS_AGO, proj.start_date or TWO_YEARS_AGO)
                for num in range(current_sprint_count + 1, 5):
                    sd = start + timedelta(days=(num - 1) * 14)
                    ed = sd + timedelta(days=13)
                    if db.query(Sprint.id).filter(Sprint.project_id == proj.id, Sprint.number == num).first():
                        continue
                    spr = Sprint(
                        id=uid(),
                        project_id=proj.id,
                        number=num,
                        name=f"SEED Sprint {num:02d} {proj.code}",
                        goal=f"Incremento funcional de {proj.code}",
                        status=SprintStatus.completed if ed < TODAY else SprintStatus.active,
                        start_date=sd,
                        end_date=ed,
                        planned_points=float(random.randint(16, 40)),
                        completed_points=float(random.randint(12, 36)),
                        velocity=float(round(random.uniform(9.0, 26.0), 1)),
                        created_by=proj.pm_id,
                    )
                    db.add(spr)
                    db.flush()
                    added_project_sprints += 1
                    if p_tasks:
                        selected_tasks = random.sample(p_tasks, k=min(5, len(p_tasks)))
                        for order_idx, t in enumerate(selected_tasks, start=1):
                            if db.query(SprintTask.id).filter(SprintTask.sprint_id == spr.id, SprintTask.task_id == t.id).first():
                                continue
                            db.add(SprintTask(id=uid(), sprint_id=spr.id, task_id=t.id, backlog_order=order_idx))

            # Epics (at least 2 per project)
            current_epic_count = db.query(Epic).filter(Epic.project_id == proj.id).count()
            if current_epic_count < 2:
                for idx in range(current_epic_count + 1, 3):
                    title = f"SEED Epic Cobertura {proj.code}-{idx:02d}"
                    if db.query(Epic.id).filter(Epic.project_id == proj.id, Epic.title == title).first():
                        continue
                    epic = Epic(
                        id=uid(),
                        project_id=proj.id,
                        title=title,
                        description=f"Épica generada para cobertura integral del proyecto {proj.code}.",
                        color=random.choice(["#2563eb", "#16a34a", "#f97316", "#a855f7"]),
                        status=random.choice(["open", "in_progress", "done"]),
                        priority=random.choice(["medium", "high", "critical"]),
                        start_date=(proj.start_date or TWO_YEARS_AGO).isoformat(),
                        end_date=((proj.start_date or TWO_YEARS_AGO) + timedelta(days=120)).isoformat(),
                        sort_order=idx,
                        created_by=proj.pm_id,
                    )
                    db.add(epic)
                    db.flush()
                    added_project_epics += 1
                    if p_tasks:
                        for t in random.sample(p_tasks, k=min(4, len(p_tasks))):
                            if db.query(EpicTask.id).filter(EpicTask.epic_id == epic.id, EpicTask.task_id == t.id).first():
                                continue
                            db.add(EpicTask(id=uid(), epic_id=epic.id, task_id=t.id))

            # Milestones + Deliverables (at least 3 per project)
            current_milestones = db.query(ProjectMilestone).filter(ProjectMilestone.project_id == proj.id).count()
            milestone_target = 3
            if current_milestones < milestone_target:
                for idx in range(current_milestones + 1, milestone_target + 1):
                    m_name = f"SEED-MILESTONE-COVER {proj.code}-{idx:02d}"
                    if db.query(ProjectMilestone.id).filter(ProjectMilestone.project_id == proj.id, ProjectMilestone.name == m_name).first():
                        continue
                    due = max(TWO_YEARS_AGO, proj.start_date or TWO_YEARS_AGO) + timedelta(days=60 * idx)
                    ms = ProjectMilestone(
                        id=uid(),
                        project_id=proj.id,
                        name=m_name,
                        description=f"Hito de cobertura integral {idx} para {proj.code}",
                        due_date=due,
                        sort_order=idx,
                        billing_status=random.choice(["completed", "approved", "pending_approval", "pending"]),
                        is_completed=idx <= 2,
                        completed_date=due if idx <= 2 else None,
                        completed_by=proj.pm_id,
                        billing_amount=float(random.randint(8000, 40000)),
                        billing_pct=float(random.choice([20, 25, 30, 40])),
                    )
                    db.add(ms)
                    db.flush()
                    added_project_milestones += 1

                    d_name = f"SEED Deliverable Cover {proj.code}-{idx:02d}"
                    if not db.query(Deliverable.id).filter(Deliverable.project_id == proj.id, Deliverable.name == d_name).first():
                        owner_id = random.choice(list(existing_member_user_ids) or all_user_ids)
                        db.add(Deliverable(
                            id=uid(),
                            code=f"DEL-SD-{global_del_counter:04d}",
                            project_id=proj.id,
                            name=d_name,
                            description=f"Entregable completo para {proj.code}",
                            format=random.choice(DELIVERABLE_FORMATS),
                            status=random.choice(list(DeliverableStatus)),
                            planned_date=due,
                            delivered_date=due if idx <= 2 else None,
                            accepted_date=due + timedelta(days=3) if idx == 1 else None,
                            owner_id=owner_id,
                            client_contact=proj.client_name,
                            acceptance_criteria="Cumplir QA, seguridad, rendimiento y aceptación funcional.",
                            milestone_id=ms.id,
                            sort_order=idx,
                        ))
                        global_del_counter += 1
                        added_project_deliverables += 1

        db.commit()
        print(
            f"   ✓ Proyectos nuevos para clientes: {created_projects_for_clients}; "
            f"miembros: {added_project_members}; imputaciones: {added_project_imputations}; "
            f"gastos: {added_project_expenses}; tickets: {added_project_tickets}; "
            f"sprints: {added_project_sprints}; épicas: {added_project_epics}; "
            f"milestones: {added_project_milestones}; entregables: {added_project_deliverables}"
        )

        # ── 17. Documentación completa por proyecto ─────────────────────────
        print("\n[17/19] Generando documentos/versiones/permisos/tags/accesos por proyecto...")
        created_documents = 0
        created_doc_versions = 0
        created_doc_permissions = 0
        created_doc_tags = 0
        created_doc_access_logs = 0

        all_projects = db.query(Project).all()
        for proj in all_projects:
            p_tasks = db.query(Task).filter(Task.project_id == proj.id).all()
            p_tickets = db.query(Ticket).filter(Ticket.project_id == proj.id).all()
            p_milestones = db.query(ProjectMilestone).filter(ProjectMilestone.project_id == proj.id).all()
            project_member_user_ids = [
                x.user_id for x in db.query(ProjectMember.user_id).filter(ProjectMember.project_id == proj.id).all()
            ]
            if not project_member_user_ids and all_user_ids:
                project_member_user_ids = random.sample(all_user_ids, k=min(4, len(all_user_ids)))

            for idx in range(1, 4):
                d_title = f"SEED DOC {proj.code}-{idx:02d}"
                doc = db.query(Document).filter(Document.project_id == proj.id, Document.title == d_title).first()
                if not doc:
                    creator_id = random.choice(project_member_user_ids) if project_member_user_ids else None
                    if creator_id is None:
                        continue
                    doc = Document(
                        id=uid(),
                        title=d_title,
                        description=f"Documento integral del proyecto {proj.code}",
                        category=random.choice([
                            DocumentCategory.requirements,
                            DocumentCategory.deliverable,
                            DocumentCategory.meeting_notes,
                            DocumentCategory.contract,
                        ]),
                        project_id=proj.id,
                        client_id=proj.client_id,
                        milestone_id=random.choice(p_milestones).id if p_milestones else None,
                        task_id=random.choice(p_tasks).id if p_tasks else None,
                        ticket_id=random.choice(p_tickets).id if p_tickets else None,
                        requires_approval=bool(random.choice([True, False])),
                        approval_status=random.choice(list(ApprovalStatus)),
                        approved_by=random.choice(project_member_user_ids) if project_member_user_ids and random.random() > 0.4 else None,
                        approved_at=random_datetime(TWO_YEARS_AGO, TODAY) if random.random() > 0.5 else None,
                        is_archived=False,
                        created_by=creator_id,
                        updated_by=creator_id,
                    )
                    db.add(doc)
                    db.flush()
                    created_documents += 1

                # Versions (2 minimum)
                existing_versions = db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id).count()
                if existing_versions < 2:
                    uploader = random.choice(project_member_user_ids) if project_member_user_ids else None
                    if uploader is not None:
                        for vnum in range(existing_versions + 1, 3):
                            db.add(DocumentVersion(
                                id=uid(),
                                document_id=doc.id,
                                version_num=vnum,
                                file_key=f"seed/{proj.code.lower()}/{doc.id}/v{vnum}.pdf",
                                file_name=f"{doc.title.replace(' ', '_').lower()}_v{vnum}.pdf",
                                file_size=random.randint(120_000, 2_400_000),
                                file_mime_type="application/pdf",
                                change_note=f"SEED revisión {vnum} para {proj.code}",
                                created_by=uploader,
                                created_at=random_datetime(TWO_YEARS_AGO, TODAY),
                            ))
                            created_doc_versions += 1

                # Permissions
                for uid_val in random.sample(project_member_user_ids, k=min(3, len(project_member_user_ids))):
                    if db.query(DocumentPermission).filter(DocumentPermission.document_id == doc.id, DocumentPermission.user_id == uid_val).first():
                        continue
                    db.add(DocumentPermission(
                        id=uid(),
                        document_id=doc.id,
                        user_id=uid_val,
                        access_level=random.choice(list(DocumentAccessLevel)),
                        granted_by=doc.created_by,
                        granted_at=random_datetime(TWO_YEARS_AGO, TODAY),
                    ))
                    created_doc_permissions += 1

                # Tags
                for tg in ["seed", proj.code.lower(), random.choice(["qa", "delivery", "tech", "contract", "meeting"] )]:
                    if db.query(DocumentTag).filter(DocumentTag.document_id == doc.id, DocumentTag.tag_name == tg).first():
                        continue
                    db.add(DocumentTag(id=uid(), document_id=doc.id, tag_name=tg))
                    created_doc_tags += 1

                # Access logs
                current_logs = db.query(DocumentAccessLog).filter(DocumentAccessLog.document_id == doc.id).count()
                if current_logs < 4 and project_member_user_ids:
                    for _ in range(4 - current_logs):
                        db.add(DocumentAccessLog(
                            id=uid(),
                            document_id=doc.id,
                            user_id=random.choice(project_member_user_ids),
                            action=random.choice(["view", "download"]),
                            accessed_at=random_datetime(TWO_YEARS_AGO, TODAY),
                            ip_address=f"10.0.{random.randint(0,254)}.{random.randint(1,254)}",
                        ))
                        created_doc_access_logs += 1

        db.commit()
        print(
            f"   ✓ documentos: {created_documents}, versiones: {created_doc_versions}, "
            f"permisos: {created_doc_permissions}, tags: {created_doc_tags}, accesos: {created_doc_access_logs}"
        )

        # ── 18. Cobertura de personas: OKRs + revisiones ────────────────────
        print("\n[18/19] Generando OKRs y revisiones para todas las personas...")
        created_objectives = 0
        created_key_results = 0
        created_kr_checkins = 0
        created_review_cycles = 0
        created_reviews = 0

        all_users = db.query(User).filter(User.is_active.is_(True)).all()
        all_projects = db.query(Project).all()
        all_project_ids = [p.id for p in all_projects]

        # Seed review cycles for the last two years
        cycle_names = [
            ("SEED Review Cycle 2025", date(2025, 1, 1), date(2025, 12, 31), ReviewCycleStatus.closed),
            ("SEED Review Cycle 2026", date(2026, 1, 1), date(2026, 12, 31), ReviewCycleStatus.active),
        ]
        cycle_objs = []
        admin_or_hr = db.query(User).filter(User.role.in_([UserRole.admin, UserRole.hr])).first()
        creator_id = admin_or_hr.id if admin_or_hr else (all_users[0].id if all_users else None)
        for nm, sd, ed, st in cycle_names:
            cycle = db.query(ReviewCycle).filter(ReviewCycle.name == nm).first()
            if not cycle:
                cycle = ReviewCycle(
                    id=uid(),
                    name=nm,
                    description="Ciclo de evaluación generado automáticamente para carga realista.",
                    start_date=sd,
                    end_date=ed,
                    status=st,
                    include_self=True,
                    include_peers=True,
                    include_manager=True,
                    created_by=creator_id,
                )
                db.add(cycle)
                db.flush()
                created_review_cycles += 1
            cycle_objs.append(cycle)

        # OKRs + KRs + checkins per person
        for idx, usr in enumerate(all_users):
            p_id = all_project_ids[idx % len(all_project_ids)] if all_project_ids else None
            title = f"SEED OKR {usr.username} {TODAY.year}"
            obj = db.query(Objective).filter(Objective.title == title, Objective.owner_id == usr.id).first()
            if not obj:
                obj = Objective(
                    id=uid(),
                    title=title,
                    description=f"Objetivo anual de desempeño y entrega para {usr.full_name}",
                    owner_id=usr.id,
                    team_id=usr.department,
                    project_id=p_id,
                    period=random.choice(list(OKRPeriod)),
                    year=TODAY.year,
                    status=random.choice([OKRStatus.active, OKRStatus.completed]),
                    progress=random.uniform(20.0, 100.0),
                )
                db.add(obj)
                db.flush()
                created_objectives += 1

            existing_krs = db.query(KeyResult).filter(KeyResult.objective_id == obj.id).count()
            if existing_krs < 2:
                for kidx in range(existing_krs + 1, 3):
                    kr = KeyResult(
                        id=uid(),
                        objective_id=obj.id,
                        title=f"SEED KR {usr.username}-{kidx}",
                        kr_type=random.choice(list(KRType)),
                        target_value=random.choice([100, 10, 1, 50000]),
                        current_value=random.choice([35, 60, 85, 100]),
                        unit=random.choice(["%", "items", "EUR", "bool"]),
                        owner_id=usr.id,
                        due_date=TODAY,
                        progress=random.uniform(15, 100),
                        notes="KR generado para reflejar actividad continua.",
                    )
                    db.add(kr)
                    db.flush()
                    created_key_results += 1

                    checkins = db.query(KRCheckin).filter(KRCheckin.kr_id == kr.id).count()
                    for cidx in range(checkins + 1, 4):
                        db.add(KRCheckin(
                            id=uid(),
                            kr_id=kr.id,
                            value=float(random.randint(10, 100)),
                            note=f"SEED check-in {cidx} para {usr.username}",
                            author_id=usr.id,
                            created_at=random_datetime(TWO_YEARS_AGO, TODAY),
                        ))
                        created_kr_checkins += 1

            # Performance reviews: self + peer per cycle
            peers = [u for u in all_users if u.id != usr.id]
            peer = random.choice(peers) if peers else usr
            for cyc in cycle_objs:
                specs = [
                    (usr.id, usr.id, "self"),
                    (usr.id, peer.id, "peer"),
                ]
                for reviewee_id, reviewer_id, review_type in specs:
                    rv = db.query(PerformanceReview).filter(
                        PerformanceReview.cycle_id == cyc.id,
                        PerformanceReview.reviewee_id == reviewee_id,
                        PerformanceReview.reviewer_id == reviewer_id,
                        PerformanceReview.review_type == review_type,
                    ).first()
                    if rv:
                        continue
                    score_base = random.uniform(3.0, 4.9)
                    submitted = random_datetime(TWO_YEARS_AGO, TODAY)
                    db.add(PerformanceReview(
                        id=uid(),
                        cycle_id=cyc.id,
                        reviewee_id=reviewee_id,
                        reviewer_id=reviewer_id,
                        review_type=review_type,
                        status=random.choice([ReviewStatus.submitted, ReviewStatus.approved]),
                        score_quality=round(score_base, 1),
                        score_delivery=round(min(5.0, score_base + random.uniform(-0.3, 0.3)), 1),
                        score_teamwork=round(min(5.0, score_base + random.uniform(-0.4, 0.4)), 1),
                        score_leadership=round(min(5.0, score_base + random.uniform(-0.5, 0.5)), 1),
                        score_innovation=round(min(5.0, score_base + random.uniform(-0.4, 0.4)), 1),
                        score_overall=round(min(5.0, score_base + random.uniform(-0.2, 0.2)), 1),
                        strengths="Entrega consistente y buena colaboración inter-áreas.",
                        improvements="Mejorar documentación de decisiones y seguimiento de riesgos.",
                        goals_next="Incrementar automatización y reducir lead time en entregas.",
                        submitted_at=submitted,
                        created_at=submitted,
                    ))
                    created_reviews += 1

        db.commit()
        print(
            f"   ✓ objetivos: {created_objectives}, KRs: {created_key_results}, "
            f"check-ins: {created_kr_checkins}, ciclos review: {created_review_cycles}, reviews: {created_reviews}"
        )

        # ── 19. Menciones y mensajes threaded para todas las personas ───────
        print("\n[19/19] Generando menciones y mensajes threaded para todas las personas...")
        created_mentions = 0
        created_threaded_comments = 0

        all_users = db.query(User).filter(User.is_active.is_(True)).all()
        all_tasks = db.query(Task).all()
        all_tickets = db.query(Ticket).all()
        if all_users and (all_tasks or all_tickets):
            for idx, usr in enumerate(all_users):
                peers = [u for u in all_users if u.id != usr.id]
                if not peers:
                    continue

                # Mentions received by this user
                for m_idx in range(1, 3):
                    by_user = random.choice(peers)
                    is_task = bool(all_tasks) and (not all_tickets or random.random() > 0.4)
                    entity_type = "task" if is_task else "ticket"
                    entity_id = random.choice(all_tasks).id if is_task else random.choice(all_tickets).id
                    context = f"SEED mention @{usr.email} en {entity_type} (iter {m_idx})"
                    if db.query(Mention.id).filter(
                        Mention.mentioned_user == usr.id,
                        Mention.mentioned_by == by_user.id,
                        Mention.entity_type == entity_type,
                        Mention.entity_id == entity_id,
                        Mention.context_text == context,
                    ).first():
                        continue
                    db.add(Mention(
                        id=uid(),
                        mentioned_user=usr.id,
                        mentioned_by=by_user.id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        context_text=context,
                        is_read=random.choice([True, False]),
                        created_at=random_datetime(TWO_YEARS_AGO, TODAY),
                    ))
                    created_mentions += 1

                # Threaded comments as conversational messages
                for c_idx in range(1, 3):
                    is_task = bool(all_tasks) and (not all_tickets or random.random() > 0.4)
                    entity_type = "task" if is_task else "ticket"
                    entity_id = random.choice(all_tasks).id if is_task else random.choice(all_tickets).id
                    root_content = f"SEED MSG root {usr.username} #{c_idx}: avance, bloqueo y próximos pasos."
                    root = db.query(ThreadedComment).filter(
                        ThreadedComment.entity_type == entity_type,
                        ThreadedComment.entity_id == entity_id,
                        ThreadedComment.parent_id.is_(None),
                        ThreadedComment.created_by == usr.id,
                        ThreadedComment.content == root_content,
                    ).first()
                    if not root:
                        root = ThreadedComment(
                            id=uid(),
                            entity_type=entity_type,
                            entity_id=entity_id,
                            parent_id=None,
                            content=root_content,
                            is_resolved=False,
                            created_by=usr.id,
                            created_at=random_datetime(TWO_YEARS_AGO, TODAY),
                        )
                        db.add(root)
                        db.flush()
                        created_threaded_comments += 1

                    # one reply from peer
                    rep_user = random.choice(peers)
                    rep_content = f"SEED MSG reply {rep_user.username}: revisado, propongo ajustar prioridad."
                    if not db.query(ThreadedComment.id).filter(
                        ThreadedComment.parent_id == root.id,
                        ThreadedComment.created_by == rep_user.id,
                        ThreadedComment.content == rep_content,
                    ).first():
                        db.add(ThreadedComment(
                            id=uid(),
                            entity_type=entity_type,
                            entity_id=entity_id,
                            parent_id=root.id,
                            content=rep_content,
                            is_resolved=random.choice([False, True]),
                            created_by=rep_user.id,
                            created_at=random_datetime(TWO_YEARS_AGO, TODAY),
                        ))
                        created_threaded_comments += 1

        db.commit()
        print(f"   ✓ menciones: {created_mentions}, mensajes threaded: {created_threaded_comments}")

        # ── Resumen ───────────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("  SEED COMPLETADO")
        print("=" * 60)
        from app.models.imputation import Imputation as Imp
        total_imp = db.query(Imp).count()
        total_tasks = db.query(Task).count()
        total_tickets = db.query(Ticket).count()
        total_inv = db.query(Invoice).count()
        total_exp = db.query(Expense).count()
        total_abs = db.query(Absence).count()
        total_sprints = db.query(Sprint).count()
        total_epics = db.query(Epic).count()
        total_deliverables = db.query(Deliverable).count()
        total_milestones = db.query(ProjectMilestone).count()
        total_uat_cases = db.query(UATCase).count()
        total_uat_sessions = db.query(UATSession).count()
        total_uat_issues = db.query(UATIssue).count()
        total_problems = db.query(Problem).count()
        total_incident_links = db.query(IncidentToProblem).count()
        total_client_users = db.query(ClientUser).count()
        total_documents = db.query(Document).count()
        total_document_versions = db.query(DocumentVersion).count()
        total_mentions = db.query(Mention).count()
        total_threaded_comments = db.query(ThreadedComment).count()
        total_objectives = db.query(Objective).count()
        total_key_results = db.query(KeyResult).count()
        total_kr_checkins = db.query(KRCheckin).count()
        total_review_cycles = db.query(ReviewCycle).count()
        total_reviews = db.query(PerformanceReview).count()
        total_users = db.query(User).count()
        total_clients = db.query(Client).count()
        total_projects = db.query(Project).count()
        print(f"  Usuarios:       {total_users}")
        print(f"  Clientes:       {total_clients}")
        print(f"  Proyectos:      {total_projects}")
        print(f"  Tareas:         {total_tasks}")
        print(f"  Imputaciones:   {total_imp}")
        print(f"  Gastos:         {total_exp}")
        print(f"  Facturas:       {total_inv}")
        print(f"  Tickets:        {total_tickets}")
        print(f"  Problemas:      {total_problems}")
        print(f"  Inc→Problem:    {total_incident_links}")
        print(f"  Ausencias:      {total_abs}")
        print(f"  Sprints:        {total_sprints}")
        print(f"  Épicas:         {total_epics}")
        print(f"  Milestones:     {total_milestones}")
        print(f"  Entregables:    {total_deliverables}")
        print(f"  UAT Cases:      {total_uat_cases}")
        print(f"  UAT Sessions:   {total_uat_sessions}")
        print(f"  UAT Issues:     {total_uat_issues}")
        print(f"  Client Users:   {total_client_users}")
        print(f"  Documentos:     {total_documents}")
        print(f"  Doc Versions:   {total_document_versions}")
        print(f"  Menciones:      {total_mentions}")
        print(f"  Msg Threaded:   {total_threaded_comments}")
        print(f"  Objetivos OKR:  {total_objectives}")
        print(f"  Key Results:    {total_key_results}")
        print(f"  KR Check-ins:   {total_kr_checkins}")
        print(f"  Review Cycles:  {total_review_cycles}")
        print(f"  Reviews 360:    {total_reviews}")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
