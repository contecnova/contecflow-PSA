"""Enumeraciones de proveedores (una sola fuente; `/suppliers/meta` las sirve)."""
from __future__ import annotations

KINDS = ("freelance", "company")
MODES = ("staff_augmentation", "outsourcing", "managed_services")
LIFECYCLE = ("onboarding", "active", "suspended", "offboarded")
#: Estados en los que el proveedor no admite trabajo nuevo.
NO_ACTIVOS = ("suspended", "offboarded")

CONTRACT_TYPES = ("msa", "sow", "service", "framework", "freelance")
CONTRACT_STATUSES = ("draft", "active", "suspended", "expired", "terminated")
PRICING_MODELS = ("per_resource", "fixed_price", "per_unit", "subscription", "expense", "bonus")
PERIODS = ("monthly", "quarterly", "annual", "one_time")
MESES_DEL_PERIODO = {"monthly": 1, "quarterly": 3, "annual": 12}

SCOPE_TYPES = ("project", "phase", "milestone", "deliverable", "tasks")
WP_STATUSES = ("planned", "in_progress", "delivered", "accepted", "rejected", "cancelled")
WP_ABIERTOS = ("planned", "in_progress", "delivered", "rejected")
#: Transiciones permitidas del paquete de trabajo.
WP_TRANSICIONES = {
    "start": (("planned", "rejected"), "in_progress"),
    "deliver": (("in_progress", "rejected"), "delivered"),
    "accept": (("delivered",), "accepted"),
    "reject": (("delivered",), "rejected"),
    "cancel": (("planned", "in_progress", "delivered", "rejected"), "cancelled"),
}

DOCUMENT_TYPES = (
    "dpa_art28", "nda", "iso27001", "soc2", "ens", "insurance_liability", "insurance_cyber",
    "security_questionnaire", "due_diligence", "tax_certificate", "social_security_certificate", "other",
)
CERTIFICACIONES_DE_SEGURIDAD = ("iso27001", "soc2", "ens")
SEGUROS = ("insurance_liability", "insurance_cyber")
ACCESS_LEVELS = ("read", "write", "admin")

RISK_CRITERIA = ("data_access", "criticality", "dependency", "financial", "location", "security")
RISK_LEVELS = ("low", "medium", "high", "critical")

#: Unidades del sistema con medicion automatica (las demas: consumo registrado).
UNIDADES_HORAS = ("hour", "day", "month")
UNIDADES_TICKETS = ("ticket", "incident", "request")
UNIDADES_RECUENTO = ("device_month", "user_month")
AUTO_UNITS = UNIDADES_HORAS + UNIDADES_TICKETS + UNIDADES_RECUENTO

#: Migracion 191. Informes del proveedor: avance de paquete, periodico de
#: servicio, parte de servicio y evidencia de SLA (los tres ultimos, de un servicio).
REPORT_TYPES = ("progress", "periodic", "service_log", "sla_evidence")
REPORT_TYPES_DE_SERVICIO = ("periodic", "service_log", "sla_evidence")
#: Estados de cuenta (`pending_approval`: en la bandeja del motor de aprobaciones).
STATEMENT_STATUSES = ("closed", "reconciled", "pending_approval", "disputed", "approved")
#: Fuentes de medicion de dispositivos/usuarios de un servicio gestionado (`medicion`).
METERING_SOURCES = ("manual", "cmdb", "external")
#: Como se resume el recuento del mes: el ultimo, el maximo o la media de las muestras.
METERING_AGGREGATIONS = ("last", "max", "average")
#: Que cuenta la CMDB: elementos (dispositivos) o propietarios distintos (usuarios).
METERING_COUNTS = ("devices", "owners")
#: Tipo de la bandeja de aprobaciones para estados de cuenta (`approval_engine.fuentes`).
TIPO_DE_APROBACION = "supplier_statement"

DEFAULT_SERVICE_TYPES = [
    ("soc", "SOC / monitorización de seguridad", "#ec4899"),
    ("service_desk", "Service desk", "#00d4ff"),
    ("helpdesk_l1", "Soporte de primer nivel", "#38bdf8"),
    ("infrastructure", "Infraestructura", "#7c3aed"),
    ("network", "Redes y comunicaciones", "#2dd4bf"),
    ("cloud_ops", "Operación cloud", "#00e5a0"),
    ("backup", "Copias de seguridad", "#84cc16"),
    ("payroll", "Nóminas", "#ffb800"),
    ("development", "Desarrollo", "#f97316"),
    ("other", "Otro", "#7a8aaa"),
]

DEFAULT_BILLING_UNITS = [
    ("hour", "Hora", "#00d4ff"),
    ("day", "Día", "#38bdf8"),
    ("month", "Mes", "#7c3aed"),
    ("ticket", "Ticket", "#00e5a0"),
    ("incident", "Incidente", "#ec4899"),
    ("request", "Petición", "#2dd4bf"),
    ("device_month", "Dispositivo al mes", "#ffb800"),
    ("user_month", "Usuario al mes", "#f97316"),
    ("call", "Llamada", "#84cc16"),
    ("expense", "Gasto", "#7a8aaa"),
]


def meta() -> dict:
    return {
        "kinds": list(KINDS), "modes": list(MODES), "lifecycle": list(LIFECYCLE),
        "contract_types": list(CONTRACT_TYPES), "contract_statuses": list(CONTRACT_STATUSES),
        "pricing_models": list(PRICING_MODELS), "periods": list(PERIODS), "scope_types": list(SCOPE_TYPES),
        "work_package_statuses": list(WP_STATUSES), "document_types": list(DOCUMENT_TYPES),
        "access_levels": list(ACCESS_LEVELS), "risk_criteria": list(RISK_CRITERIA),
        "risk_levels": list(RISK_LEVELS), "auto_units": list(AUTO_UNITS),
        "report_types": list(REPORT_TYPES), "statement_statuses": list(STATEMENT_STATUSES),
        "metering_sources": list(METERING_SOURCES), "metering_aggregations": list(METERING_AGGREGATIONS),
        "metering_counts": list(METERING_COUNTS), "metered_units": list(UNIDADES_RECUENTO),
    }


def modos(sub) -> set:
    return set(getattr(sub, "engagement_modes", None) or [])
