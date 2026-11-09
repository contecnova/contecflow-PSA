"""
BI Embedded Analytics SDK Service
===================================
Gestiona tokens JWT seguros para iframes embebidos, configuración CSP/origins
y el flujo SSO para aplicaciones externas.

Diseño:
- Tokens firmados con python-jose (HS256, TTL configurable)
- Metadatos en AppSetting JSON blob keyed by org_id
- Sin migraciones: todo el estado en sd_app_settings / bi_app_settings
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

_EMBED_ALGO = "HS256"


# ── AppSetting helpers ────────────────────────────────────────────────────────

def _get_json(db: Session, key: str) -> dict:
    from app.models.settings import AppSetting  # local import — avoids circular
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return {}


def _set_json(db: Session, key: str, data: dict) -> None:
    from app.models.settings import AppSetting
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    serialized = json.dumps(data)
    if row:
        row.value = serialized
    else:
        row = AppSetting(key=key, value=serialized)
        db.add(row)
    # Revisión 2026-11: antes sólo hacía `flush` y ningún endpoint confirmaba:
    # la lista de tokens, las revocaciones y la configuración no se guardaban
    # nunca (revocar un token no servía de nada).
    db.commit()


def _embed_secret(org_id: str) -> str:
    """Derive a stable per-org embed signing secret from the app secret key."""
    return f"{settings.SECRET_KEY}:embed:{org_id}"


# ── Embed token generation / validation ───────────────────────────────────────

def create_embed_token(
    db: Session,
    org_id: str,
    user_id: str | None,
    dashboard_id: str,
    permissions: list[str] | None = None,
    ttl_minutes: int = 60,
) -> dict:
    """Generate a signed JWT embed token.

    Returns:
        {"token": str, "expires_at": iso8601, "dashboard_id": str}
    """
    if ttl_minutes < 1 or ttl_minutes > 10080:  # max 1 week
        raise HTTPException(400, "ttl_minutes debe estar entre 1 y 10080")

    now = datetime.now(tz=timezone.utc)
    exp = now + timedelta(minutes=ttl_minutes)
    jti = str(uuid.uuid4())

    payload = {
        "sub": user_id or "anonymous",
        "org": org_id,
        "dash": dashboard_id,
        "perms": permissions or ["read"],
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "embed",
    }
    token = jwt.encode(payload, _embed_secret(org_id), algorithm=_EMBED_ALGO)

    # Store token metadata for revocation support
    meta_key = f"bi.embed.tokens.{org_id}"
    meta = _get_json(db, meta_key)
    tokens: list = meta.get("tokens", [])
    # Prune expired tokens to avoid unbounded growth
    tokens = [t for t in tokens if t.get("exp", 0) > int(now.timestamp())]
    tokens.append({"jti": jti, "exp": int(exp.timestamp()), "dash": dashboard_id, "revoked": False})
    meta["tokens"] = tokens[-200:]  # cap at 200
    _set_json(db, meta_key, meta)

    return {"token": token, "expires_at": exp.isoformat(), "dashboard_id": dashboard_id}


def validate_embed_token(db: Session, org_id: str, token: str) -> dict:
    """Validate an embed token.  Returns decoded claims or raises 401."""
    try:
        claims = jwt.decode(token, _embed_secret(org_id), algorithms=[_EMBED_ALGO])
    # intentional: chained re-raise preserves context
    except JWTError as exc:
        raise HTTPException(401, f"Token de embed inválido: {exc}") from exc

    if claims.get("type") != "embed":
        raise HTTPException(401, "Token no es de tipo embed")

    # Check revocation list
    meta_key = f"bi.embed.tokens.{org_id}"
    meta = _get_json(db, meta_key)
    jti = claims.get("jti")
    for t in meta.get("tokens", []):
        if t["jti"] == jti and t.get("revoked"):
            raise HTTPException(401, "Token de embed revocado")

    return claims


def revoke_embed_token(db: Session, org_id: str, jti: str) -> None:
    meta_key = f"bi.embed.tokens.{org_id}"
    meta = _get_json(db, meta_key)
    for t in meta.get("tokens", []):
        if t["jti"] == jti:
            t["revoked"] = True
    _set_json(db, meta_key, meta)


# ── Embed configuration (CSP, allowed origins) ────────────────────────────────

_DEFAULT_EMBED_CONFIG: dict[str, Any] = {
    "allowed_origins": [],
    "csp_frame_ancestors": ["self"],
    "sandbox_flags": [
        "allow-scripts",
        "allow-same-origin",
        "allow-popups",
        "allow-forms",
    ],
    "default_ttl_minutes": 60,
    "sso_enabled": False,
    "sso_trusted_issuers": [],
}


def get_embed_config(db: Session, org_id: str) -> dict:
    cfg = _get_json(db, f"bi.embed.config.{org_id}")
    return {**_DEFAULT_EMBED_CONFIG, **cfg}


def save_embed_config(db: Session, org_id: str, config: dict) -> dict:
    allowed_keys = set(_DEFAULT_EMBED_CONFIG.keys())
    unknown = set(config.keys()) - allowed_keys
    if unknown:
        raise HTTPException(422, f"Campos no permitidos en embed config: {unknown}")
    existing = get_embed_config(db, org_id)
    merged = {**existing, **config}
    _set_json(db, f"bi.embed.config.{org_id}", merged)
    return merged


# ── SSO Exchange ──────────────────────────────────────────────────────────────

def sso_exchange_token(
    db: Session,
    org_id: str,
    external_token: str,
    dashboard_id: str,
    ttl_minutes: int = 60,
) -> dict:
    """Exchange a trusted external SSO token for a Contecflow embed token.

    The external token is validated against the trusted issuers configured
    in embed_config.sso_trusted_issuers.  If not configured, the exchange
    always fails with 403.
    """
    cfg = get_embed_config(db, org_id)
    if not cfg.get("sso_enabled"):
        raise HTTPException(403, "SSO embed no está habilitado para esta organización")

    trusted_issuers: list[dict] = cfg.get("sso_trusted_issuers", [])
    if not trusted_issuers:
        raise HTTPException(403, "No hay emisores SSO configurados")

    # Try each trusted issuer
    external_claims: dict | None = None
    for issuer_cfg in trusted_issuers:
        secret = issuer_cfg.get("secret")
        algorithm = issuer_cfg.get("algorithm", "HS256")
        if not secret:
            continue
        try:
            external_claims = jwt.decode(external_token, secret, algorithms=[algorithm])
            break
        except JWTError:
            continue

    if external_claims is None:
        raise HTTPException(401, "Token SSO externo inválido o expirado")

    user_id = external_claims.get("sub") or external_claims.get("email")
    return create_embed_token(
        db, org_id, user_id, dashboard_id,
        permissions=external_claims.get("perms", ["read"]),
        ttl_minutes=ttl_minutes,
    )


# ── JS SDK configuration blob ─────────────────────────────────────────────────

def get_sdk_config(db: Session, org_id: str, dashboard_id: str, token: str) -> dict:
    """Return the JS SDK configuration payload consumed by the frontend SDK."""
    claims = validate_embed_token(db, org_id, token)
    cfg = get_embed_config(db, org_id)
    return {
        "dashboard_id": dashboard_id,
        "embed_token": token,
        "permissions": claims.get("perms", ["read"]),
        "allowed_origins": cfg.get("allowed_origins", []),
        "sandbox_flags": cfg.get("sandbox_flags", []),
        "csp_frame_ancestors": cfg.get("csp_frame_ancestors", ["self"]),
        "theme": "auto",
        "locale": "es",
        "sdk_version": "1.0.0",
    }


# ── Página de incrustación (revisión 2026-11) ─────────────────────────────────
#
# La pestaña de Teams y la parte web de SharePoint (`m365_bi_embed_service`)
# enlazaban a `/embed/bi`, una página que no existía; y la web se sirve con
# `X-Frame-Options: DENY`, así que ningún iframe ajeno la habría mostrado. La
# sirve la API: valida el token en el servidor (firma, tipo, revocación, empresa
# y panel) y pinta la foto de indicadores de `get_dashboard_snapshot` —la misma
# de las tarjetas de Teams y de los Word/Excel—, sin la aplicación ni sesión.
# Quién puede incrustarla lo dice su `frame-ancestors`: `BI_EMBED_FRAME_ANCESTORS`
# (Admin) más los `csp_frame_ancestors` de la configuración de la empresa.

_TEXTOS = {
    "es": {"titulo": "Indicadores", "ingresos": "Ingresos", "coste": "Coste", "horas": "Horas", "mes": "Último mes",
           "prevision": "Previsión de ingresos (3 meses)", "anomalias": "Anomalías detectadas",
           "desvios": "Proyectos con riesgo de sobrecoste", "sin_datos": "Sin datos", "generado": "Generado"},
    "en": {"titulo": "Indicators", "ingresos": "Revenue", "coste": "Cost", "horas": "Hours", "mes": "Last month",
           "prevision": "Revenue forecast (3 months)", "anomalias": "Anomalies detected",
           "desvios": "Projects at risk of overrun", "sin_datos": "No data", "generado": "Generated"},
    "zh": {"titulo": "指标", "ingresos": "收入", "coste": "成本", "horas": "工时", "mes": "上月",
           "prevision": "收入预测(3个月)", "anomalias": "检测到的异常",
           "desvios": "有超支风险的项目", "sin_datos": "无数据", "generado": "生成时间"},
}


def frame_ancestors(db: Session, org_id: str) -> str:
    """Quién puede incrustar la página: el ajuste de Admin más la lista de la empresa."""
    from app.services.settings_service import get_runtime_str
    base = (get_runtime_str(db, "BI_EMBED_FRAME_ANCESTORS", org_id) or "").split()
    extra = [("'self'" if a == "self" else a) for a in get_embed_config(db, org_id).get("csp_frame_ancestors", [])]
    vistos: list[str] = []
    for a in base + extra:
        if a and a not in vistos:
            vistos.append(a)
    return " ".join(vistos) or "'none'"


def pagina(db: Session, org_id: str, dashboard_id: str, token: str) -> str:
    """HTML de la foto de indicadores para un iframe. Lanza 401 si el token no vale para ese panel."""
    import html
    from app.services.m365_bi_embed_service import get_dashboard_snapshot
    from app.services.settings_service import get_runtime_str
    claims = validate_embed_token(db, org_id, token)
    if claims.get("org") != org_id or claims.get("dash") != dashboard_id:
        raise HTTPException(401, "El token no es de este panel")
    # Petición sin usuario: la sesión se acota a la empresa del token.
    db.info.update(organization_id=org_id, is_superadmin=False)
    foto = get_dashboard_snapshot(db, organization_id=org_id, dashboard_id=dashboard_id)
    idioma = (get_runtime_str(db, "DEFAULT_LANGUAGE", org_id) or "es")[:2]
    tx = _TEXTOS.get(idioma, _TEXTOS["es"])
    e = html.escape

    def numero(v) -> str:
        return e(f"{v:,.0f}") if isinstance(v, (int, float)) else "—"

    def filas(items, celdas) -> str:
        if not items:
            return f'<tr><td colspan="2" class="vacio">{e(tx["sin_datos"])}</td></tr>'
        return "".join("<tr>" + "".join(f"<td>{c}</td>" for c in celdas(i)) + "</tr>" for i in items)

    prevision = filas(foto.get("forecast_3m") or [], lambda f: (e(str(f.get("month"))), numero(f.get("predicted"))))
    desvios = filas(foto.get("overrun_predictions") or [],
                    lambda p: (e(str(p.get("project_name") or p.get("project_code") or p.get("project_id") or "—")),
                               e(str(p.get("risk_level") or p.get("overrun_probability") or ""))))
    return f"""<!doctype html><html lang="{e(idioma)}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(tx["titulo"])} · {e(dashboard_id)}</title>
<style>body{{font-family:system-ui,sans-serif;margin:16px;color:#1f2933;background:#fff}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0}}
.kpi{{border:1px solid #e4e7eb;border-radius:8px;padding:10px}}.kpi b{{display:block;font-size:20px}}
table{{width:100%;border-collapse:collapse;margin-top:6px}}td{{padding:5px 6px;border-bottom:1px solid #eef0f2;font-size:14px}}
h2{{font-size:15px;margin:18px 0 4px}}.vacio,small{{color:#7b8794}}
@media (prefers-color-scheme:dark){{body{{background:#14171c;color:#e4e7eb}}.kpi{{border-color:#2d333b}}td{{border-color:#232830}}}}</style>
</head><body><h1 style="font-size:18px;margin:0">{e(tx["titulo"])}</h1>
<small>{e(tx["mes"])}: {e(str(foto.get("latest_month") or "—"))}</small>
<div class="kpis"><div class="kpi">{e(tx["ingresos"])}<b>{numero(foto.get("latest_revenue"))}</b></div>
<div class="kpi">{e(tx["coste"])}<b>{numero(foto.get("latest_cost"))}</b></div>
<div class="kpi">{e(tx["horas"])}<b>{numero(foto.get("latest_hours"))}</b></div>
<div class="kpi">{e(tx["anomalias"])}<b>{numero(foto.get("anomaly_count"))}</b></div></div>
<h2>{e(tx["prevision"])}</h2><table>{prevision}</table>
<h2>{e(tx["desvios"])}</h2><table>{desvios}</table>
<p><small>{e(tx["generado"])}: {e(str(foto.get("generated_at") or ""))}</small></p></body></html>"""
