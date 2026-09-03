"""Consultas analiticas ad-hoc, drilldown y filtrado cruzado.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `v238_service.py`, un
fichero de 784 lineas nombrado por NUMERO DE VERSION y con SEIS dominios sin
relacion dentro: etapas del embudo, planificacion de capacidad, analitica
ad-hoc, pagos, instantaneas de colaboracion y SCIM.

Agrupar por version en lugar de por dominio tiene un coste concreto: nadie sabe
donde buscar, y un fichero con seis dominios no tiene revisor natural — quien
entra a tocar los pagos no revisa la analitica que hay 300 lineas mas abajo. Fue
esa misma mala ubicacion la que oculto el P0 numero 1 de la auditoria, escondido
en un fichero llamado `mfa_service`.

El reparto se pudo hacer mecanicamente porque los seis dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

from datetime import date
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException
from app.models.billing_reports import Invoice
from app.models.imputation import Imputation
from app.models.service_desk import Ticket
from app.models.task import Task

_ADHOC_METRICS: dict = {
    "hours_logged": {
        "model": lambda: Imputation,
        "value_col": lambda m: m.hours,
        "agg": "sum",
        "date_col": lambda m: m.date,
        "value_key": "hours",
        "total_key": "total_hours",
        "dimensions": {
            "month": lambda m: m.date,
            "user_id": lambda m: m.user_id,
            "project_id": lambda m: m.project_id,
        },
        "filters": {
            "project_id": lambda m: m.project_id,
            "user_id": lambda m: m.user_id,
        },
    },
    "revenue": {
        "model": lambda: Invoice,
        "value_col": lambda m: m.total,
        "agg": "sum",
        "date_col": lambda m: m.issue_date,
        "value_key": "revenue",
        "total_key": "total_revenue",
        "base_filter": lambda m: m.status != "cancelled",
        "dimensions": {
            "month": lambda m: m.issue_date,
            "status": lambda m: m.status,
            "project_id": lambda m: m.project_id,
        },
        "filters": {
            "project_id": lambda m: m.project_id,
        },
    },
    "task_count": {
        "model": lambda: Task,
        "value_col": None,
        "agg": "count",
        "date_col": None,
        "value_key": "count",
        "total_key": "total_tasks",
        "dimensions": {
            "status": lambda m: m.status,
            "priority": lambda m: m.priority,
            "project_id": lambda m: m.project_id,
        },
        "filters": {
            "project_id": lambda m: m.project_id,
            "status": lambda m: m.status,
        },
    },
    "ticket_count": {
        "model": lambda: Ticket,
        "value_col": None,
        "agg": "count",
        "date_col": lambda m: m.created_at,
        "value_key": "count",
        "total_key": "total_tickets",
        "dimensions": {
            "status": lambda m: m.status,
            "priority": lambda m: m.priority,
        },
        "filters": {
            "status": lambda m: m.status,
        },
    },
}


def _coerce_date(value) -> Optional[date]:
    """Acepta date o cadena ISO. El endpoint recibe JSON, así que llegan cadenas.

    Antes la función se anotaba `Optional[date]` y comparaba directamente contra
    columnas de fecha; con una cadena la comparación no fallaba, simplemente no
    filtraba lo esperado.
    """
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise HTTPException(400, f"Fecha no válida: {value!r}. Usa formato ISO (YYYY-MM-DD).")


def _enum_str(value):
    return value.value if hasattr(value, "value") else (str(value) if value is not None else "unknown")


def run_adhoc_query(
    metric: str,
    dimensions: List[str],
    filters: dict,
    date_from=None,
    date_to=None,
    limit: int = 100,
    db: Session = None,
) -> dict:
    """Consulta analítica ad-hoc, agregada en SQL.

    Auditoría 2026-08 (hallazgo P1-9). La versión anterior tenía dos defectos:

    1. AGREGADOS SOBRE DATOS TRUNCADOS. Hacía `rows = q.limit(limit).all()` y
       después sumaba en Python. Con más filas que el límite, `total_hours` y
       `total_revenue` salían silenciosamente incompletos: cifras financieras
       erróneas sin ningún aviso, el peor modo de fallo posible en un PSA. Ahora
       se agrega con GROUP BY en la base de datos y el `limit` se aplica al
       resultado agrupado, que es lo que significaba.

    2. Traía todas las filas a memoria para contarlas. Con un histórico grande
       eso es un problema de rendimiento por sí solo.

    El agrupado por mes usa `extract`, que SQLAlchemy compila tanto para
    PostgreSQL como para SQLite; el código original usaba `func.strftime`, que es
    exclusivo de SQLite y habría fallado en producción sobre PostgreSQL.
    """
    if db is None:
        raise HTTPException(500, "run_adhoc_query requiere una sesión de base de datos")

    spec = _ADHOC_METRICS.get(metric)
    if spec is None:
        raise HTTPException(
            400,
            f"Métrica no soportada: {metric!r}. Disponibles: "
            f"{', '.join(sorted(_ADHOC_METRICS))}.",
        )

    model = spec["model"]()
    filters = filters or {}
    date_from = _coerce_date(date_from)
    date_to = _coerce_date(date_to)
    try:
        limit = max(1, min(int(limit or 100), 10_000))
    except (TypeError, ValueError):
        limit = 100

    # Expresión agregada
    if spec["agg"] == "sum":
        agg_expr = func.coalesce(func.sum(spec["value_col"](model)), 0.0)
    else:
        agg_expr = func.count(model.id)

    # Dimensión: sólo la primera reconocida, como hacía la versión anterior
    dim_name = next((d for d in (dimensions or []) if d in spec["dimensions"]), None)

    def _apply_common(q):
        if "base_filter" in spec:
            q = q.filter(spec["base_filter"](model))
        date_col_fn = spec.get("date_col")
        if date_col_fn is not None:
            col = date_col_fn(model)
            if date_from:
                q = q.filter(col >= date_from)
            if date_to:
                q = q.filter(col <= date_to)
        for key, value in filters.items():
            col_fn = spec["filters"].get(key)
            if col_fn is not None and value is not None:
                q = q.filter(col_fn(model) == value)
        return q

    if dim_name is None:
        # Total global: una sola fila desde la base de datos.
        total = _apply_common(db.query(agg_expr)).scalar() or 0
        value = round(float(total), 2) if spec["agg"] == "sum" else int(total)
        results = [{spec["total_key"]: value}]
        return {
            "metric": metric,
            "dimensions": dimensions,
            "filters": filters,
            "results": results,
            "total_rows": len(results),
        }

    value_key = spec["value_key"]

    if dim_name == "month":
        date_col = spec["dimensions"]["month"](model)
        y = func.extract("year", date_col)
        m = func.extract("month", date_col)
        q = _apply_common(db.query(y.label("y"), m.label("m"), agg_expr.label("v")))
        rows = q.group_by(y, m).order_by(y, m).limit(limit).all()
        results = [
            {
                "month": f"{int(r.y):04d}-{int(r.m):02d}" if r.y is not None else "unknown",
                value_key: round(float(r.v or 0), 2) if spec["agg"] == "sum" else int(r.v or 0),
            }
            for r in rows
        ]
    else:
        dim_col = spec["dimensions"][dim_name](model)
        q = _apply_common(db.query(dim_col.label("k"), agg_expr.label("v")))
        # Mayor primero para las sumas (era el orden de la versión anterior en
        # user_id/project_id); alfabético para los recuentos por estado.
        order = agg_expr.desc() if spec["agg"] == "sum" else dim_col
        rows = q.group_by(dim_col).order_by(order).limit(limit).all()
        results = [
            {
                dim_name: _enum_str(r.k),
                value_key: round(float(r.v or 0), 2) if spec["agg"] == "sum" else int(r.v or 0),
            }
            for r in rows
        ]

    return {
        "metric": metric,
        "dimensions": dimensions,
        "filters": filters,
        "results": results,
        "total_rows": len(results),
    }


def run_analytics_drilldown(
    metric: str,
    dimension: str,
    value: str,
    date_from: Optional[date],
    date_to: Optional[date],
    page: int,
    page_size: int,
    db: Session,
) -> dict:

    offset = (page - 1) * page_size
    rows = []

    if metric == "hours_logged":
        q = db.query(Imputation)
        if dimension == "project_id":
            q = q.filter(Imputation.project_id == value)
        elif dimension == "user_id":
            q = q.filter(Imputation.user_id == value)
        elif dimension == "month" and len(value) == 7:
            yr, mo = int(value[:4]), int(value[5:7])
            q = q.filter(
                func.strftime('%Y', Imputation.date) == str(yr),
                func.strftime('%m', Imputation.date) == f"{mo:02d}",
            )
        if date_from:
            q = q.filter(Imputation.date >= date_from)
        if date_to:
            q = q.filter(Imputation.date <= date_to)
        q.count()
        items = q.offset(offset).limit(page_size).all()
        rows = [
            {"id": i.id, "date": str(i.date), "hours": i.hours,
             "project_id": i.project_id, "user_id": i.user_id,
             "description": i.description}
            for i in items
        ]
    elif metric == "revenue":
        q = db.query(Invoice).filter(Invoice.status != "cancelled")
        if dimension == "project_id":
            q = q.filter(Invoice.project_id == value)
        elif dimension == "month" and len(value) == 7:
            yr, mo = int(value[:4]), int(value[5:7])
            q = q.filter(
                func.strftime('%Y', Invoice.issue_date) == str(yr),
                func.strftime('%m', Invoice.issue_date) == f"{mo:02d}",
            )
        elif dimension == "status":
            q = q.filter(Invoice.status == value)
        q.count()
        items = q.offset(offset).limit(page_size).all()
        rows = [
            {"id": i.id, "number": i.number, "total": i.total,
             "currency": i.currency,
             "status": str(i.status.value) if hasattr(i.status, 'value') else str(i.status),
             "issue_date": str(i.issue_date), "client_name": i.client_name}
            for i in items
        ]
    else:
        raise HTTPException(status_code=400, detail=f"Metric '{metric}' not supported for drilldown")

    return {
        "metric": metric,
        "dimension": dimension,
        "value": value,
        "page": page,
        "page_size": page_size,
        "rows": rows,
    }


def run_analytics_cross_filter(payload: dict, db: Session) -> dict:

    active = payload.get("active_filters", {})
    metrics = payload.get("metrics", ["task_count"])
    result = {}

    if "task_count" in metrics:
        q = db.query(Task)
        if active.get("project_id"):
            q = q.filter(Task.project_id == active["project_id"])
        if active.get("status"):
            q = q.filter(Task.status == active["status"])
        if active.get("assignee_id"):
            q = q.filter(Task.assignee_id == active["assignee_id"])
        tasks = q.all()
        result["task_count"] = {"total": len(tasks), "by_status": {}, "by_priority": {}}
        for t in tasks:
            s = str(t.status.value) if hasattr(t.status, 'value') else str(t.status)
            p = str(t.priority.value) if hasattr(t.priority, 'value') else str(t.priority)
            result["task_count"]["by_status"][s] = result["task_count"]["by_status"].get(s, 0) + 1
            result["task_count"]["by_priority"][p] = result["task_count"]["by_priority"].get(p, 0) + 1

    if "hours_logged" in metrics:
        q = db.query(Imputation)
        if active.get("project_id"):
            q = q.filter(Imputation.project_id == active["project_id"])
        if active.get("user_id"):
            q = q.filter(Imputation.user_id == active["user_id"])
        imps = q.all()
        total_h = sum(i.hours or 0 for i in imps)
        by_proj: dict = {}
        for i in imps:
            by_proj[i.project_id or "N/A"] = by_proj.get(i.project_id or "N/A", 0) + (i.hours or 0)
        result["hours_logged"] = {
            "total": round(total_h, 2),
            "by_project": {k: round(v, 2) for k, v in sorted(by_proj.items(), key=lambda x: -x[1])[:20]},
        }

    return {"active_filters": active, "results": result}
