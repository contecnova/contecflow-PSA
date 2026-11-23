"""Key management + automatic rotation for JWT and integration secrets.

Responsibilities:
- Maintain a JWT key ring with active kid and grace keys.
- Optionally generate key material via AWS KMS data keys (envelope mode).
- Periodically rotate integration secrets by decrypt+re-encrypt.
- Persist rotation metadata in app_settings.
"""
from __future__ import annotations

import base64
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.settings import AppSetting
from app.core.encryption import decrypt_value, encrypt_value
from app.models.ai_providers import AIProvider
from app.models.cab import IntegrationConfig
from app.models.enterprise import SSOConfig, Webhook
from app.core.codigos_de_error import ErrorConCodigo

logger = logging.getLogger("contecflow.key_management")

JWT_RING_KEY = "security.jwt_keyring"
INTEGRATION_ROTATION_KEY = "security.integration_rotation"
INTEGRATION_ROTATION_ALERT_KEY = "security.integration_rotation_alert_sent_at"
SENSITIVE_APP_SETTING_KEYS = {"jira_api_token"}


@dataclass
class KeyRingState:
    active_kid: str
    keys: dict[str, str]  # kid -> material_ref (plain:<key> | kms:<cipher_b64>)
    last_rotated_at: datetime


_cache: dict[str, Optional[KeyRingState]] = {"jwt": None}
#: Cuándo se cargó `_cache["jwt"]` (monotónico). Auditoría 22-11-2026 (02 A37):
#: sin caducidad, la rotación hecha en Celery no llegaba a los procesos web hasta
#: reiniciar (401 intermitentes con el kid nuevo y tokens sin validar al podar).
_cargado_en: dict[str, float] = {"jwt": 0.0}


def _cache_caducada() -> bool:
    import time as _t
    ttl = float(getattr(settings, "JWT_KEYRING_CACHE_SECONDS", 60) or 0)
    return _cache["jwt"] is None or (ttl > 0 and _t.monotonic() - _cargado_en["jwt"] > ttl)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_str(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _str_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _kms_enabled() -> bool:
    return settings.KMS_PROVIDER.lower() == "aws" and bool(settings.AWS_KMS_KEY_ID)


def _kms_client():
    import boto3

    kwargs = {}
    if settings.AWS_KMS_REGION:
        kwargs["region_name"] = settings.AWS_KMS_REGION
    return boto3.client("kms", **kwargs)


def _generate_key_material_ref() -> str:
    """Generate a new key reference (plain or KMS-wrapped)."""
    if _kms_enabled():
        try:
            client = _kms_client()
            res = client.generate_data_key(KeyId=settings.AWS_KMS_KEY_ID, KeySpec="AES_256")
            ciphertext = base64.urlsafe_b64encode(res["CiphertextBlob"]).decode()
            return f"kms:{ciphertext}"
        except Exception as exc:
            logger.error("KMS key generation failed: %s", exc, exc_info=True)
            raise

    # Non-KMS: encrypt the key material at rest with the app's field encryption
    # (Audit Sprint 3-4) so the JWT keyring is never stored as plaintext in the
    # DB, even without a KMS. `enc:` wraps an encrypt_value() ciphertext.
    raw = secrets.token_urlsafe(64)
    return f"enc:{encrypt_value(raw)}"


def _resolve_material(ref: str) -> str:
    """Resolve material ref to plaintext key string."""
    if ref.startswith("kms:"):
        blob_b64 = ref.split(":", 1)[1]
        blob = base64.urlsafe_b64decode(blob_b64.encode())
        client = _kms_client()
        res = client.decrypt(CiphertextBlob=blob)
        plaintext = base64.urlsafe_b64encode(res["Plaintext"]).decode()
        return plaintext
    if ref.startswith("enc:"):
        plaintext = decrypt_value(ref.split(":", 1)[1])
        if plaintext is None:
            raise ErrorConCodigo("error_interno", detail="Failed to decrypt enc: JWT key material")
        return plaintext
    if ref.startswith("plain:"):
        # Legacy plaintext keys (pre-encryption). Still resolvable for backward
        # compatibility; migrated to enc: by _upgrade_plaintext_keys on load.
        return ref.split(":", 1)[1]
    raise ErrorConCodigo("error_interno", detail="Invalid key material reference format")


def _get_setting(db, key: str) -> Optional[AppSetting]:
    # Key management settings are global (organization-independent).
    return db.query(AppSetting).filter(
        AppSetting.key == key, AppSetting.organization_id.is_(None)
    ).first()


def _settings_table_available(db) -> bool:
    try:
        db.query(AppSetting.id).limit(1).first()
        return True
    except (OperationalError, ProgrammingError):
        return False


def _save_keyring(db, state: KeyRingState) -> None:
    payload = {
        "active_kid": state.active_kid,
        "keys": state.keys,
        "last_rotated_at": _dt_to_str(state.last_rotated_at),
    }
    row = _get_setting(db, JWT_RING_KEY)
    if not row:
        row = AppSetting(key=JWT_RING_KEY, value=json.dumps(payload), description="JWT signing key ring")
        db.add(row)
    else:
        row.value = json.dumps(payload)


def _load_keyring(db) -> Optional[KeyRingState]:
    row = _get_setting(db, JWT_RING_KEY)
    if not row or not row.value:
        return None
    try:
        raw = json.loads(row.value)
        return KeyRingState(
            active_kid=raw["active_kid"],
            keys=raw["keys"],
            last_rotated_at=_str_to_dt(raw["last_rotated_at"]),
        )
    except Exception as exc:
        logger.error("Invalid JWT keyring payload: %s", exc, exc_info=True)
        return None


def _upgrade_plaintext_keys(db, state: KeyRingState) -> bool:
    """Re-wrap any legacy ``plain:`` key material as encrypted-at-rest (``enc:``).

    Idempotent and value-preserving: the underlying key bytes are unchanged, so
    every JWT already signed with these kids stays valid. Runs opportunistically
    on keyring load so existing deployments migrate without a manual step.
    """
    changed = False
    for kid, ref in list(state.keys.items()):
        if ref.startswith("plain:"):
            raw = ref.split(":", 1)[1]
            try:
                state.keys[kid] = f"enc:{encrypt_value(raw)}"
                changed = True
            except Exception:
                logger.error("Failed to encrypt legacy plaintext JWT key kid=%s", kid, exc_info=True)
    if changed:
        _save_keyring(db, state)
        db.commit()
        logger.info("Migrated legacy plaintext JWT key material to encrypted-at-rest")
    return changed


def ensure_jwt_keyring(db) -> KeyRingState:
    if not _settings_table_available(db):
        raise RuntimeError("Settings table not available for JWT keyring initialization.")

    state = _load_keyring(db)
    if state:
        _upgrade_plaintext_keys(db, state)
        return state

    kid = _nuevo_kid()
    state = KeyRingState(
        active_kid=kid,
        keys={kid: _generate_key_material_ref()},
        last_rotated_at=_now(),
    )
    _save_keyring(db, state)
    db.commit()
    logger.info("Initialized JWT keyring with kid=%s", kid)
    return state


def refresh_caches(db=None) -> None:
    own_session = False
    if db is None:
        db = SessionLocal()
        from app.db.contexto_de_tenant import declarar_sistema as _declarar_sistema
        _declarar_sistema(db, "llavero JWT (global)")  # auditoría 22-11-2026: TENANT_SESION_SIN_CONTEXTO=cerrar
        own_session = True
    try:
        import time as _t
        state = ensure_jwt_keyring(db)
        _cache["jwt"] = state
        _cargado_en["jwt"] = _t.monotonic()
    finally:
        if own_session:
            db.close()


def _recargar_por_caducidad() -> None:
    """Recarga el llavero caducado; si la base no responde, sigue con el que hay.

    23-11-2026: con la caducidad (02 A37) un fallo pasajero al releer `settings`
    (base caída un momento, o la sesión de pruebas en memoria) tumbaba TODA
    autenticación con 500. Con un llavero ya cargado se registra y se reintenta
    en la siguiente petición; sin ninguno, el error sube como antes.
    """
    try:
        refresh_caches()
    except Exception:
        if _cache["jwt"] is None:
            raise
        logger.warning("JWT keyring: no se pudo recargar; se sigue con el cargado", exc_info=True)


def get_jwt_signing_key() -> tuple[str, str]:
    """Return (kid, plaintext_key)."""
    if _cache_caducada():
        _recargar_por_caducidad()
    state = _cache["jwt"]
    if state is None:
        raise RuntimeError("JWT key ring not initialised — call refresh_caches() first")
    material = state.keys.get(state.active_kid)
    if not material:
        raise RuntimeError("Active JWT kid not present in key ring")
    return state.active_kid, _resolve_material(material)


def get_jwt_verification_keys(kid: Optional[str] = None) -> dict[str, str]:
    """Return map kid -> plaintext_key (active and retained keys only).

    Con `kid` desconocido se recarga el llavero una vez: lo acaba de rotar otro
    proceso (02 A37).
    """
    if _cache_caducada() or (kid and _cache["jwt"] is not None and kid not in _cache["jwt"].keys):
        _recargar_por_caducidad()
    state = _cache["jwt"]
    if state is None:
        raise RuntimeError("JWT key ring not initialised — call refresh_caches() first")
    out: dict[str, str] = {}
    for kid, ref in state.keys.items():
        try:
            # Auditoría 22-11-2026 (baja): el material descifrado se guarda por su
            # referencia; antes cada `decode_token` descifraba el llavero entero
            # (con KMS, una llamada por petición).
            if ref not in _materiales:
                _materiales[ref] = _resolve_material(ref)
            out[kid] = _materiales[ref]
        except Exception as exc:
            logger.warning("Failed resolving key for kid=%s: %s", kid, exc)
    return out


#: Material en claro por referencia (la referencia cambia al rotar: no caduca mal).
_materiales: dict[str, str] = {}


def _nuevo_kid() -> str:
    """Baja (auditoría 22-11-2026): el kid lleva un sufijo aleatorio (antes solo
    el segundo: dos rotaciones en el mismo segundo daban el mismo kid). Sigue
    empezando por la fecha, así que ordenar por kid sigue siendo cronológico."""
    import secrets as _secrets
    return f"k-{_now().strftime('%Y%m%d%H%M%S')}-{_secrets.token_hex(3)}"


def _rotate_jwt_keyring(db) -> bool:
    from app.services.settings_service import get_runtime_int
    rotation_days = get_runtime_int(db, "JWT_KEY_ROTATION_DAYS") or settings.JWT_KEY_ROTATION_DAYS
    retention     = get_runtime_int(db, "JWT_KEY_RETENTION_COUNT") or settings.JWT_KEY_RETENTION_COUNT

    # Baja (auditoría 22-11-2026): la web y el worker podían rotar a la vez y
    # perder una clave. Se serializa con un bloqueo de transacción y se relee.
    from app.db.session import is_postgres
    if is_postgres():
        from sqlalchemy import text
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext('jwt_keyring_rotation'))"))
    state = ensure_jwt_keyring(db)
    due_at = state.last_rotated_at + timedelta(days=rotation_days)
    if _now() < due_at:
        return False

    new_kid = _nuevo_kid()
    state.keys[new_kid] = _generate_key_material_ref()
    state.active_kid = new_kid
    state.last_rotated_at = _now()

    # Poda de las más antiguas manteniendo `retention`. §5 (auditoría
    # 22-11-2026): la excepción de "legacy-secret-key" era una referencia
    # colgante (ningún `kid` se llama así) y se retira.
    ordered = sorted(state.keys.keys())
    while len(ordered) > retention:
        drop = ordered.pop(0)
        state.keys.pop(drop, None)

    _save_keyring(db, state)
    db.commit()
    logger.warning("JWT keyring rotated. New active kid=%s", new_kid)
    return True


# ── Recifrado de secretos de integracion ─────────────────────────────────────
#
# Auditoria 2026-08. `_rotate_integration_secrets` era complejidad 21 en cinco
# bloques que hacen lo mismo sobre cinco modelos. Al ponerlos uno al lado del
# otro aparecio una asimetria que NO era intencionada, y que corrompia material
# criptografico.
#
# ── El defecto ────────────────────────────────────────────────────────────────
#
# Tres de los cinco bloques llevaban una rama de respaldo «esto es plaintext
# heredado, ciframoslo»:
#
#     if plain:                      -> recifrar
#     elif not valor.startswith("v2:"):   -> tratar como plaintext y cifrar
#
# El respaldo de SSO y de webhooks solo comprobaba `v2:`; el de `AppSetting`
# comprobaba `v2:` y `kmsv1:`. Y la rama es inalcanzable para su proposito
# declarado: `decrypt_value()` YA devuelve el texto plano cuando el valor es
# plaintext heredado —lo hace su propio respaldo interno—, asi que un plaintext
# entra siempre por `if plain:`.
#
# Lo unico que llega al `elif` es un valor cuyo descifrado FALLO de verdad. Y
# entonces:
#
#     valor = "kmsv1:..."  y KMS no responde  ->  decrypt_value() = None
#                                              ->  no empieza por "v2:"
#                                              ->  se CIFRA EL CRIPTOGRAMA
#
# Resultado: el secreto de cliente OIDC y los secretos de webhook quedan
# cifrados dos veces y son irrecuperables sin descifrar dos niveles. Como se
# ejecuta desde la rotacion programada, ocurriria sin que nadie lo pidiera, y el
# sintoma seria que el SSO deja de funcionar. `AppSetting` se salvaba solo
# porque su comprobacion incluia los dos prefijos.
#
# Comprobado por ejecucion:
#     decrypt_value("clave-en-claro") -> 'clave-en-claro'   (entra por `if plain`)
#     decrypt_value("v2:sin-punto")   -> None
#     decrypt_value("kmsv1:AAAA")     -> None                (el caso corruptor)
#
# ── El arreglo ────────────────────────────────────────────────────────────────
#
# Se recifra SOLO cuando el descifrado ha funcionado. Un valor que no se puede
# descifrar se deja intacto y se AVISA con el modelo, el identificador y el
# campo —nunca el valor—, para que un secreto ilegible se vea en el log en vez
# de destruirse en silencio o desaparecer sin rastro.


@dataclass(frozen=True, slots=True)
class _SecretoARecifrar:
    """Un modelo y los campos suyos que guardan secretos cifrados."""

    modelo: object
    campos: tuple[str, ...]
    filtro: object = None      # consulta acotada, si el modelo lo necesita
    modo: str = "valor"        # ver `_secretos_a_recifrar`


def _secretos_a_recifrar() -> tuple[_SecretoARecifrar, ...]:
    """La tabla de lo que hay que recifrar.

    Se construye en una funcion y no como constante de modulo porque
    `SENSITIVE_APP_SETTING_KEYS` se lee en el momento de la consulta.

    Auditoría 22-11-2026 (02 A38): solo había 5 modelos; las credenciales por
    empresa, Jira, los tokens de colaboración, NVD/GHSA, marketplace, Slack,
    licencias, MFA, discovery y los blobs JSON con secretos anidados quedaban
    ilegibles al retirar `SECRET_KEY_PREVIOUS`.
    `tests/test_seguridad_entrada_salida_2026_11_23.py` comprueba que toda
    columna que el código cifra está aquí.

    `modo`: "valor" (columna cifrada con `encrypt_value`; lo heredado en claro
    también se cifra), "prefijo" (solo se recifra lo que ya lleva `v2:`/`kmsv1:`),
    "json" (texto JSON con valores cifrados anidados) o "colab" (MultiFernet
    propio de las integraciones de colaboración).
    """
    from app.models.alm import ALMLicense
    from app.models.cab import GDPRRequest, WebhookTrigger
    from app.models.cmdb import CMDBDiscoveryProvider
    from app.models.cmdb_software import SoftwareConfig
    from app.models.collaboration import CollaborationIntegration
    from app.models.jira_integration import JiraConfig
    from app.models.marketplace import IntegrationInstance
    from app.models.mfa import SlackConfig
    from app.models.service_desk.datos_propios import VoiceSession
    from app.models.settings import IntegrationCredential
    from app.models.user import User

    return (
        _SecretoARecifrar(AIProvider, ("api_key",)),
        _SecretoARecifrar(IntegrationConfig, ("access_token", "refresh_token")),
        _SecretoARecifrar(IntegrationConfig, ("config",), modo="json"),
        _SecretoARecifrar(SSOConfig, ("oidc_client_secret",)),
        _SecretoARecifrar(Webhook, ("secret",)),
        _SecretoARecifrar(
            AppSetting, ("value",),
            filtro=lambda q: q.filter(
                AppSetting.key.in_(list(SENSITIVE_APP_SETTING_KEYS))
            ),
        ),
        # Blobs JSON de ajustes con secretos anidados (BI ETL, BI O365, reuniones...).
        _SecretoARecifrar(
            AppSetting, ("value",), modo="json",
            filtro=lambda q: q.filter(
                ~AppSetting.key.in_(list(SENSITIVE_APP_SETTING_KEYS)),
                AppSetting.value.like('%"v2:%') | AppSetting.value.like('%"kmsv1:%'),
            ),
        ),
        _SecretoARecifrar(IntegrationCredential, ("value_encrypted",)),
        _SecretoARecifrar(JiraConfig, ("jira_api_token_enc",)),
        _SecretoARecifrar(SoftwareConfig, ("nvd_api_key", "ghsa_token"), modo="prefijo"),
        _SecretoARecifrar(SlackConfig, ("bot_token",)),
        _SecretoARecifrar(WebhookTrigger, ("secret",)),
        _SecretoARecifrar(ALMLicense, ("_license_key",), modo="prefijo"),
        _SecretoARecifrar(User, ("mfa_secret",), modo="prefijo"),
        _SecretoARecifrar(CMDBDiscoveryProvider, ("config_json",), modo="prefijo"),
        _SecretoARecifrar(IntegrationInstance, ("encrypted_config",), modo="prefijo"),
        _SecretoARecifrar(GDPRRequest, ("export_data",), modo="prefijo"),
        # Migracion 200: sesiones de voz (numero, entidades y transcripcion cifrados).
        _SecretoARecifrar(VoiceSession, ("caller_id_enc", "entities_enc", "transcript_enc"), modo="prefijo"),
        _SecretoARecifrar(CollaborationIntegration, ("access_token_enc", "refresh_token_enc"), modo="colab"),
    )


_PREFIJOS_CIFRADOS = ("v2:", "kmsv1:")


def _todas_las_empresas(db, consulta) -> list:
    """La rotación es de plataforma: lee las filas de todas las empresas."""
    try:
        from app.db.contexto_de_tenant import contexto_de_sistema
        with contexto_de_sistema(db, "rotación de claves de cifrado"):
            from app.db.session import sin_filtro_de_tenant
            with sin_filtro_de_tenant(db):
                return consulta.all()
    except ImportError:
        from app.db.session import sin_filtro_de_tenant
        with sin_filtro_de_tenant(db):
            return consulta.all()


def _recifrar_anidado(valor):
    """Recorre un JSON y recifra cada cadena cifrada. Devuelve (nuevo, cambios)."""
    if isinstance(valor, str) and valor.startswith(_PREFIJOS_CIFRADOS):
        plano = decrypt_value(valor)
        return (encrypt_value(plano), 1) if plano else (valor, 0)
    if isinstance(valor, dict):
        cambios = 0
        salida = {}
        for k, v in valor.items():
            salida[k], n = _recifrar_anidado(v)
            cambios += n
        return salida, cambios
    if isinstance(valor, list):
        cambios = 0
        salida = []
        for v in valor:
            nuevo, n = _recifrar_anidado(v)
            salida.append(nuevo)
            cambios += n
        return salida, cambios
    return valor, 0


def _recifrar_segun_modo(fila, campo: str, nombre_modelo: str, modo: str) -> bool:
    valor = getattr(fila, campo, None)
    if not valor:
        return False
    if modo == "valor":
        return _recifrar_campo(fila, campo, nombre_modelo)
    if modo == "prefijo":
        if not str(valor).startswith(_PREFIJOS_CIFRADOS):
            return False
        return _recifrar_campo(fila, campo, nombre_modelo)
    if modo == "json":
        try:
            datos = json.loads(valor)
        except (TypeError, ValueError):
            return False
        nuevo, cambios = _recifrar_anidado(datos)
        if cambios:
            setattr(fila, campo, json.dumps(nuevo))
        return bool(cambios)
    if modo == "colab":
        from app.services.collaboration._integrations import _fernet
        try:
            setattr(fila, campo, _fernet().rotate(str(valor).encode()).decode())
            return True
        except Exception:  # noqa: BLE001 — ilegible: se deja intacto y se avisa
            logger.warning("Rotación: %s.%s del registro %s no se puede descifrar; se deja intacto.",
                           nombre_modelo, campo, getattr(fila, "id", "?"))
            return False
    raise ValueError(f"recifrado_modo_desconocido:{modo}")


def _recifrar_campo(fila, campo: str, nombre_modelo: str) -> bool:
    """Recifra un campo si se puede descifrar. Devuelve si ha cambiado.

    Deja el valor intacto cuando no se puede descifrar: volver a cifrarlo
    produciria un criptograma de un criptograma, irrecuperable. Ver la nota de
    cabecera.
    """
    valor = getattr(fila, campo, None)
    if not valor:
        return False

    plano = decrypt_value(valor)
    if plano:
        setattr(fila, campo, encrypt_value(plano))
        return True

    # No se ha podido descifrar. Nunca se toca: se avisa con lo justo para
    # localizar el registro y jamas con el valor.
    logger.warning(
        "Rotación: %s.%s del registro %s no se puede descifrar; se deja intacto. "
        "Si el cifrado es KMS, comprueba el acceso a la clave antes de repetir.",
        nombre_modelo, campo, getattr(fila, "id", "?"),
    )
    return False


def _rotate_integration_secrets(db) -> int:
    """Re-encrypt sensitive integration secrets with current encryption policy."""
    changed = 0
    for spec in _secretos_a_recifrar():
        nombre = spec.modelo.__name__
        consulta = db.query(spec.modelo)
        if spec.filtro is not None:
            consulta = spec.filtro(consulta)
        for fila in _todas_las_empresas(db, consulta):
            for campo in spec.campos:
                if _recifrar_segun_modo(fila, campo, nombre, spec.modo):
                    changed += 1
    return changed


def _fecha_de_ajuste(row) -> Optional[datetime]:
    """La fecha guardada en un ajuste, o `None` si no hay o no se puede leer.

    Un valor corrupto se lee como «nunca», que es el lado seguro: fuerza una
    rotación en vez de saltársela.
    """
    if not row or not row.value:
        return None
    try:
        return _str_to_dt(row.value)
    except Exception:
        logger.debug("_fecha_de_ajuste: excepcion ignorada", exc_info=True)
        return None


def _rotacion_activada(db) -> bool:
    """Si la rotación automática está encendida, con el ajuste de fichero como respaldo."""
    from app.services.settings_service import get_runtime_bool

    try:
        activada = get_runtime_bool(db, "KEY_ROTATION_ENABLED")
    except Exception:
        logger.debug("_rotacion_activada: excepcion ignorada", exc_info=True)
        return settings.KEY_ROTATION_ENABLED
    return settings.KEY_ROTATION_ENABLED if activada is None else activada


def _rotar_secretos_si_toca(db) -> int:
    """Vuelve a cifrar los secretos de integración si ha pasado el intervalo."""
    from app.services.settings_service import get_runtime_int

    row = _get_setting(db, INTEGRATION_ROTATION_KEY)
    ultima = _fecha_de_ajuste(row)
    dias = (
        get_runtime_int(db, "INTEGRATION_SECRET_ROTATION_DAYS")
        or settings.INTEGRATION_SECRET_ROTATION_DAYS
    )
    if ultima is not None and _now() < ultima + timedelta(days=dias):
        return 0

    recifrados = _rotate_integration_secrets(db)
    if not row:
        row = AppSetting(
            key=INTEGRATION_ROTATION_KEY,
            description="Last integration secret re-encryption",
        )
        db.add(row)
    row.value = _dt_to_str(_now())
    return recifrados


def rotate_due_materials(db=None) -> dict:
    """Rota lo que toque: el llavero JWT y los secretos de integración."""
    propia = db is None
    db = db or SessionLocal()
    if propia:  # auditoría 22-11-2026: TENANT_SESION_SIN_CONTEXTO=cerrar
        from app.db.contexto_de_tenant import declarar_sistema as _declarar_sistema
        _declarar_sistema(db, "rotación de claves y secretos (global)")
    try:
        if not _rotacion_activada(db):
            return {"enabled": False, "jwt_rotated": False, "integration_reencrypted": 0}

        # Sin tabla de ajustes no hay dónde anotar la rotación, así que no se
        # rota: hacerlo sin poder registrar la fecha la repetiría en cada
        # arranque.
        if not _settings_table_available(db):
            refresh_caches(db)
            return {"enabled": True, "jwt_rotated": False, "integration_reencrypted": 0}

        rotado = _rotate_jwt_keyring(db)
        recifrados = _rotar_secretos_si_toca(db)

        db.commit()
        refresh_caches(db)
        return {
            "enabled": True,
            "jwt_rotated": rotado,
            "integration_reencrypted": recifrados,
        }
    finally:
        if propia:
            db.close()


def run_scheduled_rotation() -> None:
    """Scheduler entrypoint: rotate due keys and refresh caches."""
    try:
        result = rotate_due_materials()
        logger.info("Key rotation job result: %s", result)
    except Exception as exc:
        logger.error("Key rotation job failed: %s", exc, exc_info=True)


def _avisar_de_rotacion_vencida(db, ahora: datetime, ultima, vence) -> None:
    """Registra el aviso de rotación vencida, como mucho una vez cada 24 h.

    La limitación importa: esta función la llama una pantalla de estado, así
    que sin ella cada visita al panel escribiría una línea de aviso.
    """
    fila = _get_setting(db, INTEGRATION_ROTATION_ALERT_KEY)
    ultimo_aviso = _fecha_de_ajuste(fila)
    if ultimo_aviso is not None and ahora < ultimo_aviso + timedelta(hours=24):
        return

    logger.warning(
        "Integration secret rotation overdue: last=%s due=%s",
        _dt_to_str(ultima) if ultima else "never",
        _dt_to_str(vence) if vence else "unknown",
    )
    if not fila:
        fila = AppSetting(
            key=INTEGRATION_ROTATION_ALERT_KEY,
            description="Last emission time for integration secret rotation overdue alert",
        )
        db.add(fila)
    fila.value = _dt_to_str(ahora)
    db.commit()


def get_integration_rotation_status(db=None) -> dict:
    """Estado de la rotación de secretos, con aviso limitado cuando está vencida."""
    from app.services.settings_service import get_runtime_int

    propia = db is None
    db = db or SessionLocal()
    if propia:  # auditoría 22-11-2026: TENANT_SESION_SIN_CONTEXTO=cerrar
        from app.db.contexto_de_tenant import declarar_sistema as _declarar_sistema
        _declarar_sistema(db, "rotación de claves y secretos (global)")
    try:
        ahora = _now()
        ultima = _fecha_de_ajuste(_get_setting(db, INTEGRATION_ROTATION_KEY))
        dias = int(
            get_runtime_int(db, "INTEGRATION_SECRET_ROTATION_DAYS")
            or settings.INTEGRATION_SECRET_ROTATION_DAYS
            or 30
        )

        vence = (ultima + timedelta(days=dias)) if ultima else None
        vencida = bool(vence and ahora > vence)
        # Sin fecha de última rotación no se puede decir cuántos días quedan:
        # `None` es «no se sabe», que no es lo mismo que cero.
        quedan = int((vence - ahora).total_seconds() // 86400) if vence else None

        if vencida:
            _avisar_de_rotacion_vencida(db, ahora, ultima, vence)

        return {
            "interval_days": dias,
            "last_rotated_at": _dt_to_str(ultima) if ultima else None,
            "next_due_at": _dt_to_str(vence) if vence else None,
            "days_until_due": quedan,
            "is_overdue": vencida,
            "alert_level": (
                "critical" if vencida
                else "warning" if quedan is not None and quedan <= 7
                else "ok"
            ),
        }
    finally:
        if propia:
            db.close()
