"""Service layer for Salesforce sync operations."""
from datetime import date
from app.core.timeutil import utcnow
from typing import List, Optional

from sqlalchemy.orm import Session
from app.models.marketplace import IntegrationInstance
from app.models.marketplace import IntegrationConnector
from app.models.pipeline import Opportunity
from app.services.settings_service import outbound_http_timeout
from app.core.codigos_de_error import error



def _version_de_api() -> str:
    """Version de la API REST de Salesforce (`SALESFORCE_API_VERSION`; ronda 2
    auditoria 2026-11-22, §6: antes `v57.0` escrito en la URL)."""
    from app.core.config import settings
    v = str(getattr(settings, "SALESFORCE_API_VERSION", "") or "v57.0").strip()
    return v if v.startswith("v") else f"v{v}"

def get_salesforce_instance(db: Session, instance_id: str, org_id: Optional[str]):
    """Return enabled IntegrationInstance for Salesforce, scoped to org."""

    return (
        db.query(IntegrationInstance)
        .filter(
            IntegrationInstance.id == instance_id,
            IntegrationInstance.organization_id == org_id,
            IntegrationInstance.is_enabled == True,
        )
        .first()
    )


def get_salesforce_connector(db: Session, connector_id: str):
    """Return IntegrationConnector with slug=='salesforce'."""

    return (
        db.query(IntegrationConnector)
        .filter(
            IntegrationConnector.id == connector_id,
            IntegrationConnector.slug == "salesforce",
        )
        .first()
    )


def find_opportunity_by_external_id(db: Session, sf_id: str):
    """Return existing Opportunity matched by external_id, or None."""

    if not hasattr(Opportunity, "external_id"):
        return None
    return db.query(Opportunity).filter(Opportunity.external_id == sf_id).first()


def upsert_opportunity(db: Session, sf_opp: dict, mapped_stage: str, close_date: Optional[date]) -> None:
    """Create or update a local Opportunity from a Salesforce record."""

    sf_id = sf_opp.get("Id")
    existing = find_opportunity_by_external_id(db, sf_id)

    if existing:
        existing.name = sf_opp.get("Name", existing.name)
        existing.expected_revenue = sf_opp.get("Amount") or existing.expected_revenue
        existing.stage = mapped_stage
        if close_date and hasattr(existing, "close_date"):
            existing.close_date = close_date
    else:
        new_opp = Opportunity(
            name=sf_opp.get("Name", "Imported from Salesforce"),
            client_name=sf_opp.get("AccountId", "Salesforce Account"),
            stage=mapped_stage,
            expected_revenue=sf_opp.get("Amount") or 0,
        )
        if hasattr(new_opp, "external_id"):
            new_opp.external_id = sf_id
        if close_date and hasattr(new_opp, "close_date"):
            new_opp.close_date = close_date
        db.add(new_opp)


def commit_opportunities(db: Session) -> None:
    """Flush upserted opportunities to the database."""
    db.commit()


def update_instance_sync_status(
    db: Session, inst, records: int, errors: List[str]
) -> None:
    """Persist last-sync metadata on the IntegrationInstance."""
    inst.last_sync_at = utcnow()
    inst.last_sync_status = "error" if errors else "ok"
    inst.last_sync_records = records
    inst.last_error = "; ".join(errors) if errors else None
    db.commit()


# ── Sincronizacion de oportunidades (segunda auditoria 2026-11, n.º 20) ──────
# Estaba entera en el endpoint. Aqui la ejecuta el worker via `encolar`.

STAGE_MAP = {
    "Prospecting": "lead",
    "Qualification": "qualification",
    "Needs Analysis": "qualification",
    "Value Proposition": "proposal",
    "Id. Decision Makers": "proposal",
    "Perception Analysis": "negotiation",
    "Proposal/Price Quote": "proposal",
    "Negotiation/Review": "negotiation",
    "Closed Won": "won",
    "Closed Lost": "lost",
}


def preparar_sincronizacion(db: Session, instance_id: str, org_id: Optional[str]):
    """(instancia, url, token) o ErrorDeDominio 404/400/503, como antes."""
    import json
    import logging

    from app.core.encryption import decrypt_value

    inst = get_salesforce_instance(db, instance_id, org_id)
    if not inst:
        raise error(404, "no_encontrado", detail="Salesforce integration instance not found or disabled", que="integracion")
    if not get_salesforce_connector(db, inst.connector_id):
        raise error(400, "integracion_no_es_salesforce", detail="This instance is not a Salesforce connector")
    try:
        config = json.loads(decrypt_value(inst.encrypted_config) if inst.encrypted_config else "{}")
    except Exception:
        logging.getLogger(__name__).debug("sync_salesforce_opportunities: excepcion ignorada", exc_info=True)
        config = {}
    sf_base = config.get("instance_url", "")
    access_token = config.get("access_token", "")
    if not sf_base or not access_token:
        raise error(503, "esign_credenciales_incompletas", detail="Salesforce credentials incomplete. Configure instance_url and access_token in the integration settings.", servicio="Salesforce")
    return inst, sf_base, access_token


def probar_conexion(db: Session, instance_id: str, org_id: Optional[str]) -> dict:
    """Prueba real contra Salesforce (23-11-2026, «sin probar contra el servicio
    real»), solo lectura:

    - `credencial`: `GET /services/data/{version}/limits` (token válido y versión
      de API admitida por esa instancia).
    - `oportunidades`: `SELECT Id FROM Opportunity LIMIT 1` (el permiso de
      lectura que usa la sincronización de entrada).

    La sincronización de SALIDA no está implementada (`salida: no_implementada`).
    Nunca devuelve el texto de la respuesta remota."""
    from app.core.outbound_url import cliente_httpx, validate_outbound_url

    _, sf_base, access_token = preparar_sincronizacion(db, instance_id, org_id)
    validate_outbound_url(sf_base, field="instance_url", require_https=True)
    base = f"{sf_base.rstrip('/')}/services/data/{_version_de_api()}"
    cabeceras = {"Authorization": f"Bearer {access_token}"}
    resultado = {"ok": False, "verificado": "nada", "credencial": False, "oportunidades": False,
                 "salida": "no_implementada", "api_version": _version_de_api()}
    try:
        with cliente_httpx(timeout=outbound_http_timeout(db, default=15.0)) as client:
            r = client.get(f"{base}/limits", headers=cabeceras)
            if r.status_code != 200:
                return {**resultado, "status": r.status_code}
            resultado.update(credencial=True, verificado="credencial")
            q = client.get(f"{base}/query", params={"q": "SELECT Id FROM Opportunity LIMIT 1"}, headers=cabeceras)
            if q.status_code == 200:
                resultado.update(oportunidades=True, verificado="credencial_y_uso", ok=True)
            else:
                resultado["status"] = q.status_code
    except Exception as exc:  # noqa: BLE001 - se informa la clase, no el texto
        import logging
        logging.getLogger(__name__).info("prueba de Salesforce fallida", exc_info=True)
        resultado["error"] = type(exc).__name__
    return resultado


def sincronizar_oportunidades(db: Session, *, instance_id: str, direction: str,
                              org_id: Optional[str]) -> dict:
    """Trae las oportunidades abiertas de Salesforce al pipeline."""
    import logging

    inst, sf_base, access_token = preparar_sincronizacion(db, instance_id, org_id)
    synced_in = 0
    synced_out = 0
    errors: List[str] = []

    if direction in ("inbound", "bidirectional"):
        try:
            # 22-11-2026 (03 A-RZ4): `instance_url` es configuración de empresa y
            # recibe el Bearer: HTTPS y guardia SSRF central (IP conectada).
            from app.core.outbound_url import cliente_httpx, validate_outbound_url
            validate_outbound_url(sf_base, field="instance_url", require_https=True)
            with cliente_httpx(timeout=outbound_http_timeout(db, default=20.0)) as client:
                resp = client.get(
                    f"{sf_base}/services/data/{_version_de_api()}/query",
                    params={
                        "q": "SELECT Id,Name,Amount,StageName,CloseDate,AccountId FROM Opportunity WHERE IsClosed=false LIMIT 200"
                    },
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
                sf_opps = resp.json().get("records", [])
        except Exception as exc:
            logging.getLogger(__name__).warning("sync_salesforce_opportunities: excepcion ignorada", exc_info=True)
            errors.append(f"Salesforce API error: {getattr(exc, 'detail', None) or type(exc).__name__}")
            sf_opps = []

        for sf_opp in sf_opps:
            mapped_stage = STAGE_MAP.get(sf_opp.get("StageName", ""), "lead")
            try:
                close_date = date.fromisoformat(sf_opp["CloseDate"]) if sf_opp.get("CloseDate") else None
            except ValueError:
                close_date = None
            upsert_opportunity(db, sf_opp, mapped_stage, close_date)
            synced_in += 1

        if sf_opps:
            commit_opportunities(db)

    update_instance_sync_status(db, inst, synced_in + synced_out, errors)

    return {
        "ok": not errors,
        "direction": direction,
        "synced_inbound": synced_in,
        "synced_outbound": synced_out,
        "errors": errors,
        "synced_at": str(utcnow()),
    }
