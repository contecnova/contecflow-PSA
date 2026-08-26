"""
v238 Features Service — Business logic extracted from v238_features.py router.
Covers: Pipeline stage configs, forecast, booking conflicts, gantt leveling,
automation trigger/action types, custom field trigger test, BI ad-hoc,
drilldown, cross-filter, Stripe payments, CRDT collab snapshots.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List
import json
import logging
import hmac
import hashlib

from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException

from app.core.config import settings
from app.models.user import User
from app.models.bookings import ResourceBooking as Booking
from app.models.pipeline import PipelineStageConfig
from app.models.billing_reports import Invoice
from app.models.document_collab import DocumentCollabSnapshot
from app.models.documents import Document
from app.models.imputation import Imputation
from app.models.service_desk import Ticket
from app.models.task import Task
from collections import defaultdict

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE — stage configs + forecast
# ──────────────────────────────────────────────────────────────────────────────

_DEFAULT_STAGE_CONFIGS = [
    {"stage_key": "lead", "label": "Lead", "color": "#6B7280", "order": 0, "probability_default": 10, "is_terminal": False, "is_won": False},
    {"stage_key": "qualification", "label": "Calificación", "color": "#3B82F6", "order": 1, "probability_default": 25, "is_terminal": False, "is_won": False},
    {"stage_key": "proposal", "label": "Propuesta", "color": "#8B5CF6", "order": 2, "probability_default": 50, "is_terminal": False, "is_won": False},
    {"stage_key": "negotiation", "label": "Negociación", "color": "#F59E0B", "order": 3, "probability_default": 75, "is_terminal": False, "is_won": False},
    {"stage_key": "won", "label": "Ganada", "color": "#10B981", "order": 4, "probability_default": 100, "is_terminal": True, "is_won": True},
    {"stage_key": "lost", "label": "Perdida", "color": "#EF4444", "order": 5, "probability_default": 0, "is_terminal": True, "is_won": False},
]


def get_stage_configs(db: Session) -> dict:
    configs = db.query(PipelineStageConfig).filter(
        PipelineStageConfig.is_active == True
    ).order_by(PipelineStageConfig.order).all()
    if not configs:
        return {"configs": _DEFAULT_STAGE_CONFIGS, "source": "defaults"}
    return {
        "configs": [
            {
                "id": c.id, "stage_key": c.stage_key, "label": c.label,
                "description": c.description, "color": c.color, "order": c.order,
                "probability_default": c.probability_default,
                "is_terminal": c.is_terminal, "is_won": c.is_won,
            }
            for c in configs
        ],
        "source": "custom",
    }


def create_stage_config_record(
    stage_key: str,
    label: str,
    description: Optional[str],
    color: Optional[str],
    order: Optional[int],
    probability_default: Optional[float],
    is_terminal: Optional[bool],
    is_won: Optional[bool],
    db: Session,
) -> dict:
    existing = db.query(PipelineStageConfig).filter(
        PipelineStageConfig.stage_key == stage_key
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Stage key '{stage_key}' already exists")
    config = PipelineStageConfig(
        stage_key=stage_key,
        label=label,
        description=description,
        color=color or "#6B7280",
        order=order or 0,
        probability_default=probability_default or 50,
        is_terminal=is_terminal or False,
        is_won=is_won or False,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return {"id": config.id, "stage_key": config.stage_key, "label": config.label, "created": True}


def delete_stage_config_record(stage_key: str, db: Session) -> None:
    config = db.query(PipelineStageConfig).filter(PipelineStageConfig.stage_key == stage_key).first()
    if not config:
        raise HTTPException(status_code=404, detail="Stage config not found")
    config.is_active = False
    db.commit()


def get_booking_conflicts(
    user_id: Optional[str],
    start_date: Optional[date],
    end_date: Optional[date],
    threshold_pct: float,
    db: Session,
) -> dict:

    q = db.query(Booking)
    if user_id:
        q = q.filter(Booking.user_id == user_id)
    if start_date:
        q = q.filter(Booking.end_date >= start_date)
    if end_date:
        q = q.filter(Booking.start_date <= end_date)

    bookings = q.all()
    user_bookings: dict = defaultdict(list)
    for b in bookings:
        user_bookings[b.user_id].append(b)

    conflicts = []
    capacity_per_day = settings.DEFAULT_WORKING_HOURS_PER_DAY

    for uid, user_bks in user_bookings.items():
        daily: dict = defaultdict(float)
        for b in user_bks:
            d = b.start_date
            while d <= b.end_date:
                daily[d] += (b.hours_per_day or settings.DEFAULT_WORKING_HOURS_PER_DAY)
                d += timedelta(days=1)

        overloaded_days = [
            {"date": str(d), "hours": round(h, 1), "utilization_pct": round(h / capacity_per_day * 100, 1)}
            for d, h in daily.items()
            if h / capacity_per_day * 100 > threshold_pct
        ]
        if overloaded_days:
            user_obj = db.query(User).filter(User.id == uid).first()
            conflicts.append({
                "user_id": uid,
                "user_name": user_obj.full_name if user_obj else uid,
                "overloaded_days": sorted(overloaded_days, key=lambda x: x["date"]),
                "max_utilization_pct": max(d["utilization_pct"] for d in overloaded_days),
                "bookings_count": len(user_bks),
            })

    return {
        "threshold_pct": threshold_pct,
        "conflicts_count": len(conflicts),
        "conflicts": sorted(conflicts, key=lambda x: x["max_utilization_pct"], reverse=True),
    }


def get_gantt_leveling(
    project_id: Optional[str],
    start_date: Optional[date],
    end_date: Optional[date],
    db: Session,
) -> dict:

    q = db.query(Booking)
    if project_id:
        q = q.filter(Booking.project_id == project_id)
    if start_date:
        q = q.filter(Booking.end_date >= start_date)
    if end_date:
        q = q.filter(Booking.start_date <= end_date)

    bookings = q.order_by(Booking.start_date).all()
    capacity = settings.DEFAULT_WORKING_HOURS_PER_DAY
    user_bookings: dict = defaultdict(list)
    for b in bookings:
        user_bookings[b.user_id].append(b)

    proposals = []
    for uid, user_bks in user_bookings.items():
        sorted_bks = sorted(user_bks, key=lambda x: x.start_date)
        user_obj = db.query(User).filter(User.id == uid).first()
        daily: dict = defaultdict(float)
        for b in sorted_bks:
            d = b.start_date
            while d <= b.end_date:
                daily[d] += (b.hours_per_day or settings.DEFAULT_WORKING_HOURS_PER_DAY)
                d += timedelta(days=1)

        overloaded = {d for d, h in daily.items() if h / capacity * 100 > 100}
        if not overloaded:
            continue

        for b in sorted_bks:
            bk_days = set()
            d = b.start_date
            while d <= b.end_date:
                bk_days.add(d)
                d += timedelta(days=1)
            conflict_days = bk_days & overloaded
            if conflict_days:
                latest_conflict = max(conflict_days)
                suggested_start = latest_conflict + timedelta(days=1)
                duration_days = (b.end_date - b.start_date).days
                suggested_end = suggested_start + timedelta(days=duration_days)
                proposals.append({
                    "booking_id": b.id,
                    "user_id": uid,
                    "user_name": user_obj.full_name if user_obj else uid,
                    "project_id": b.project_id,
                    "current_start": str(b.start_date),
                    "current_end": str(b.end_date),
                    "suggested_start": str(suggested_start),
                    "suggested_end": str(suggested_end),
                    "conflict_days_count": len(conflict_days),
                    "reason": f"Resource overloaded on {len(conflict_days)} day(s)",
                })

    return {
        "analysis_period": {
            "start": str(start_date or "all"),
            "end": str(end_date or "all"),
        },
        "overloaded_users": len(set(p["user_id"] for p in proposals)),
        "proposals_count": len(proposals),
        "proposals": proposals,
    }


# ──────────────────────────────────────────────────────────────────────────────
# BI — ad-hoc query, drilldown, cross-filter
# ──────────────────────────────────────────────────────────────────────────────

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


# Métricas soportadas: cada una declara su modelo, la columna que se agrega
# (None = contar filas), su columna de fecha y las dimensiones admitidas.
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


# ──────────────────────────────────────────────────────────────────────────────
# STRIPE — payment links + webhook
# ──────────────────────────────────────────────────────────────────────────────

def create_payment_link_record(invoice_id: str, db: Session) -> dict:
    from app.services.integration_credentials_service import get_credential
    org_id = None  # Stripe creds resolved at org-NULL scope unless caller threads through
    stripe_secret = get_credential(db, "stripe", "secret_key", org_id=org_id)
    if not stripe_secret:
        raise HTTPException(
            status_code=503,
            detail="Stripe no configurado. Edita en Settings → Sistema → Credenciales → Stripe, o define STRIPE_SECRET_KEY en .env."
        )
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status not in ("sent", "overdue"):
        raise HTTPException(status_code=400, detail=f"Invoice status must be 'sent' or 'overdue', got '{inv.status}'")
    if not inv.total or inv.total <= 0:
        raise HTTPException(status_code=400, detail="Invoice total must be greater than 0")

    if inv.stripe_payment_link_url:
        return {
            "invoice_id": invoice_id,
            "payment_link_url": inv.stripe_payment_link_url,
            "stripe_payment_link_id": inv.stripe_payment_link_id,
            "already_existed": True,
        }

    import httpx
    amount_cents = int(inv.total * 100)
    currency = (inv.currency or settings.DEFAULT_CURRENCY).lower()

    try:
        from app.services.settings_service import outbound_http_timeout
        with httpx.Client(timeout=outbound_http_timeout(db, default=10.0)) as client:
            price_resp = client.post(
                "https://api.stripe.com/v1/prices",
                auth=(stripe_secret, ""),
                data={
                    "unit_amount": str(amount_cents),
                    "currency": currency,
                    "product_data[name]": f"Factura {inv.number}",
                },
            )
            if price_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Stripe price creation failed: {price_resp.text}")
            price_id = price_resp.json()["id"]

            link_resp = client.post(
                "https://api.stripe.com/v1/payment_links",
                auth=(stripe_secret, ""),
                data={
                    "line_items[0][price]": price_id,
                    "line_items[0][quantity]": "1",
                    "metadata[invoice_id]": invoice_id,
                    "metadata[invoice_number]": inv.number,
                    "after_completion[type]": "redirect",
                    "after_completion[redirect][url]": f"{settings.FRONTEND_URL}/invoices?paid={invoice_id}",
                },
            )
            if link_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Stripe payment link creation failed: {link_resp.text}")
            link_data = link_resp.json()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe API error: {str(e)}")

    inv.stripe_payment_link_id = link_data["id"]
    inv.stripe_payment_link_url = link_data["url"]
    db.commit()

    return {
        "invoice_id": invoice_id,
        "invoice_number": inv.number,
        "payment_link_url": link_data["url"],
        "stripe_payment_link_id": link_data["id"],
        "amount": inv.total,
        "currency": currency,
    }


def handle_stripe_webhook(raw_body: bytes, stripe_signature: Optional[str], db: Session) -> dict:
    from app.services.integration_credentials_service import get_credential
    webhook_secret = get_credential(db, "stripe", "webhook_secret")

    if webhook_secret and stripe_signature:
        try:
            parts = {p.split("=")[0]: p.split("=")[1] for p in stripe_signature.split(",")}
            timestamp = parts.get("t", "")
            sig = parts.get("v1", "")
            signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
            expected = hmac.new(
                webhook_secret.encode("utf-8"),
                signed_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, sig):
                raise HTTPException(status_code=400, detail="Invalid Stripe signature")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Signature verification failed")

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        invoice_id = (data.get("metadata") or {}).get("invoice_id")
        if invoice_id:
            inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
            if inv and inv.status != "paid":
                inv.status = "paid"
                inv.paid_date = date.today()
                inv.stripe_paid_at = datetime.now(timezone.utc)
                if data.get("payment_intent"):
                    inv.stripe_payment_intent_id = data["payment_intent"]
                db.commit()
                logger.info(f"Invoice {invoice_id} marked as paid via Stripe webhook")

    return {"received": True, "event_type": event_type}


# ──────────────────────────────────────────────────────────────────────────────
# COLLABORATIVE DOCS — CRDT snapshot persistence
# ──────────────────────────────────────────────────────────────────────────────

def save_collab_snapshot_record(document_id: str, body: bytes, user_id: str, db: Session) -> dict:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not body:
        raise HTTPException(status_code=400, detail="Request body must be the Yjs binary state vector")

    db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
        DocumentCollabSnapshot.is_current == True,
    ).update({"is_current": False})

    last = db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
    ).order_by(DocumentCollabSnapshot.clock.desc()).first()
    clock = (last.clock or 0) + 1 if last else 1

    snapshot = DocumentCollabSnapshot(
        document_id=document_id,
        state_vector=body,
        clock=clock,
        size_bytes=len(body),
        is_current=True,
        created_by=user_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return {
        "id": snapshot.id,
        "document_id": document_id,
        "clock": snapshot.clock,
        "size_bytes": snapshot.size_bytes,
        "created_at": str(snapshot.created_at),
    }


def load_collab_snapshot_record(document_id: str, db: Session) -> dict:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    snapshot = db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
        DocumentCollabSnapshot.is_current == True,
    ).order_by(DocumentCollabSnapshot.clock.desc()).first()

    if not snapshot:
        return {"document_id": document_id, "snapshot": None, "clock": 0}

    import base64
    return {
        "document_id": document_id,
        "id": snapshot.id,
        "clock": snapshot.clock,
        "size_bytes": snapshot.size_bytes,
        "state_vector_b64": base64.b64encode(snapshot.state_vector).decode("utf-8"),
        "created_at": str(snapshot.created_at),
    }


def list_collab_snapshots_records(document_id: str, limit: int, db: Session) -> list:
    snapshots = db.query(DocumentCollabSnapshot).filter(
        DocumentCollabSnapshot.document_id == document_id,
    ).order_by(DocumentCollabSnapshot.clock.desc()).limit(limit).all()
    return [
        {"id": s.id, "clock": s.clock, "size_bytes": s.size_bytes,
         "is_current": s.is_current, "created_at": str(s.created_at)}
        for s in snapshots
    ]


# ── SCIM helpers ───────────────────────────────────────────────────────────────

def scim_bulk_error(bulk_id, status, detail) -> dict:
    return {
        "method": "UNKNOWN",
        "bulkId": bulk_id,
        "status": str(status),
        "response": {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
            "status": str(status),
            "detail": detail,
        }
    }
