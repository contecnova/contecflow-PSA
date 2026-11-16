"""Ajustes en caliente de licencias y hardware (grupo `alm` del catálogo).

Los valores por defecto están en `app/core/config.py` (``ALM_*``); cada empresa
los cambia en Ajustes → Licencias y hardware. Un valor ilegible cae al defecto.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings


def ajuste_str(db: Session, clave: str, org: Optional[str]) -> str:
    from app.services.settings_service import get_runtime_str
    valor = get_runtime_str(db, clave, org)
    return str(valor if valor is not None else getattr(settings, clave, "") or "")


def ajuste_int(db: Session, clave: str, org: Optional[str]) -> int:
    from app.services.settings_service import get_runtime_int
    try:
        valor = get_runtime_int(db, clave, org)
    except (TypeError, ValueError):
        valor = None
    return int(valor if valor is not None else getattr(settings, clave, 0) or 0)


def ajuste_float(db: Session, clave: str, org: Optional[str]) -> float:
    from app.services.settings_service import get_runtime_float
    try:
        valor = get_runtime_float(db, clave, org)
    except (TypeError, ValueError):
        valor = None
    return float(valor if valor is not None else getattr(settings, clave, 0.0) or 0.0)


def ajuste_bool(db: Session, clave: str, org: Optional[str]) -> bool:
    from app.services.settings_service import get_runtime_bool
    valor = get_runtime_bool(db, clave, org)
    return bool(valor if valor is not None else getattr(settings, clave, False))


def ajuste_lista(db: Session, clave: str, org: Optional[str]) -> list[str]:
    return [p.strip() for p in ajuste_str(db, clave, org).split(",") if p.strip()]


# ── Textos de los avisos ──────────────────────────────────────────────────────
# Un aviso se guarda como texto (la bandeja no traduce): sale en el idioma de
# la plataforma (`DEFAULT_LANGUAGE`).

_AVISOS = {
    "es": {
        "act_to_sign_title": "Acta pendiente de firma: {nombre}",
        "act_to_sign_delivery": "Revisa y firma el acta de entrega del equipo.",
        "act_to_sign_return": "Revisa y firma el acta de devolución del equipo.",
        "loan_due_title": "Devolución próxima: {nombre}",
        "loan_due_body": "El préstamo vence el {fecha}.",
        "loan_overdue_title": "Préstamo vencido: {nombre}",
        "loan_overdue_body": "Debía devolverse el {fecha} ({dias} días de retraso).",
        "renewal_notice_title": "Renovación próxima: {nombre}",
        "renewal_notice_body": "Renueva el {fecha}. El preaviso para cancelar o reducir acaba el {limite}.",
        "renewal_deadline_title": "Último día de preaviso: {nombre}",
        "renewal_deadline_body": "Si no se decide hoy, renovará el {fecha} en las mismas condiciones.",
        "auto_renewed_title": "Renovado automáticamente: {nombre}",
        "auto_renewed_body": "Nueva fecha de renovación: {fecha}.",
        "expired_title": "Vencido sin renovar: {nombre}",
        "expired_body": "Venció el {fecha}.",
    },
    "en": {
        "act_to_sign_title": "Act waiting for your signature: {nombre}",
        "act_to_sign_delivery": "Review and sign the equipment delivery act.",
        "act_to_sign_return": "Review and sign the equipment return act.",
        "loan_due_title": "Loan due soon: {nombre}",
        "loan_due_body": "The loan is due on {fecha}.",
        "loan_overdue_title": "Loan overdue: {nombre}",
        "loan_overdue_body": "It was due on {fecha} ({dias} days late).",
        "renewal_notice_title": "Upcoming renewal: {nombre}",
        "renewal_notice_body": "Renews on {fecha}. The notice period to cancel or reduce ends on {limite}.",
        "renewal_deadline_title": "Last day of notice: {nombre}",
        "renewal_deadline_body": "Without a decision today it renews on {fecha} on the same terms.",
        "auto_renewed_title": "Renewed automatically: {nombre}",
        "auto_renewed_body": "New renewal date: {fecha}.",
        "expired_title": "Expired without renewal: {nombre}",
        "expired_body": "It expired on {fecha}.",
    },
    "zh": {
        "act_to_sign_title": "待签署的交接单：{nombre}",
        "act_to_sign_delivery": "请查看并签署设备交付单。",
        "act_to_sign_return": "请查看并签署设备归还单。",
        "loan_due_title": "借用即将到期：{nombre}",
        "loan_due_body": "借用将于 {fecha} 到期。",
        "loan_overdue_title": "借用已逾期：{nombre}",
        "loan_overdue_body": "应于 {fecha} 归还（已逾期 {dias} 天）。",
        "renewal_notice_title": "即将续订：{nombre}",
        "renewal_notice_body": "将于 {fecha} 续订。取消或缩减的通知期截止于 {limite}。",
        "renewal_deadline_title": "通知期最后一天：{nombre}",
        "renewal_deadline_body": "若今天不作决定，将于 {fecha} 按相同条件续订。",
        "auto_renewed_title": "已自动续订：{nombre}",
        "auto_renewed_body": "新的续订日期：{fecha}。",
        "expired_title": "已到期未续订：{nombre}",
        "expired_body": "已于 {fecha} 到期。",
    },
}


def texto_de_aviso(clave: str, **kw) -> str:
    idioma = (settings.DEFAULT_LANGUAGE or "es")[:2]
    plantilla = _AVISOS.get(idioma, _AVISOS["en"]).get(clave) or _AVISOS["en"].get(clave, clave)
    try:
        return plantilla.format(**kw)[:255]
    except (KeyError, IndexError):
        return plantilla[:255]
