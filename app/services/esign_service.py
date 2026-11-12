"""
Service layer for e-sign (ESignEnvelope / ESignSigner) database operations.
All db.query/add/commit/flush calls live here; the router only calls these functions.
"""
import logging
import os
from datetime import timedelta
from app.core.timeutil import utcnow
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.documents import Document
from app.models.esign import ESignEnvelope, ESignProvider, ESignSigner, ESignStatus
from app.models.settings import AppSetting
from app.core.config import settings

_log = logging.getLogger(__name__)


# ── Inbound webhook authentication ──────────────────────────────────────────────
# Provider webhooks mutate envelope state (incl. legally-binding "completed"),
# so they MUST be authenticated. Both verifiers fail CLOSED: when the relevant
# secret is not configured, every request is rejected — never silently trusted.

def verify_docusign_signature(body: bytes, signature_headers: List[str]) -> bool:
    """Verify a DocuSign Connect HMAC-SHA256 signature.

    DocuSign sends one ``X-DocuSign-Signature-N`` header per active HMAC key
    (base64 of HMAC-SHA256 over the raw request body). We accept the request if
    any provided signature matches our configured key, using a constant-time
    comparison. Returns False when no key is configured (fail-closed).
    """
    import hmac
    import hashlib
    import base64

    secret = settings.DOCUSIGN_CONNECT_HMAC_KEY
    if not secret:
        return False
    expected = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    for header in signature_headers:
        if header and hmac.compare_digest(expected, header.strip()):
            return True
    return False


def verify_adobe_client_id(client_id_header: Optional[str]) -> bool:
    """Verify an Adobe Sign webhook via the ``X-AdobeSign-ClientId`` header.

    Adobe Sign authenticates webhooks by echoing the registered OAuth client id
    in every callback (and in the intent-verification handshake). We compare it
    in constant time against ``ADOBE_SIGN_CLIENT_ID``. Returns False when the
    client id is not configured (fail-closed).
    """
    import hmac

    expected = settings.ADOBE_SIGN_CLIENT_ID
    if not expected:
        return False
    if not client_id_header:
        return False
    return hmac.compare_digest(expected, client_id_header.strip())


# ── Read helpers ──────────────────────────────────────────────────────────────

def list_envelopes(
    db: Session,
    *,
    created_by_id: Optional[int] = None,
    document_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[ESignEnvelope]:
    q = db.query(ESignEnvelope)
    if created_by_id is not None:
        q = q.filter(ESignEnvelope.created_by_id == created_by_id)
    if document_id:
        q = q.filter(ESignEnvelope.document_id == document_id)
    if status:
        q = q.filter(ESignEnvelope.status == status)
    return q.order_by(ESignEnvelope.created_at.desc()).limit(limit).all()


def get_envelope(db: Session, envelope_id: int) -> Optional[ESignEnvelope]:
    return db.query(ESignEnvelope).filter(ESignEnvelope.id == envelope_id).first()


def get_envelope_by_provider_id(db: Session, provider_envelope_id: str) -> Optional[ESignEnvelope]:
    return (
        db.query(ESignEnvelope)
        .filter(ESignEnvelope.provider_envelope_id == provider_envelope_id)
        .first()
    )


def get_document(db: Session, document_id: int) -> Optional[Document]:
    return db.query(Document).filter(Document.id == document_id).first()


def get_signer(db: Session, signer_id: int, envelope_id: int) -> Optional[ESignSigner]:
    return (
        db.query(ESignSigner)
        .filter(ESignSigner.id == signer_id, ESignSigner.envelope_id == envelope_id)
        .first()
    )


def get_signers_for_envelope(db: Session, envelope_id: int) -> List[ESignSigner]:
    return db.query(ESignSigner).filter(ESignSigner.envelope_id == envelope_id).all()


def get_stats(db: Session) -> dict:
    rows = (
        db.query(ESignEnvelope.status, func.count().label("count"))
        .group_by(ESignEnvelope.status)
        .all()
    )
    total = sum(r.count for r in rows)
    by_status = {r.status: r.count for r in rows}
    return {
        "total": total,
        "by_status": by_status,
        "completed": by_status.get(ESignStatus.completed, 0),
        "pending": by_status.get(ESignStatus.sent, 0) + by_status.get(ESignStatus.delivered, 0),
        "draft": by_status.get(ESignStatus.draft, 0),
        "declined": by_status.get(ESignStatus.declined, 0),
    }


# ── Write helpers ─────────────────────────────────────────────────────────────

def create_envelope(
    db: Session,
    *,
    document_id: int,
    created_by_id: int,
    provider: ESignProvider,
    subject: str,
    message: Optional[str],
    expires_days: int,
    signers: list,
    provider_result: dict,
) -> ESignEnvelope:
    envelope = ESignEnvelope(
        document_id=document_id,
        created_by_id=created_by_id,
        provider=provider,
        subject=subject,
        message=message,
        expires_at=utcnow() + timedelta(days=expires_days),
    )
    db.add(envelope)
    db.flush()

    for s in signers:
        signer = ESignSigner(
            envelope_id=envelope.id,
            name=s.name,
            email=s.email,
            routing_order=s.routing_order,
            user_id=s.user_id,
        )
        db.add(signer)

    db.flush()

    envelope.provider_envelope_id = provider_result.get("provider_envelope_id")
    envelope.signing_url = provider_result.get("signing_url")
    envelope.status = provider_result.get("status", ESignStatus.draft)
    if envelope.status == ESignStatus.sent:
        envelope.sent_at = utcnow()

    db.commit()
    db.refresh(envelope)
    return envelope


def update_envelope_status(
    db: Session,
    envelope: ESignEnvelope,
    new_status: ESignStatus,
) -> ESignEnvelope:
    envelope.status = new_status
    envelope.updated_at = utcnow()
    if new_status == ESignStatus.completed and not envelope.completed_at:
        envelope.completed_at = utcnow()
    if new_status == ESignStatus.sent and not envelope.sent_at:
        envelope.sent_at = utcnow()
    db.commit()
    return envelope


def mark_signer_signed(
    db: Session,
    signer: ESignSigner,
    envelope: ESignEnvelope,
) -> None:
    signer.signed = True
    signer.signed_at = utcnow()

    all_signed = all(s.signed for s in get_signers_for_envelope(db, envelope.id))
    if all_signed:
        envelope.status = ESignStatus.completed
        envelope.completed_at = utcnow()

    db.commit()


def void_envelope(db: Session, envelope: ESignEnvelope) -> ESignEnvelope:
    envelope.status = ESignStatus.voided
    envelope.updated_at = utcnow()
    db.commit()
    return envelope


def update_envelope_from_webhook(
    db: Session,
    envelope: ESignEnvelope,
    new_status: str,
) -> None:
    envelope.status = new_status
    if new_status == ESignStatus.completed.value and not envelope.completed_at:
        envelope.completed_at = utcnow()
    db.commit()


# ── AppSetting helpers for e-sign config ──────────────────────────────────────
#
# Auditoria 2026-11: los secretos de DocuSign y Adobe se guardaban en claro en
# `app_settings`. Ahora se cifran al guardar (las claves que
# `settings_service.es_sensible` reconoce) y se descifran al leer; un valor
# antiguo en claro se sigue leyendo (`decrypt_value` lo devuelve tal cual) y la
# migracion 117 cifra los que ya habia.

def cifrar_si_es_secreto(clave: str, valor: Optional[str]) -> Optional[str]:
    from app.core.encryption import encrypt_value
    from app.services.settings_service import es_sensible
    if not valor or not es_sensible(clave) or valor.startswith(("v2:", "kmsv1:")):
        return valor
    return encrypt_value(valor)


def descifrar_si_es_secreto(clave: str, valor: Optional[str]) -> Optional[str]:
    from app.core.encryption import decrypt_value
    from app.services.settings_service import es_sensible
    if not valor or not es_sensible(clave):
        return valor
    return decrypt_value(valor)


def _get_db_setting(db: Optional[Session], key: str) -> Optional[str]:
    """Read an AppSetting KV value; returns None if db is None or key missing."""
    if db is None:
        return None
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return descifrar_si_es_secreto(key, row.value) if row and row.value else None


def _set_db_setting(db: Session, key: str, value: str) -> None:
    value = cifrar_si_es_secreto(key, value)
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value, description=f"E-firma config: {key}"))
    db.commit()


def _get_docusign_config(db: Optional[Session]) -> dict:
    """Merge env-var config with DB-stored config; DB takes precedence."""
    return {
        "integration_key": _get_db_setting(db, "esign.docusign_integration_key") or settings.DOCUSIGN_INTEGRATION_KEY,
        "secret_key": _get_db_setting(db, "esign.docusign_secret_key") or settings.DOCUSIGN_SECRET_KEY,
        "account_id": _get_db_setting(db, "esign.docusign_account_id") or settings.DOCUSIGN_ACCOUNT_ID,
        "base_url": _get_db_setting(db, "esign.docusign_base_url") or settings.DOCUSIGN_BASE_URL or "https://na1.docusign.net",
        "access_token": _get_db_setting(db, "esign.docusign_access_token"),
        "refresh_token": _get_db_setting(db, "esign.docusign_refresh_token"),
        "is_demo": (_get_db_setting(db, "esign.docusign_is_demo") or "true").lower() == "true",
    }


def _get_adobe_config(db: Optional[Session]) -> dict:
    """Merge env-var config with DB-stored config; DB takes precedence."""
    return {
        "client_id": _get_db_setting(db, "esign.adobe_sign_client_id") or settings.ADOBE_SIGN_CLIENT_ID,
        "client_secret": _get_db_setting(db, "esign.adobe_sign_client_secret") or settings.ADOBE_SIGN_CLIENT_SECRET,
        "base_url": _get_db_setting(db, "esign.adobe_sign_base_url") or settings.ADOBE_SIGN_BASE_URL,
        "access_token": _get_db_setting(db, "esign.adobe_sign_access_token"),
        "refresh_token": _get_db_setting(db, "esign.adobe_sign_refresh_token"),
    }


def _ensure_docusign_token(db: Session, cfg: dict) -> Optional[str]:
    """Return a valid DocuSign access token, refreshing if needed."""
    from app.services.esign_providers import docusign_refresh_token as _ds_refresh

    token = cfg.get("access_token")
    if token:
        return token

    refresh = cfg.get("refresh_token")
    if refresh and cfg.get("integration_key") and cfg.get("secret_key"):
        result = _ds_refresh(
            cfg["integration_key"], cfg["secret_key"], refresh,
            is_demo=cfg.get("is_demo", True),
        )
        if result["ok"]:
            _set_db_setting(db, "esign.docusign_access_token", result["access_token"])
            if result.get("refresh_token"):
                _set_db_setting(db, "esign.docusign_refresh_token", result["refresh_token"])
            _log.info("[eSign] DocuSign access token refreshed successfully")
            return result["access_token"]
        _log.warning("[eSign] DocuSign token refresh failed: %s", result.get("error"))

    return None


def _ensure_adobe_token(db: Session, cfg: dict) -> Optional[str]:
    """Return a valid Adobe Sign access token, refreshing if needed."""
    from app.services.esign_providers import adobe_sign_refresh_token as _ab_refresh

    token = cfg.get("access_token")
    if token:
        return token

    refresh = cfg.get("refresh_token")
    if refresh and cfg.get("client_id") and cfg.get("client_secret"):
        result = _ab_refresh(
            cfg["client_id"], cfg["client_secret"], refresh,
            base_url=cfg.get("base_url"),
        )
        if result["ok"]:
            _set_db_setting(db, "esign.adobe_sign_access_token", result["access_token"])
            if result.get("refresh_token"):
                _set_db_setting(db, "esign.adobe_sign_refresh_token", result["refresh_token"])
            _log.info("[eSign] Adobe Sign access token refreshed successfully")
            return result["access_token"]
        _log.warning("[eSign] Adobe Sign token refresh failed: %s", result.get("error"))

    return None


def _read_document_bytes(doc: Document, db: Optional[Session]) -> tuple[bytes, str, str]:
    """Return (file_content_bytes, file_name, file_extension) for the document's latest version.

    Tries S3 first, then local filesystem. Falls back to a 1-byte placeholder
    on error so the envelope is still registered.
    """
    # Get latest version
    latest_version = None
    if doc.versions:
        latest_version = sorted(doc.versions, key=lambda v: v.version_num, reverse=True)[0]
    elif db is not None:
        from app.models.documents import DocumentVersion
        latest_version = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc.id)
            .order_by(DocumentVersion.version_num.desc())
            .first()
        )

    if latest_version is None:
        _log.error("[eSign] Document %s has no stored versions; cannot send for signature", doc.id)
        raise ValueError(
            f"Document {doc.id} has no content to sign (no stored versions)."
        )

    file_name = latest_version.file_name or "document.pdf"
    ext = os.path.splitext(file_name)[1].lstrip(".").lower() or "pdf"
    file_key = latest_version.file_key

    # Try S3
    try:
        # Con el cliente ya configurado, y no con un `boto3.client("s3")` nuevo:
        # ese no sabía nada de `AWS_S3_ENDPOINT_URL` ni de las credenciales del
        # `.env`, así que con el almacén del stack preguntaba a AWS, fallaba y
        # caía al disco, donde el documento no está. Firmar un documento
        # guardado en S3 fallaba siempre fuera de AWS.
        from app.services.s3_service import S3Service, file_storage
        if isinstance(file_storage, S3Service) and file_storage.is_available() and file_key:
            obj = file_storage.client.get_object(Bucket=file_storage.bucket, Key=file_key)
            return obj["Body"].read(), file_name, ext
    except Exception as exc:
        _log.debug("[eSign] S3 read failed, trying local: %s", exc)

    # Try local filesystem
    # `UPLOAD_DIR` ya esta declarado en `Settings` con `env="UPLOAD_DIR"` y
    # defecto "uploads", asi que pydantic lee la variable de entorno por su
    # cuenta: el `os.environ.get` de respaldo era una segunda fuente para el
    # mismo ajuste. Auditoria 2026-08.
    upload_root = settings.UPLOAD_DIR
    local_path = os.path.join(upload_root, file_key.lstrip("/"))
    if os.path.exists(local_path):
        with open(local_path, "rb") as fh:
            return fh.read(), file_name, ext

    _log.error("[eSign] Could not read document %s from S3 or local path %s", doc.id, local_path)
    raise ValueError(
        f"Document {doc.id} content could not be retrieved from storage; refusing "
        f"to send an empty document for signature."
    )


# ── Provider helpers ───────────────────────────────────────────────────────────

def docusign_configured(db: Optional[Session] = None) -> bool:
    cfg = _get_docusign_config(db)
    return bool(cfg["integration_key"] and cfg["account_id"])


def adobe_agreement_status(db: Session, agreement_id: str) -> Optional[str]:
    """Estado real del acuerdo segun la API de Adobe Sign, o None si no se pudo leer.

    Auditoria 2026-11: el webhook de Adobe solo trae `X-AdobeSign-ClientId`, que
    no es un secreto (Adobe no firma sus webhooks). Quien lo conozca podia marcar
    un sobre como firmado. El estado ya no se toma del cuerpo: se pregunta a
    Adobe con nuestras credenciales.
    """
    from app.services.esign_providers import adobe_sign_get_agreement_status

    cfg = _get_adobe_config(db)
    token = _ensure_adobe_token(db, cfg)
    if not token:
        return None
    result = adobe_sign_get_agreement_status(token, cfg["base_url"], agreement_id)
    if not result["ok"]:
        _log.warning("[eSign] No se pudo leer el acuerdo %s de Adobe Sign: %s", agreement_id, result.get("error"))
        return None
    return result["status"]


def adobe_configured(db: Optional[Session] = None) -> bool:
    cfg = _get_adobe_config(db)
    return bool(cfg["client_id"])


#: Lo que devuelve esta función cuando no hay proveedor configurado: el sobre se
#: queda en borrador y se firma a mano.
_MODO_MANUAL = {"provider_envelope_id": None, "signing_url": None, "status": ESignStatus.draft}


def _enviar_a_proveedor(envelope, doc, db, *, nombre: str, config, asegurar_token,
                        crear, clave_obligatoria: str, clave_del_id: str,
                        ajuste_a_limpiar: str) -> dict:
    """Crea el sobre en un proveedor de firma. Vale para DocuSign y para Adobe.

    Auditoría 2026-09 (hallazgo 18): los dos proveedores estaban escritos como
    dos bloques **estructuralmente idénticos** —comprobar configuración,
    asegurar token, leer el documento, resolver firmantes, llamar, limpiar el
    token si hay 401, registrar— de cuarenta líneas cada uno. Lo que cambia
    entre ellos son cinco nombres, y eso son parámetros, no una copia.

    El 401 borra el token guardado a propósito: es la señal de que caducó, y
    dejarlo puesto haría fallar también la siguiente llamada.
    """
    cfg = config(db)
    if not cfg.get(clave_obligatoria) or (nombre == "DocuSign" and not cfg.get("account_id")):
        _log.info("[eSign] %s not configured; falling back to manual mode", nombre)
        return dict(_MODO_MANUAL)

    token = asegurar_token(db, cfg) if db else cfg.get("access_token")
    if not token:
        raise ValueError(
            f"{nombre} access token not available. Complete OAuth at "
            f"/esign/auth/{nombre.lower().replace(' ', '')}/authorize"
        )

    doc_bytes, doc_name, doc_ext = _read_document_bytes(doc, db)
    resultado = crear(
        token=token,
        cfg=cfg,
        subject=envelope.subject or "Document for signature",
        message=envelope.message,
        signers=_envelope_signers_from_envelope(envelope, db),
        doc_name=doc_name,
        doc_content=doc_bytes,
        doc_extension=doc_ext,
    )

    if not resultado["ok"]:
        if "401" in str(resultado.get("error", "")) and db:
            _set_db_setting(db, ajuste_a_limpiar, "")
        raise ValueError(f"{nombre} envelope creation failed: {resultado.get('error')}")

    _log.info("[eSign] %s envelope created: %s", nombre, resultado.get(clave_del_id))
    return {
        "provider_envelope_id": resultado[clave_del_id],
        "signing_url": None,
        "status": ESignStatus.sent,
    }


def create_provider_envelope(envelope, doc, db: Optional[Session] = None) -> dict:
    """Crea el sobre/acuerdo en el proveedor configurado.

    Devuelve `{provider_envelope_id, signing_url, status}`. Si el proveedor no
    está configurado —o no se reconoce— cae a modo manual, que es un estado
    válido y no un error: el documento se firma fuera de la aplicación.
    """
    from app.services.esign_providers import (
        docusign_create_envelope as _ds_create,
        adobe_sign_create_agreement as _ab_create,
    )

    if envelope.provider == ESignProvider.docusign:
        return _enviar_a_proveedor(
            envelope, doc, db,
            nombre="DocuSign",
            config=_get_docusign_config,
            asegurar_token=_ensure_docusign_token,
            crear=lambda *, token, cfg, **kw: _ds_create(
                access_token=token, account_id=cfg["account_id"], base_url=cfg["base_url"],
                send_immediately=True, **kw,
            ),
            clave_obligatoria="integration_key",
            clave_del_id="envelope_id",
            ajuste_a_limpiar="esign.docusign_access_token",
        )

    if envelope.provider == ESignProvider.adobe_sign:
        return _enviar_a_proveedor(
            envelope, doc, db,
            nombre="Adobe Sign",
            config=_get_adobe_config,
            asegurar_token=_ensure_adobe_token,
            crear=lambda *, token, cfg, **kw: _ab_create(
                access_token=token, base_url=cfg["base_url"], **kw,
            ),
            clave_obligatoria="client_id",
            clave_del_id="agreement_id",
            ajuste_a_limpiar="esign.adobe_sign_access_token",
        )

    return dict(_MODO_MANUAL)


def _envelope_signers_from_envelope(envelope, db: Optional[Session]) -> list:
    """Extract signer dicts from the envelope's signers relationship or DB query."""
    signers_list = []
    if hasattr(envelope, "signers") and envelope.signers:
        for s in envelope.signers:
            signers_list.append({
                "name": s.name,
                "email": s.email,
                "routing_order": s.routing_order,
            })
    return signers_list


# ── Los ajustes de e-firma, por organizacion ────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 22). Estos dos ayudantes vivian en
# `endpoints/esign.py` y buscaban asi:
#
#     db.query(AppSetting).filter(AppSetting.key == key).first()
#
# **Sin organizacion.** Y lo que guardan son las credenciales de DocuSign y de
# Adobe Sign de cada cliente, incluidos su `secret_key` y —lo mas grave— los
# **tokens de acceso y de refresco** que devuelve el OAuth.
#
# Las consecuencias, en orden:
#
#   · La escritura creaba la fila con `organization_id` a NULL, que en
#     `AppSetting` significa «valor global del despliegue». Asi que el primer
#     cliente que configurara su DocuSign lo dejaba como valor de TODOS.
#   · La lectura devolvia la primera fila con esa clave, sin mirar de quien es.
#     Un cliente firmaba con la cuenta de DocuSign de otro.
#   · Y al completar el OAuth, el token de acceso de un cliente quedaba
#     guardado como global: cualquier otro enviaba sobres con su token.
#
# La regla que se aplica es la que ya usa el resto del repositorio para
# `AppSetting` (ver `governance_compliance_service`): **lo propio si existe, y
# si no el global**, que es el valor que trae el despliegue. La escritura
# siempre en lo propio. Asi las filas globales que ya existen siguen sirviendo
# de respaldo y no se rompe ningun despliegue en marcha.

#: Las claves de configuracion de e-firma que expone `/esign/config`.
CLAVES_DE_FIRMA = [
    "esign.docusign_integration_key",
    "esign.docusign_secret_key",
    "esign.docusign_account_id",
    "esign.docusign_base_url",
    "esign.adobe_sign_client_id",
    "esign.adobe_sign_client_secret",
    "esign.adobe_sign_base_url",
]

#: De esas, las que nunca se devuelven en claro.
CLAVES_SECRETAS = {
    "esign.docusign_secret_key",
    "esign.adobe_sign_client_secret",
}


def ajuste_de_firma(db: Session, sujeto, clave: str):
    """El valor de un ajuste de e-firma: el propio, y si no el global.

    Un sujeto sin organizacion solo ve el global, que es lo correcto: no hay
    «lo propio» que devolver.
    """
    from app.models.settings import AppSetting

    org_id = getattr(sujeto, "organization_id", None)
    if org_id:
        fila = (
            db.query(AppSetting)
            .filter(
                AppSetting.key == clave,
                AppSetting.organization_id == org_id,
            )
            .first()
        )
        if fila and fila.value:
            return descifrar_si_es_secreto(clave, fila.value)

    fila = (
        db.query(AppSetting)
        .filter(
            AppSetting.key == clave,
            AppSetting.organization_id.is_(None),
        )
        .first()
    )
    return descifrar_si_es_secreto(clave, fila.value) if fila and fila.value else None


def guardar_ajuste_de_firma(db: Session, sujeto, clave: str, valor: str) -> None:
    """Guarda un ajuste de e-firma en la organizacion del sujeto.

    No confirma: la frontera de transaccion es `guardar_ajustes_de_firma`.

    Si el sujeto no tiene organizacion escribe el global, que es el unico sitio
    donde puede escribir y coincide con lo que hacia antes para todos.
    """
    from app.models.settings import AppSetting

    valor = cifrar_si_es_secreto(clave, valor)
    org_id = getattr(sujeto, "organization_id", None)
    consulta = db.query(AppSetting).filter(AppSetting.key == clave)
    if org_id:
        consulta = consulta.filter(AppSetting.organization_id == org_id)
    else:
        consulta = consulta.filter(AppSetting.organization_id.is_(None))

    fila = consulta.first()
    if fila:
        fila.value = valor
        return

    db.add(AppSetting(
        key=clave,
        value=valor,
        organization_id=org_id,
        description=f"E-firma config: {clave}",
    ))


def guardar_ajustes_de_firma(db: Session, sujeto, ajustes: dict) -> None:
    """Guarda varios ajustes de e-firma en una sola transaccion, y confirma.

    Un solo `commit` al final, no uno por clave: un fallo a mitad no deja unas
    credenciales guardadas y otras no.
    """
    for clave, valor in ajustes.items():
        guardar_ajuste_de_firma(db, sujeto, clave, valor)
    db.commit()
