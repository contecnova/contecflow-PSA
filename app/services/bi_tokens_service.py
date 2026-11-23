"""Tokens de acceso para BI externo y los datos que exponen.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `mfa_service.py`, un
fichero de 1.435 lineas que contenia OCHO dominios sin relacion entre si —MFA,
organizaciones, Slack, presupuestos, planificacion asistida, escenarios, PDF y
tokens de BI— servidos ademas por un unico router llamado `mfa.py` con 38 rutas.

El reparto se pudo hacer mecanicamente porque los ocho dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

from app.core import timeutil
import json
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user import User
from app.models.project import Project
from app.models.imputation import Imputation
from app.models.mfa import (
    BIToken,
)
from sqlalchemy.orm import joinedload as jl
from app.core.codigos_de_error import ErrorConCodigo


#: A14 (auditoría 22-11-2026): alcances de un token BI. `read` = todo lo de
#: `/bi/data/*` (lo que había); los demás, solo su recurso. Es el modelo de
#: los conectores de Power BI/Tableau de los PSA del mercado (un alcance de
#: lectura por conjunto de datos).
ALCANCES = ("read", "projects:read", "timesheets:read", "kpis:read")

#: Caché de verificación: HMAC-SHA256 del token → id del token (bcrypt solo la
#: primera vez). Los tokens son 192 bits aleatorios: el bcrypt de cada petición
#: no añadía seguridad y costaba ~250 ms. Se vuelve a leer la fila en cada
#: petición, así que revocar o caducar sigue siendo inmediato.
_VERIFICADOS: dict = {}
_VERIFICADOS_MAX = 2048


def _huella(token: str) -> str:
    import hashlib
    import hmac
    from app.core.config import settings
    return hmac.new(str(settings.SECRET_KEY).encode(), token.encode(), hashlib.sha256).hexdigest()


def _vigente(bt: BIToken) -> bool:
    exp = bt.expires_at.replace(tzinfo=timezone.utc) if bt.expires_at and not bt.expires_at.tzinfo else bt.expires_at
    return bool(bt.is_active) and not (exp and exp < datetime.now(timezone.utc))


def _contar_peticion(bt: BIToken, db: Session) -> None:
    """A14: `requests_today` se reinicia al cambiar el día (UTC) y no pasa del
    límite diario (`BI_TOKEN_DAILY_REQUEST_LIMIT`, por empresa; 0 = sin límite)."""
    from app.services.settings_service import get_runtime_int
    ahora = datetime.now(timezone.utc)
    ultimo = bt.last_used_at.replace(tzinfo=timezone.utc) if bt.last_used_at and not bt.last_used_at.tzinfo else bt.last_used_at
    hoy = 0 if (ultimo is None or ultimo.date() != ahora.date()) else int(bt.requests_today or 0)
    tope = get_runtime_int(db, "BI_TOKEN_DAILY_REQUEST_LIMIT", getattr(bt, "organization_id", None), default=0) or 0
    if tope and hoy >= tope:
        from app.core.codigos_de_error import error
        raise error(429, "bi_token_limite_diario", limite=tope)
    bt.last_used_at = ahora
    bt.requests_today = hoy + 1


def verify_bi_token(token: str, db: Session) -> Optional[BIToken]:
    if not token or not token.startswith("bi_"):
        return None
    huella = _huella(token)
    token_id = _VERIFICADOS.get(huella)
    if token_id:
        bt = db.query(BIToken).filter(BIToken.id == token_id).first()
        if bt is None or not _vigente(bt):
            _VERIFICADOS.pop(huella, None)
            return None
        _contar_peticion(bt, db)
        return bt
    import bcrypt
    prefix = token[:10]
    candidates = db.query(BIToken).filter(
        BIToken.token_prefix == prefix,
        BIToken.is_active == True,
    ).all()
    for bt in candidates:
        if bcrypt.checkpw(token.encode(), bt.token_hash.encode()):
            if not _vigente(bt):
                return None
            if len(_VERIFICADOS) >= _VERIFICADOS_MAX:
                _VERIFICADOS.clear()
            _VERIFICADOS[huella] = bt.id
            _contar_peticion(bt, db)
            return bt
    return None


def alcances_de(bt: BIToken) -> set:
    try:
        return set(json.loads(bt.scopes or '["read"]'))
    except (TypeError, ValueError):
        return set()


def list_bi_tokens(db: Session) -> list:
    tokens = db.query(BIToken).options(jl(BIToken.creator)).all()
    return [{
        "id": t.id, "name": t.name, "tool": t.tool,
        "token_prefix": t.token_prefix,
        "scopes": json.loads(t.scopes or '["read"]'),
        "is_active": t.is_active,
        "expires_at": str(t.expires_at)[:10] if t.expires_at else None,
        "last_used_at": str(t.last_used_at)[:16] if t.last_used_at else None,
        "requests_today": t.requests_today or 0,
        "created_by": t.creator.full_name if t.creator else None,
    } for t in tokens]


def _alcances_validos(scopes) -> list:
    """A14: solo alcances conocidos (antes se guardaba cualquier texto y no se miraba)."""
    lista = list(scopes or ["read"])
    malos = [x for x in lista if x not in ALCANCES]
    if malos:
        raise ErrorConCodigo("campo_no_valido_opciones", campo="scopes", opciones=", ".join(ALCANCES))
    return lista


def create_bi_token(payload_dict: dict, created_by: str, db: Session) -> dict:
    import bcrypt
    raw_token = "bi_" + secrets.token_hex(24)
    prefix = raw_token[:10]
    hashed = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    expires_at = None
    if payload_dict.get("expires_days"):
        expires_at = datetime.now(timezone.utc) + timedelta(days=payload_dict["expires_days"])
    t = BIToken(
        name=payload_dict["name"], tool=payload_dict.get("tool", "powerbi"),
        token_hash=hashed, token_prefix=prefix,
        scopes=json.dumps(_alcances_validos(payload_dict.get("scopes"))),
        expires_at=expires_at, created_by=created_by,
    )
    db.add(t); db.commit()
    return {"ok": True, "id": t.id, "token": raw_token,
            "warning": "Guarda este token. No se mostrará de nuevo."}


def revoke_bi_token(token_id: str, db: Session) -> dict:
    t = db.query(BIToken).filter(BIToken.id == token_id).first()
    if not t:
        raise ValueError("not_found")
    t.is_active = False
    db.commit()
    return {"ok": True}


def _check_bi_token_auth(raw_token: Optional[str], db: Session, alcance: Optional[str] = None) -> BIToken:
    """Verify BI token auth; raises ValueError('unauthorized') if invalid.

    Periodo libre (16-11-2026): además publica en la sesión la empresa del
    token (``organization_id`` y ``is_superadmin=False``) para que el filtro
    automático por empresa se aplique a lo que sigue. Sin esto la sesión de
    una petición con token BI no tenía contexto, el filtro se saltaba (sesión
    no inicializada) y ``/bi/data/*`` devolvía datos de todas las empresas.
    No se duplica el filtro: es el mismo de cualquier petición con usuario.
    Se publica DESPUÉS de verificar el token (esa consulta va sin empresa).
    """
    if not raw_token:
        raise ErrorConCodigo("token_no_valido", detail="unauthorized")
    bt = verify_bi_token(raw_token, db)
    if not bt:
        raise ErrorConCodigo("token_no_valido", detail="unauthorized")
    db.commit()
    # A14: el alcance del token se aplica (antes se guardaba y no se miraba).
    if alcance:
        tiene = alcances_de(bt)
        if "read" not in tiene and alcance not in tiene:
            from app.core.codigos_de_error import error
            raise error(403, "bi_token_sin_alcance", alcance=alcance)
    org_id = getattr(bt, "organization_id", None)
    info = getattr(db, "info", None)
    if isinstance(info, dict):
        info["organization_id"] = org_id
        info["is_superadmin"] = False
        from app.db.session import exigir_organizacion_activa
        exigir_organizacion_activa(db, org_id)
    return bt


def zona_del_token(bt: BIToken, db: Session):
    """Zona de la empresa del token (no hay usuario): ``Organization.timezone`` o UTC."""
    from app.core.timeutil import resolve_zone
    from app.models.mfa import Organization

    org_id = getattr(bt, "organization_id", None)
    org = db.get(Organization, org_id) if org_id else None
    return resolve_zone(getattr(org, "timezone", None))


def bi_data_projects(raw_token: Optional[str], db: Session) -> list:
    _check_bi_token_auth(raw_token, db, "projects:read")
    projects = db.query(Project).filter(Project.status != "archived").all()
    # Auditoría 22-11-2026: horas en UNA consulta agregada (antes una por
    # proyecto) y solo imputaciones activas.
    horas = dict(db.query(Imputation.project_id, func.sum(Imputation.hours)).filter(
        Imputation.project_id.in_([p.id for p in projects] or [""]), Imputation.is_active.is_(True),
    ).group_by(Imputation.project_id).all())
    return [{
        "id": p.id, "code": p.code, "name": p.name,
        "client_name": p.client_name, "status": p.status,
        "start_date": str(p.start_date) if p.start_date else None,
        "end_date_planned": str(p.end_date_planned) if p.end_date_planned else None,
        "budget_amount": p.budget_amount, "billing_rate": p.billing_rate,
        "total_hours_logged": float(horas.get(p.id) or 0),
    } for p in projects]


def bi_data_timesheets(
    raw_token: Optional[str],
    date_from: Optional[str], date_to: Optional[str],
    page: int, page_size: int,
    db: Session,
    desde: Optional[str] = None, hasta: Optional[str] = None,
    granularidad: Optional[str] = None, tz: Optional[str] = None,
) -> list:
    """Imputaciones para BI externo (token ``bi_*``, sin usuario).

    Periodo libre (16-11-2026): ``desde``/``hasta`` (ISO; ``hasta`` excluido)
    y ``granularidad`` (``day|week|month|auto``: la imputación es un día de
    calendario, sin hora). Las fechas sin zona se interpretan en ``tz`` o en
    la zona de la **empresa del token**. ``date_from``/``date_to`` (``date_to``
    incluido) siguen valiendo. Sin periodo, todas las imputaciones paginadas,
    como antes.

    Con ``granularidad`` la respuesta es la serie agregada del periodo (un
    punto por tramo: ``t``, ``clave``, ``hours``, ``billable_hours``,
    ``entries``), sin paginar; sin ella, las filas paginadas de siempre.
    """
    bt = _check_bi_token_auth(raw_token, db, "timesheets:read")
    p = None
    if any((desde, hasta, date_from, date_to, granularidad)):
        from app.core.periodo import SIN_HORA, limites_de_periodo, resolver_periodo, zona_de

        if not desde and date_from:
            desde = date_from
        if not hasta and date_to:
            # date_to era inclusivo: hasta = día siguiente (como los alias de `periodo()`).
            fin = date_to.strip()
            try:
                hasta = (date.fromisoformat(fin) + timedelta(days=1)).isoformat() if len(fin) == 10 else fin
            except ValueError:  # no es «token inválido» (401): es una fecha mal escrita
                from app.core.periodo import ErrorDePeriodo
                raise ErrorDePeriodo("fecha_invalida", f"Fecha no válida en «date_to»: {date_to}", param="date_to", valor=date_to)
        zona = zona_de(tz) if tz else zona_del_token(bt, db)
        p = resolver_periodo(
            desde=desde, hasta=hasta, granularidad=granularidad, zona=zona,
            limites=limites_de_periodo(db, getattr(bt, "organization_id", None)),
            dias_por_defecto=30, admitidas=SIN_HORA, serie=bool(granularidad),
        )

    if granularidad and p is not None:
        from app.core.periodo import expresion_de_bucket, filtro_de_periodo
        from sqlalchemy import case

        tramo = expresion_de_bucket(db, Imputation.date, p).label("clave")
        filas = (
            db.query(
                tramo,
                func.sum(Imputation.hours),
                func.sum(case((Imputation.is_billable == True, Imputation.hours), else_=0)),  # noqa: E712
                func.count(Imputation.id),
            )
            .filter(filtro_de_periodo(Imputation.date, p), Imputation.is_active.is_(True))
            .group_by(tramo)
            .all()
        )
        datos = {
            str(clave): {
                "hours": round(float(horas or 0), 2),
                "billable_hours": round(float(facturables or 0), 2),
                "entries": int(n or 0),
            }
            for clave, horas, facturables, n in filas if clave
        }
        return p.rellenar(datos, vacio={"hours": 0.0, "billable_hours": 0.0, "entries": 0})

    q = db.query(Imputation).options(jl(Imputation.user), jl(Imputation.project)).filter(Imputation.is_active.is_(True))
    if p is not None:
        from app.core.periodo import filtro_de_periodo
        q = q.filter(filtro_de_periodo(Imputation.date, p))
    imputations = (
        q.order_by(Imputation.date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [{
        "date": str(i.date),
        "user_name": i.user.full_name if i.user else "—",
        "user_role": i.user.role if i.user else "—",
        "project_code": i.project.code if i.project else "—",
        "project_name": i.project.name if i.project else "—",
        "hours": i.hours,
        "is_billable": i.is_billable,
        "description": i.description,
    } for i in imputations]


def bi_data_kpis(raw_token: Optional[str], db: Session) -> dict:
    _check_bi_token_auth(raw_token, db, "kpis:read")
    active_projects = db.query(func.count(Project.id)).filter(Project.status == "active").scalar()
    total_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    this_week_start = timeutil.today() - timedelta(days=timeutil.today().weekday())
    hours_this_week = db.query(func.sum(Imputation.hours)).filter(
        Imputation.date >= this_week_start, Imputation.is_active.is_(True),
    ).scalar() or 0
    total_budget = db.query(func.sum(Project.budget_amount)).filter(
        Project.status.in_(["active", "planning"])
    ).scalar() or 0
    return {
        "active_projects": active_projects,
        "total_users": total_users,
        "hours_this_week": round(hours_this_week, 1),
        "total_budget_active": round(total_budget, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
