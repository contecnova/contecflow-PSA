# Auditoría de Seguridad — Contecflow PSA
**Fecha:** 2025-07  
**Alcance:** Revisión completa del backend (FastAPI/Python), autenticación, autorización, cifrado, integraciones externas, subida de archivos, ML, webhooks y configuración.  
**Auditor:** GitHub Copilot (análisis estático exhaustivo de código)

---

## Resumen Ejecutivo

El sistema presenta una postura de seguridad sólida en las áreas críticas: autenticación JWT con rotación de claves, bcrypt para contraseñas, CSRF en SSO, validación MIME en uploads, proxies de confianza configurables y limitación de tasa con respaldo en Redis. Se identificaron y corrigieron en sesiones previas **5 vulnerabilidades de severidad alta**. En esta auditoría completa se encontraron **2 vulnerabilidades nuevas de severidad media** y 3 hallazgos de riesgo bajo/informativo adicionales.

**Estado global: MEJORADO — pendiente aplicar 2 correcciones de severidad media.**

| Severidad | Estado           | Cantidad |
|-----------|-----------------|---------|
| ALTA      | ✅ Corregidas    | 5       |
| MEDIA     | ⚠️ Pendientes   | 2       |
| BAJA      | ⚠️ Pendientes   | 2       |
| INFO      | ℹ️ Informativo  | 1       |

---

## Tabla de Hallazgos

| ID      | Severidad  | Estado          | Área              | Descripción breve                                                      |
|---------|------------|-----------------|-------------------|------------------------------------------------------------------------|
| SEC-001 | **ALTA**   | ✅ CORREGIDO    | ML                | Modelos sin firma HMAC aceptados en producción                         |
| SEC-002 | **ALTA**   | ✅ CORREGIDO    | SSRF              | `_execute_provision_action` no validaba URL antes de petición HTTP     |
| SEC-003 | **ALTA**   | ✅ CORREGIDO    | Auth/SSO          | Open redirect en callback SSO                                          |
| SEC-004 | **ALTA**   | ✅ CORREGIDO    | Auth              | Stub SAML permitía autenticación sin verificar firma                   |
| SEC-005 | **ALTA**   | ✅ CORREGIDO    | Webhooks          | Webhook GitHub/GitLab aceptaba peticiones con secreto vacío            |
| SEC-006 | **MEDIA**  | ⚠️ PENDIENTE   | SSRF              | Paso `webhook` de workflow queue no valida URL contra redes internas   |
| SEC-007 | **MEDIA**  | ⚠️ PENDIENTE   | Auth/SSO          | `process_oidc_callback` acepta `email` directamente del payload POST   |
| SEC-008 | **BAJA**   | ⚠️ PENDIENTE   | GDPR/Privacidad   | IPs de usuarios transmitidas al servicio externo `ipapi.co`            |
| SEC-009 | **BAJA**   | ℹ️ INFORMATIVO | Cifrado           | Cifrado v1 legacy usa salt PBKDF2 estático (sin migración documentada) |
| SEC-010 | **INFO**   | ℹ️ DISEÑO      | ABAC              | `enforce_abac` es fail-open cuando no hay políticas configuradas       |

---

## Correcciones Anteriores (Verificadas y en Vigor)

### SEC-001 — Modelos ML sin firma HMAC ✅ CORREGIDO
**Archivo:** `app/services/ml_trainer.py` — `_deserialize_model`  
**Descripción:** En versiones anteriores el sistema cargaba modelos ML con `pickle.loads`/`joblib.load` sin verificar integridad HMAC, permitiendo RCE (Remote Code Execution) mediante un modelo malicioso inyectado en la BD o almacenamiento.  
**Corrección aplicada:** Los modelos sin firma HMAC-SHA256 son rechazados en entornos no-development. En development se registra advertencia en logs.

---

### SEC-002 — SSRF en provisión de identidad ✅ CORREGIDO
**Archivo:** `app/services/bookings_service.py` — `_execute_provision_action`  
**Descripción:** La función realizaba peticiones HTTP a URLs arbitrarias de configuración de workflow sin validar que no apuntasen a redes internas (metadata de cloud, servicios internos, Redis, etc.).  
**Corrección aplicada:** Se añadió `_validate_provision_url(url)` antes de toda petición httpx. Bloquea: localhost, `.local`, IPs privadas RFC1918, loopback, link-local, multicast, y cualquier hostname que resuelva DNS a esos rangos (protección anti DNS-rebinding).

---

### SEC-003 — Open Redirect en SSO ✅ CORREGIDO
**Archivo:** `app/services/bookings_service.py` — `_validate_redirect_to`  
**Descripción:** El parámetro `redirect_to` no era validado, permitiendo redirigir a URLs externas arbitrarias tras autenticación.  
**Corrección aplicada:** Solo se permiten rutas relativas que comiencen en `/` (no `//`). Cualquier URL con scheme es rechazada y se devuelve `/dashboard`.

---

### SEC-004 — Stub SAML sin verificación de firma ✅ CORREGIDO
**Archivos:** `app/services/bookings_service.py` — `process_saml_callback`; `app/api/v1/routers/auth_saml.py`  
**Descripción:** El handler SAML aceptaba aserciones XML sin verificar la firma digital, permitiendo a cualquier atacante impersonar cualquier usuario incluyendo administradores.  
**Corrección aplicada:** `process_saml_callback` lanza HTTP 503. Todos los endpoints SAML devuelven 503 indicando que SAML 2.0 no está habilitado en esta instalación.

---

### SEC-005 — Bypass de autenticación en webhooks Git ✅ CORREGIDO
**Archivo:** `app/services/git_service.py` — `verify_github_signature`, `verify_gitlab_token`  
**Descripción:** Cuando `GITHUB_WEBHOOK_SECRET` / `GITLAB_WEBHOOK_SECRET` estaban vacíos, las funciones de verificación devolvían `True`, aceptando cualquier petición como autenticada (fail-open incorrecto).  
**Corrección aplicada:** Ambas funciones devuelven `False` (rechazar) cuando el secreto no está configurado. El endpoint git lanza HTTP 403.

---

## Vulnerabilidades Nuevas — Pendientes de Corrección

### SEC-006 — SSRF en paso `webhook` de workflow queue
**Severidad:** MEDIA  
**Archivo:** `app/services/bookings_service.py` — `process_workflow_queue_record`  
**OWASP:** A10:2021 — Server-Side Request Forgery

**Descripción:**  
El procesador de workflow soporta un tipo de paso `step_type == "webhook"` que realiza una petición HTTP a una URL obtenida de la configuración del workflow (`config.get("url")`). A diferencia de `_execute_provision_action` (que tiene SSRF protection completa), este paso **no llama a `_validate_provision_url`**, exponiendo la misma superficie de ataque que fue corregida en SEC-002 pero para el tipo de paso `webhook`.

```python
# CÓDIGO VULNERABLE (bookings_service.py)
elif step.step_type == "webhook":
    try:
        import httpx
        url = config.get("url")   # ← URL sin validar contra redes internas
        method = str(config.get("method", "POST")).upper()
        ...
        if url:
            with httpx.Client(timeout=5.0) as client:
                resp = client.request(method, url, ...)  # ← SSRF posible
```

**Impacto:** Un administrador malicioso o una configuración de workflow comprometida puede usarse para hacer peticiones a servicios internos (ej. `http://169.254.169.254/` en AWS EC2, servicios en red interna, bases de datos con API HTTP, Redis con HTTP).  
**Vector de ataque:** Acceso de administrador a la configuración de workflows (UI o API) + ejecución del procesador de cola.

**Corrección recomendada:**

```python
elif step.step_type == "webhook":
    try:
        import httpx as _httpx
        url = config.get("url")
        if not url:
            step_result["ok"] = False
            step_result["error"] = "webhook step requires 'url'"
        else:
            _validate_provision_url(url)  # SSRF protection — same policy as provision actions
            method = str(config.get("method", "POST")).upper()
            headers = _render_step_value(config.get("headers") or {}, context)
            payload_wh = _render_step_value(
                config.get("payload") or {"event": config.get("event"), "context": context},
                context,
            )
            with _httpx.Client(timeout=5.0) as client:
                resp = client.request(method, url, headers=headers, json=payload_wh)
            step_result["http_status"] = resp.status_code
            step_result["response"] = resp.text[:1000]
    except ValueError as ssrf_exc:
        step_result["ok"] = False
        step_result["error"] = f"SSRF protection blocked URL: {ssrf_exc}"
    except Exception as e:
        step_result["ok"] = False
        step_result["error"] = str(e)[:100]
```

---

### SEC-007 — OIDC callback acepta `email` directamente del payload POST
**Severidad:** MEDIA  
**Archivo:** `app/services/bookings_service.py` — `process_oidc_callback`  
**OWASP:** A07:2021 — Identification and Authentication Failures

**Descripción:**  
La función `process_oidc_callback` obtiene el email del usuario directamente del payload POST sin verificar un `id_token` firmado por el IdP. En un flujo OIDC correcto, el backend debe: (1) recibir el `code` de autorización, (2) intercambiarlo con el IdP por un `id_token` JWT firmado, y (3) verificar la firma del token antes de extraer claims. Aquí el email llega directamente del cliente:

```python
def process_oidc_callback(payload: dict, db) -> dict:
    state = payload.get("state")
    state_obj = db.query(OAuthState).filter(
        OAuthState.state == state,
        OAuthState.used == False,
        OAuthState.expires_at > datetime.now(timezone.utc),
    ).first()
    if not state_obj: raise HTTPException(400, "Estado OIDC inválido o expirado")
    ...
    user_email = payload.get("email")  # ← Email arbitrario del cliente
```

**Impacto:** Cualquier cliente que posea un `state` OIDC válido (no expirado, no consumido) puede autenticarse como cualquier email arbitrario, incluyendo administradores. El estado es válido 10 minutos desde su creación.  
**Escenario de ataque:** El atacante inicia el flujo SSO para obtener un `state` válido → envía ese `state` al endpoint callback con `email=admin@empresa.com` → recibe un access token válido como administrador.

**Corrección recomendada:**  
- **Opción A (backend completo, recomendada):** El endpoint recibe el `code` de autorización, lo intercambia con el IdP (`token_endpoint` de la discovery URL), verifica la firma del `id_token` JWT con la JWKS pública del IdP, y extrae el email del `id_token` verificado.  
- **Opción B (si el frontend intercambia el código):** Exigir que el payload contenga el `id_token` firmado por el IdP. Verificar la firma JWT con las JWKS del IdP antes de aceptar cualquier claim. Nunca aceptar el email como campo independiente.

---

## Hallazgos de Riesgo Bajo / Informativos

### SEC-008 — IPs de usuarios transmitidas a servicio externo (GDPR)
**Severidad:** BAJA — Impacto en privacidad/cumplimiento  
**Archivo:** `app/services/session_security.py` — `_lookup_ip_intel`  

**Descripción:** Para enriquecer la información de sesión (país, ciudad), el sistema realiza una petición HTTP a `https://ipapi.co/{ip}/json/` para cada nueva sesión de usuario, transmitiendo la IP del usuario a un tercero.

**Impacto:**
- Posible incumplimiento del RGPD/GDPR Art. 28 (sub-encargado de tratamiento) si no hay DPA firmado con ipapi.co
- Las IPs son datos personales según GDPR Art. 4(1)
- Dependencia de disponibilidad de servicio externo en el flujo de creación de sesiones

**Corrección recomendada:**
1. Añadir configuración `IP_GEOLOCATION_ENABLED: bool = False` con opt-in explícito
2. Si se habilita, ofrecer `IP_GEOLOCATION_PROVIDER` con opción de usar MaxMind GeoLite2 (base de datos local, sin transmisión de IPs a terceros)
3. Documentar en la política de privacidad del producto

---

### SEC-009 — Cifrado v1 usa salt PBKDF2 estático (legacy)
**Severidad:** BAJA — Riesgo limitado, no explotable directamente  
**Archivo:** `app/core/encryption.py`  

**Descripción:** El esquema de cifrado v1 (legacy) usa PBKDF2 con salt estático `b"contecflow_field_enc_v1"` para derivar la clave de cifrado. El esquema v2 (actualmente activo) usa HKDF con salt aleatorio de 16 bytes por registro. Los registros v1 siguen siendo descifrables para compatibilidad.

**Impacto:** Si la clave maestra se compromete, los registros v1 son más vulnerables a ataques de precomputación que los v2 (sin salt per-registro). No es explotable sin la clave maestra comprometida.

**Recomendación:** Implementar un job de migración que re-cifre todos los valores v1 al esquema v2 y documente el procedimiento.

---

### SEC-010 — ABAC fail-open por diseño (informativo)
**Severidad:** INFO — Comportamiento documentado e intencional  
**Archivo:** `app/core/abac_enforce.py` — `enforce_abac`  

**Descripción:** Cuando no hay políticas ABAC configuradas para un recurso, `enforce_abac` retorna sin error (permite el acceso). Esto es intencional para organizaciones que solo usan RBAC sin ABAC.

El middleware ABAC (`abac_middleware.py`) es correctamente fail-closed (devuelve 403 en errores inesperados). Solo `enforce_abac` directo es fail-open.

**Recomendación:** Documentar en DOCS.md que las organizaciones que quieran usar ABAC deben configurar al menos una política por defecto. Considerar añadir `ABAC_STRICT_MODE` configurable.

---

## Aspectos de Seguridad Correctamente Implementados

### Autenticación y Tokens
- **JWT HS256** con rotación de claves por `kid`, access tokens 15 min, refresh 30 días con JTI rotation — detección de reuso con revocación en cascada
- **bcrypt** para contraseñas y API keys (no hash reversible)
- **TOTP + WebAuthn** para MFA, desafíos con JTI únicos de 5 minutos consumibles
- **Bypass de superadmin** solo activo con 4 condiciones simultáneas: `ENABLE_SUPERADMIN_BYPASS=1`, `ENVIRONMENT=development`, `TESTING!=1`, URL de BD no-producción — múltiples capas de seguridad
- **`_JWT_RESERVED_CLAIMS`** previene inyección de claims reservados via `extra`
- **Anti-enumeración** en password reset (respuesta genérica, sin revelar existencia de usuario)

### Control de Acceso
- **RBAC + ABAC dual** — middleware ABAC fail-closed en errores inesperados
- **Aislamiento de tenant** — `organization_id` propagado a `db.info` en cada request via `get_current_user`
- **SCIM** — rechaza peticiones cuando `SCIM_BEARER_TOKEN` está vacío (HTTP 503), comparación constante con `hmac.compare_digest`

### Protección contra Ataques Web
- **Rate limiting** con slowapi + Redis obligatorio en producción (`RATE_LIMIT_REQUIRE_REDIS_IN_PRODUCTION=True`), UUID único por request en tests para evitar contaminación
- **Redis-backed login lockout** — bloqueo de cuentas tras intentos fallidos (configurable)
- **CSRF en SSO** — estado HMAC-SHA256 firmado, consumido una única vez, expira en 10 min
- **Open redirect** — `_validate_redirect_to` bloquea URLs externas y rutas `//`
- **SSRF en OIDC discovery** — `validate_https_discovery_url` bloquea IPs privadas + DNS rebinding
- **SSRF en provisión** — `_validate_provision_url` con idéntica protección
- **Proxy headers de confianza** — solo `X-Forwarded-For` de CIDRs configurados explícitamente (`TRUSTED_PROXY_CIDRS`); `TRUST_PROXY_HEADERS` desactivado por defecto

### Subida de Ficheros
- **Lista blanca de extensiones** + detección de **magic bytes** + verificación de que el MIME reclamado coincide con el detectado
- **Bloqueo de archivos comprimidos** (extensiones `.zip`, `.tar`, `.gz`, etc.)
- **SVGs** forzados a `Content-Disposition: attachment` para prevenir XSS inline
- **Path traversal** — `LocalFileStorage.get_file_bytes` verifica que la ruta resuelta está dentro del directorio de uploads raíz

### Webhooks y Comunicaciones Externas
- **Webhooks salientes** firmados con HMAC-SHA256 `X-Contecflow-Signature`
- **Webhooks GitHub/GitLab entrantes** rechazan peticiones cuando el secreto está vacío (fail-secure)
- **SMTP** con STARTTLS en puerto 587

### Cifrado de Campos
- **v2 (activo)** — HKDF con salt aleatorio de 16 bytes per-registro
- **KMS** — opción de sobre-cifrado con AWS KMS disponible

### Subprocess / Inyección de Comandos
- `subprocess.run` en `_run_cli` usa **lista de argumentos** (nunca `shell=True`) — sin inyección de comandos
- Lista blanca doble para Terraform: `ALLOWED_TERRAFORM_COMMANDS = {"plan", "apply", "destroy"}` validada a nivel de config Y a nivel de runtime policy

### Configuración
- `SECRET_KEY` — mínimo 32 caracteres, rechaza placeholders conocidos
- `DEFAULT_USER_PASSWORD` — rechaza placeholder, rechaza valor por defecto en staging/prod
- `WEBHOOK_SECRET` / `INBOUND_EMAIL_SECRET` — requerido en staging/prod, mínimo 24 caracteres

---

## Plan de Remediación

### Prioridad 1 — Aplicar Inmediatamente

**Fix SEC-006** — Añadir `_validate_provision_url(url)` antes de la petición httpx en el bloque `step.step_type == "webhook"` de `process_workflow_queue_record` en `app/services/bookings_service.py`.

**Fix SEC-007** — Implementar verificación del `id_token` firmado por el IdP en `process_oidc_callback`. Como mínimo, documentar que el endpoint requiere el `id_token` del IdP y añadir validación de firma JWKS.

### Prioridad 2 — Próximo Sprint

- **Fix SEC-008** — Añadir `IP_GEOLOCATION_ENABLED=false` como configuración con opt-in y soporte MaxMind local.
- **Fix SEC-009** — Crear job de migración v1→v2 de cifrado de campos.

### Prioridad 3 — Mejoras Futuras

- **SEC-010** — Añadir `ABAC_STRICT_MODE` configurable y documentar en DOCS.md.
- Añadir cabecera `Content-Security-Policy` en respuestas API.
- Evaluar HSTS a nivel de reverse proxy.
- Considerar migrar JWT de HS256 a RS256 para arquitecturas multi-servicio.

---

## Metodología

La auditoría cubrió los siguientes dominios en todos los ficheros del backend:

1. **Autenticación** — JWT, bcrypt, refresh tokens, MFA (TOTP, WebAuthn), API keys, lockout
2. **Autorización** — RBAC, ABAC middleware, dependencias FastAPI, aislamiento multi-tenant
3. **SSO / OAuth2 / OIDC** — CSRF de estado, redirect_uri, SSRF en discovery, callbacks, state management
4. **SAML** — stubs, firma de aserciones
5. **SCIM** — autenticación de token, bearer vacío
6. **Webhooks entrantes** — GitHub, GitLab, email entrante (INBOUND_EMAIL_SECRET)
7. **Webhooks salientes** — firma HMAC, workflows, automation steps
8. **Subida de archivos** — MIME, magic bytes, path traversal, SVG, archivos comprimidos
9. **Cifrado de campos** — v1 legacy PBKDF2, v2 HKDF, KMS envelope
10. **ML / modelos** — integridad HMAC, deserialización pickle/joblib
11. **Configuración** — secrets, placeholders, validadores de producción
12. **Inyección SQL** — uso de ORM SQLAlchemy, ausencia de SQL raw con input de usuario
13. **Inyección de comandos** — `subprocess.run` sin `shell=True`, whitelist Terraform/Ansible
14. **Privacidad / GDPR** — transferencias de datos a terceros (ipapi.co)

Se verificó la ausencia de `shell=True` en todos los `subprocess.run` del backend. Se verificó que las consultas dinámicas usan el ORM de SQLAlchemy parametrizado (sin interpolación de strings en SQL raw con input de usuario final). El único uso de `text(f"...")` en migrate.py usa variables de metadatos internos (nombres de columna/tabla obtenidos del schema, no de input de usuario).

---

*Documento actualizado en julio 2025 — revisión completa post-correcciones v2.*

- **SSRF en provisión** — `_validate_provision_url` con idéntica protección anti DNS-rebinding
- **Proxy headers de confianza** — solo `X-Forwarded-For` de CIDRs configurados explícitamente; `TRUST_PROXY_HEADERS` desactivado por defecto

### Subida de Ficheros
- **Lista blanca de extensiones** + detección de **magic bytes** + verificación de que el MIME reclamado coincide con el detectado
- **Bloqueo de archivos comprimidos** (extensiones `.zip`, `.tar`, `.gz`, etc.)
- **SVGs** forzados a `Content-Disposition: attachment` para prevenir XSS inline
- **Path traversal** — `LocalFileStorage.get_file_bytes` verifica que la ruta resuelta está dentro del directorio de uploads raíz

### Webhooks y Comunicaciones Externas
- **Webhooks salientes** firmados con HMAC-SHA256 `X-Contecflow-Signature`
- **Webhooks GitHub/GitLab entrantes** rechazan peticiones cuando el secreto está vacío (fail-secure)
- **SMTP** con STARTTLS en puerto 587

### Cifrado de Campos
- **v2 (activo)** — HKDF con salt aleatorio de 16 bytes per-registro
- **KMS** — opción de sobre-cifrado con AWS KMS disponible

### Subprocess / Inyección de Comandos
- `subprocess.run` en `_run_cli` usa **lista de argumentos** (nunca `shell=True`) — sin inyección de comandos
- Lista blanca doble para Terraform: `ALLOWED_TERRAFORM_COMMANDS = {"plan", "apply", "destroy"}` validada a nivel de config Y a nivel de runtime policy

### Configuración
- `SECRET_KEY` — mínimo 32 caracteres, rechaza placeholders conocidos
- `DEFAULT_USER_PASSWORD` — rechaza placeholder, rechaza valor por defecto en staging/prod
- `WEBHOOK_SECRET` / `INBOUND_EMAIL_SECRET` — requerido en staging/prod, mínimo 24 caracteres

---

## Plan de Remediación

### Prioridad 1 — Aplicar Inmediatamente

**Fix SEC-006** — Añadir `_validate_provision_url(url)` antes de la petición httpx en el bloque `step.step_type == "webhook"` de `process_workflow_queue_record` en `app/services/bookings_service.py`.

**Fix SEC-007** — Implementar verificación del `id_token` firmado por el IdP en `process_oidc_callback`. Como mínimo, rechazar payloads sin `id_token` y verificar su firma con las JWKS del IdP antes de aceptar el email.

### Prioridad 2 — Próximo Sprint

- **Fix SEC-008** — Añadir `IP_GEOLOCATION_ENABLED=false` como configuración con opt-in y soporte MaxMind local.
- **Fix SEC-009** — Crear job de migración v1→v2 de cifrado de campos.

### Prioridad 3 — Mejoras Futuras

- **SEC-010** — Añadir `ABAC_STRICT_MODE` configurable y documentar en DOCS.md.
- Añadir cabecera `Content-Security-Policy` en respuestas API.
- Evaluar HSTS a nivel de reverse proxy.
- Considerar migrar JWT de HS256 a RS256 para arquitecturas multi-servicio.

---

## Metodología

La auditoría cubrió los siguientes dominios en todos los ficheros del backend:

1. **Autenticación** — JWT, bcrypt, refresh tokens, MFA (TOTP, WebAuthn), API keys, lockout
2. **Autorización** — RBAC, ABAC middleware, dependencias FastAPI, aislamiento multi-tenant
3. **SSO / OAuth2 / OIDC** — CSRF de estado, redirect_uri, SSRF en discovery, callbacks, state management
4. **SAML** — stubs, firma de aserciones
5. **SCIM** — autenticación de token, bearer vacío
6. **Webhooks entrantes** — GitHub, GitLab, email entrante (INBOUND_EMAIL_SECRET)
7. **Webhooks salientes** — firma HMAC, workflows, automation steps
8. **Subida de archivos** — MIME, magic bytes, path traversal, SVG, archivos comprimidos
9. **Cifrado de campos** — v1 legacy PBKDF2, v2 HKDF, KMS envelope
10. **ML / modelos** — integridad HMAC, deserialización pickle/joblib
11. **Configuración** — secrets, placeholders, validadores de producción
12. **Inyección SQL** — uso de ORM SQLAlchemy, ausencia de SQL raw con input de usuario
13. **Inyección de comandos** — `subprocess.run` sin `shell=True`, whitelist Terraform/Ansible
14. **Privacidad / GDPR** — transferencias de datos a terceros (ipapi.co)

Se verificó la ausencia de `shell=True` en todos los `subprocess.run` del backend. Se verificó que las consultas dinámicas usan el ORM de SQLAlchemy parametrizado. El único uso de `text(f"...")` en `app/db/migrate.py` usa variables de metadatos internos del schema (no input de usuario final).

---

*Documento actualizado en julio 2025 — revisión completa post-correcciones v2.*
