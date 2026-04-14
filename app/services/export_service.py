"""
Export service — helper functions for generating Excel/CSV reports.
The heavy lifting is in integrations.py endpoint; this module holds
reusable helpers for formatting and data extraction.
"""
from sqlalchemy.orm import Session
from datetime import date
from app.models.imputation import Imputation


def get_imputation_rows(db: Session, user_id=None, project_ids=None,
                        date_from: date = None, date_to: date = None,
                        include_costs: bool = False) -> list:
    q = db.query(Imputation).join(Imputation.user).join(Imputation.project)
    if user_id:
        q = q.filter(Imputation.user_id == user_id)
    if project_ids:
        q = q.filter(Imputation.project_id.in_(project_ids))
    if date_from:
        q = q.filter(Imputation.date >= date_from)
    if date_to:
        q = q.filter(Imputation.date <= date_to)

    rows = []
    for imp in q.all():
        row = {
            "Fecha": imp.date,
            "Persona": imp.user.full_name if imp.user else "",
            "Departamento": imp.user.department if imp.user else "",
            "Proyecto": imp.project.name if imp.project else "",
            "Código": imp.project.code if imp.project else "",
            "Horas": imp.hours,
            "Descripción": imp.description or "",
            "Facturable": "Sí" if imp.is_billable else "No",
            "Aprobado": "Sí" if imp.is_approved else "No",
        }
        if include_costs:
            row["Coste (€)"] = imp.cost_amount or 0
            row["Tarifa €/h"] = imp.hourly_rate_snapshot or 0
        rows.append(row)
    return rows
