# Auditoría de Seguridad — Contecflow PSA

**Fecha:** 2025  
**Alcance:** Código fuente completo del backend (FastAPI/Python) y frontend (React/Vite)  
**Metodología:** Revisión estática de código, análisis OWASP Top 10, revisión de dependencias

---

## Resumen Ejecutivo

Contecflow PSA tiene una base de seguridad sólida en la mayoría de las áreas críticas:
autenticación con JWT, MFA/passkeys, ABAC+RBAC, headers de seguridad completos, rate limiting,
y protección SSRF en OIDC. Se identificaron **4 vulnerabilidades que requieren corrección**
(1 HIGH, 2 MEDIUM, 1 MEDIUM-LOW) y varias recomendaciones informativas.

| Severidad | Cantidad |
|-----------|---------|
| HIGH      | 1       |
| MEDIUM    | 2       |
| LOW       | 2       |
| INFO      | 4       |

---

## 1. Autenticación y Gestión de Sesiones

### Estado: ✅ Bien implementado

**Positivo:**
- JWT HS256 con rotación de claves vía `kid` header (`app/services/key_management.py`)
- Tokens de corta duración: access 15 min (máx 30 min), refresh 30 días
- Refresh tokens con JTI rotation — detección de reuso (revocación en cascada)
- Cookies: `httponly=True`, `samesite=lax`, `secure` en producción, path restringido
- Brute-force: rate limiting `5/minute` en login + lockout Redis por user+IP bucket
- Account lockout: 5 intentos → 900s lockout (`LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS`)
- MFA: TOTP (pyotp) + WebAuthn/FIDO2 — flujo con `mfa_challenge_token` consumible
- Anti-enumeración en password reset (respuesta genérica)
- `_JWT_RESERVED_CLAIMS` protege contra claim injection

**Finding INFO-1:** JWT usa HS256 (simétrico). Para arquitecturas multi-servicio se recomienda RS256.

---

## 2. Autorización (RBAC + ABAC)

### Estado: ✅ Bien implementado

**Positivo:**
- `ABACMiddleware` global sobre rutas registradas — fail-closed (403 en error inesperado)
- `enforce_abac` en endpoints críticos (documentos, etc.)
- `RequireRole` con bypass solo para superadmin
- Tenant isolation via `db.info["organization_id"]` en `get_current_user`
- SCIM: `require_scim_token` rechaza con 503 si `SCIM_BEARER_TOKEN` está vacío (correcto)

---

## 3. Inyección SQL

### Estado: ✅ Sin vulnerabilidades explotables

- ORM SQLAlchemy en todo el backend — sin SQL raw excepto casos aislados
- `app/services/scheduled_reports_compat.py:55`: columnas dinámicas validadas contra `PRAGMA table_info` (metadatos internos, no input de usuario)
- `app/integrations/bi_etl_connectors.py:256`: nombre de entidad Salesforce, configurado por admin, no por usuario final

---

## 4. Inyección de Comandos / Shell

### Estado: ✅ Sin vulnerabilidades explotables

- `subprocess.run` en `bookings_service.py` con `shell=False` (por defecto)
- Whitelist estricta `ALLOWED_TERRAFORM_COMMANDS = {"plan", "apply", "destroy"}`
- Doble validación: whitelist del config + whitelist de runtime policy

---

## 5. SSRF — Server-Side Request Forgery

### 🔴 FINDING HIGH-1: SSRF en `_execute_provision_action`

**Archivo:** `app/services/bookings_service.py` ~línea 985  
**Riesgo:** Un administrador que pueda configurar flujos de aprovisionamiento puede apuntar la URL a servicios internos (metadata de cloud, Redis, bases de datos internas).

**Código vulnerable:**
```python
url = config.get("url")
# ...sin validación...
with httpx.Client(timeout=timeout_seconds) as client:
    resp = client.request(method, url, headers=headers, json=payload)
```

**Contraste:** `validate_https_discovery_url()` en `auth_service.py` tiene protección completa contra SSRF (localhost, IPs privadas, resolución DNS).

**Remediación:** Aplicar la misma validación SSRF antes de hacer la petición. **FIX APLICADO** (ver sección de correcciones).

---

### Estado SSRF en OIDC: ✅ Protegido

`validate_https_discovery_url()` bloquea: localhost, `.local`, IPs privadas/loopback/link-local/multicast, y valida la resolución DNS.

---

## 6. Carga de Archivos

### Estado: ✅ Bien implementado, con una nota

**Positivo:**
- Whitelist MIME (`ALLOWED_MIME_TYPES`) + whitelist extensiones + detección magic bytes
- Bloquea extensiones de archivos comprimidos (`.zip`, `.tar`, `.gz`, etc.)
- Bloquea ejecutables por magic bytes (MZ, ELF, Mach-O, shebang)
- SVGs servidos con `Content-Disposition: attachment` — previene ejecución inline de scripts

**Finding LOW-1:** `application/xml` y `text/xml` están en whitelist. Los archivos XML maliciosos pueden causar XXE si se parsean con un parser inseguro. Verificar que ningún código procese XMLs subidos con parsers no-hardened.

---

## 7. Deserialización Insegura

### 🟡 FINDING MEDIUM-1: ML Model — Ruta legacy sin verificación HMAC

**Archivo:** `app/services/ml_trainer.py` ~línea 103  
**Riesgo:** Modelos ML serializados con joblib/pickle sin firma HMAC se cargan con solo un `warning`. Un atacante con acceso de escritura a la base de datos o al almacenamiento de modelos podría subir un pickle malicioso.

**Código vulnerable:**
```python
def _deserialize_model(data: bytes):
    if len(data) < 33:
        # Legacy unsigned model bytes — allow load but log warning
        logger.warning("ML model bytes have no HMAC signature (legacy)...")
        return joblib.load(io.BytesIO(data))  # ← carga sin validación
```

**Remediación:** En entornos de producción, rechazar modelos sin firma. **FIX APLICADO** (ver sección de correcciones).

---

## 8. Open Redirect en SSO

### 🟡 FINDING MEDIUM-2: `redirect_to` sin validación en SSO

**Archivo:** `app/services/bookings_service.py` ~línea 887, `app/models/bookings.py` línea 243  
**Riesgo:** El parámetro `redirect_to` se acepta en el query string del endpoint SSO y se devuelve en la respuesta sin validación de destino. Si el frontend usa este valor para redirigir, puede ser un open redirect.

**Código afectado:**
```python
# bookings.py model
redirect_to = Column(String(500), default="/dashboard")

# sso_create_or_login_user — devuelve el redirect_to tal cual
return { ..., "redirect_to": redirect_to, ... }
```

**Remediación:** Validar que `redirect_to` sea una ruta relativa (comience con `/`) o esté en una lista de dominios permitidos. **FIX APLICADO** (ver sección de correcciones).

---

## 9. Criptografía y Secretos

### Estado: ✅ Bien implementado

**Positivo:**
- `SECRET_KEY` requerido (sin default en config)
- bcrypt para contraseñas y API keys
- Fernet + HKDF (v2, per-record salt) para field-level encryption
- AWS KMS envelope mode disponible
- Webhook/email/SCIM secrets con default vacío — configuración intencional (SCIM rechaza si vacío)

**Finding INFO-2:** `WEBHOOK_SECRET`, `INBOUND_EMAIL_SECRET` tienen default `""`. Si el código webhook no valida la firma cuando el secret está vacío, podrían recibirse callbacks sin autenticación. Verificar handlers de webhooks.

---

## 10. Headers de Seguridad y Transporte

### Estado: ✅ Bien implementado

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY` (SAMEORIGIN solo en previews de documentos)
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy` completo
- HSTS en producción
- CSP completo para API; `unsafe-inline` solo en Swagger/ReDoc
- CORS: lista explícita (`ALLOWED_ORIGINS`), sin wildcard

**Finding INFO-3 (INFO):** CSP en rutas de documentación (`/docs`, `/redoc`) permite `unsafe-inline` para scripts. Aceptable para Swagger UI pero documentar.

---

## 11. Rate Limiting y DoS

### Estado: ✅ Bien implementado

- slowapi con Redis en producción, in-memory en dev
- Rate limit global: `200/minute` por defecto
- Login: `5/minute` + lockout
- Password reset: `5/minute` con ventana de 15 min
- Aviso en logs si Redis no está disponible (fallback in-memory no seguro para multi-worker)

---

## 12. WebSockets

### Estado: ✅ Bien implementado

- Tickets de acceso firmados con HMAC, verificados al conectar
- `r.eval()` en `ws.py` es el método Redis Lua scripting (librería redis-py) — no es `eval()` de Python

---

## 13. SSO / SAML

### Estado: ⚠️ Parcialmente implementado

**Finding LOW-2: SAML — Implementación demo, sin validación de firma**

**Archivo:** `app/services/bookings_service.py` ~línea 848  
```python
redirect_url = f"{config.saml_sso_url}?SAMLRequest=DEMO_ENCODED_REQUEST&RelayState={state}"
```
El callback SAML (`process_saml_callback`) acepta campos del payload sin verificar la firma XML de la aserción SAML. Esto es una implementación demo/stub. Si SAML se activa en producción, **se debe integrar una librería de validación SAML real** (ej. `python3-saml`, `pysaml2`).

---

## 14. Frontend

### Estado: ⚠️ No auditado en profundidad

Las principales superficies de riesgo frontend a revisar manualmente:
- Uso de `dangerouslySetInnerHTML` con datos de usuario
- Almacenamiento de tokens en `localStorage` vs cookies HttpOnly
- Dependencias con vulnerabilidades conocidas (`npm audit`)

---

## Resumen de Findings

| ID | Severidad | Descripción | Archivo | Estado |
|----|-----------|-------------|---------|--------|
| HIGH-1 | 🔴 HIGH | SSRF en `_execute_provision_action` — URL sin validación | `bookings_service.py:985` | ✅ CORREGIDO |
| MEDIUM-1 | 🟡 MEDIUM | ML model legacy path — pickle sin firma HMAC en producción | `ml_trainer.py:103` | ✅ CORREGIDO |
| MEDIUM-2 | 🟡 MEDIUM | Open redirect — `redirect_to` sin validar en SSO | `bookings_service.py:887` | ✅ CORREGIDO |
| LOW-1 | 🟢 LOW | XML en whitelist de uploads — riesgo XXE si se parsea | `documents.py:54` | Pendiente manual |
| LOW-2 | 🟢 LOW | SAML — sin validación de firma, implementación demo | `bookings_service.py:848` | Pendiente |
| INFO-1 | ℹ️ INFO | JWT HS256 simétrico — considerar RS256 para multi-servicio | `security.py` | Informativo |
| INFO-2 | ℹ️ INFO | Webhook secret default vacío — verificar handlers | `config.py` | Pendiente verificación |
| INFO-3 | ℹ️ INFO | CSP `unsafe-inline` en Swagger/ReDoc | `main.py` | Aceptable/Documentado |

---

## Correcciones Aplicadas

### HIGH-1: SSRF en `_execute_provision_action`

Se añadió validación SSRF (idéntica a `validate_https_discovery_url`) antes de ejecutar peticiones HTTP en flujos de aprovisionamiento. Bloquea: URLs no-HTTPS, localhost, dominios `.local`, IPs privadas/loopback/link-local/multicast, y también valida la resolución DNS.

**Archivo modificado:** `app/services/bookings_service.py`

### MEDIUM-1: ML Model legacy unsigned load

Se añade comprobación del entorno: en producción (`ENVIRONMENT != "development"`), los modelos sin firma HMAC se rechazan con excepción en lugar de cargarse con warning.

**Archivo modificado:** `app/services/ml_trainer.py`

### MEDIUM-2: Open redirect en SSO `redirect_to`

Se añade función `_validate_redirect_to` que solo permite rutas relativas (empiezan con `/`) o la URL del backend/frontend configurada. URLs externas o con `://` son rechazadas.

**Archivo modificado:** `app/services/bookings_service.py`
