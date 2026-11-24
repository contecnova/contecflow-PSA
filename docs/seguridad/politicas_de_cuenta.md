# Políticas de cuenta y seguridad de acceso

Revisión del 23-11-2026. Primero se midió lo que ya había (§1) y después se
completó (§2-§9). Referencias de mercado: NIST SP 800-63B (rev. 4),
ISO/IEC 27001:2022 A.5.15-A.5.18, A.8.2, A.8.5 y A.8.15, y CIS Controls v8
(5 y 6). En cada ajuste se indica el valor recomendado y si el valor por
defecto coincide con él.

## 1. Medición previa (antes de esta revisión)

Medido con grep y lectura del código el 23-11-2026.

| Control | ¿Existía? | Cómo | Qué faltaba |
|---|---|---|---|
| Longitud mínima y complejidad | Sí | `security.validate_password_policy`, ajustes `MIN_PASSWORD_LENGTH` y `PASSWORD_REQUIRE_*` (grupo `password_policy`, por empresa) | Longitud máxima, lista de contraseñas comunes, contraseñas con el usuario o el correo |
| Caducidad de contraseña | No | — | Fecha de último cambio, caducidad en días, aviso previo y cambio forzado al entrar |
| Historial de contraseñas | No | — | Tabla de hashes y comprobación de las N últimas |
| Cambio forzado por el administrador | No | — | Marca por usuario y para toda la empresa |
| Contraseñas temporales | No | — | Caducidad de la contraseña que pone un administrador |
| Auditoría del cambio de contraseña | Parcial | `PASSWORD_RESET_*` en `audit_log`; `POST /auth/change-password` no auditaba | Registrar el cambio propio con actor, IP y empresa |
| Bloqueo por intentos | Sí | Cubetas `usuario|IP` y por cuenta en Redis o en memoria (`auth_service/estado_efimero.py`); ajustes `LOGIN_MAX_ATTEMPTS`, `LOGIN_ATTEMPT_WINDOW_SECONDS` y `LOGIN_LOCKOUT_SECONDS` | Se leían solo en el ámbito global (no por empresa); no había bloqueo persistente, desbloqueo por administrador ni aviso al usuario. La IP del cubo era `request.client.host` (la del proxy tras nginx) |
| MFA TOTP | Sí | `users.mfa_secret` cifrado, `mfa_last_timestep` contra reutilización, reto con contador (`auth_mfa.py`) | — |
| MFA WebAuthn / passkeys | Sí | `webauthn_credentials`, acceso sin contraseña opcional (`PASSKEY_PASSWORDLESS_ENABLED`) | — |
| Códigos de recuperación | Sí | `mfa_backup_codes` con bcrypt, un solo uso | — |
| MFA obligatorio por empresa | Sí | `organizations.require_mfa`, bloquea el login sin factor | Obligatorio por rol o por capacidad sensible, métodos permitidos, periodo de gracia |
| Restablecer el MFA de otro (admin) | No | — | Endpoint auditado, con segundo administrador si se exige |
| Quitarse el propio MFA | Sí, sin freno | `POST /auth/mfa/disable` con código | Impedirlo si la política lo exige |
| Recordar dispositivo | No | — | Cookie firmada y revocable que evita el reto MFA durante N días |
| Sesiones activas del usuario | Sí | `user_sessions`, `GET /auth/sessions/active`, revocar una o todas | Lista y cierre por el administrador; el token de acceso seguía valiendo hasta caducar (15 min) tras revocar |
| Inactividad | Parcial | Solo en el navegador (`idle_timeout_enabled`, `idle_timeout_minutes`) | Aplicarlo en el servidor |
| Duración máxima de la sesión | Parcial | Duración del refresco (`REFRESH_TOKEN_EXPIRE_DAYS`) | Tope absoluto desde el inicio de sesión |
| Sesiones concurrentes | No | — | Máximo por usuario |
| Cierre al cambiar contraseña | Sí | `revocar_sesiones_del_usuario` | — |
| Cierre al desactivar | Parcial | `get_current_user` rechaza al inactivo, pero sus filas de sesión seguían vivas | Revocarlas al desactivar, venga de donde venga |
| IP permitidas | No | (`TRUSTED_PROXY_CIDRS` es otra cosa: proxies de confianza) | Lista de IP o CIDR por empresa |
| Horario de acceso | No | — | Franja y días por empresa |
| Bloqueo por país | No | Geolocalización por IP opcional (`GEOIP_LOOKUP_ENABLED`, apagada por defecto) solo para el riesgo de la sesión | Lista de países bloqueados que solo actúa si hay país conocido |
| `ENABLE_SUPERADMIN_BYPASS` | Sí, acotado | Apagado por defecto; ocho condiciones (desarrollo, SQLite...); el arranque se niega fuera de desarrollo | No dejaba rastro en `audit_log` ni avisaba al arrancar |
| SSO OIDC / SAML y SCIM | Sí | `auth_sso.py`, `auth_saml.py`, `scim.py` | Fuera del alcance de esta revisión |
| Auditoría de login | Sí | `LOGIN` en `audit_log`, eventos SOC (`security_events`), anomalías (`login_anomalies`) | Alertas al administrador |
| Alertas de seguridad | Parcial | Detecciones del SOC (`security_detections`) | Aviso en la campana al administrador: fallos masivos, IP nueva, MFA desactivado, cambio de política, bloqueo |
| Informe de cumplimiento | Sí | `informe_de_cumplimiento.py`: cobertura MFA, política, inactividad, cuentas dormidas, administradores, cadena | Contraseñas caducadas, cuentas bloqueadas, privilegios elevados con detalle, revisión periódica de accesos, bypass |
| Revisión periódica de accesos | No | — | Campañas de recertificación por responsable con evidencia |
| Desactivación de cuentas inactivas | No | Solo el aviso del informe (`COMPLIANCE_STALE_ACCOUNT_DAYS`) | Desactivación automática opcional |
| Inmutabilidad de `audit_logs` | No | Cadena HMAC + Ed25519 (`cadena_auditoria.py`) que detecta cambios, pero nada los impedía | Trigger en Postgres y SQLite que niega UPDATE y DELETE (hallazgo B.1 del informe 05) |
| Separación de funciones en seguridad | No | — | Segundo administrador para cambios de política y restablecimientos de MFA si la empresa lo exige |

## 2. Dónde se configura

**Configuración › Seguridad › Seguridad de cuentas** (`/settings/seguridad-cuentas`), con la
capacidad `seguridad.administrar` (rol `admin`). Todo es **por empresa**. Los ajustes viven en el
registro en vivo (grupos `password_policy` y `account_security`). Solo se escriben por
`PUT /api/v1/security/policy`, que valida, aplica la separación de funciones y audita. El editor
genérico de ajustes en vivo rechaza esos dos grupos (`ajuste_grupo_de_seguridad`).

La recertificación de accesos tiene su propia sección (**Configuración › Seguridad ›
Recertificación de accesos**). Los responsables la abren con `seguridad.recertificar`, que
tienen los roles `admin`, `pm`, `team_lead` y `hr`.

## 3. Contraseñas

| Ajuste | Defecto | Recomendado | Notas |
|---|---|---|---|
| `MIN_PASSWORD_LENGTH` | 8 | 15 sin MFA, 8 con MFA (NIST 800-63B-4 §3.1.1.2) | Ya existía |
| `PASSWORD_MAX_LENGTH` | 128 | ≥ 64 (NIST) | Nuevo. Tope 1024 |
| `PASSWORD_REQUIRE_UPPERCASE/LOWERCASE/DIGIT/SPECIAL` | sí | **no** (NIST desaconseja reglas de composición) | Ya existían; se conservan por compatibilidad |
| `PASSWORD_BLOCK_COMMON` | sí | sí (NIST «blocklist») | Lista **local** (`app/services/seguridad_de_cuentas/comunes.txt`) más patrones triviales. No se envía nada a terceros |
| `PASSWORD_BLOCK_PERSONAL` | sí | sí | Rechaza la que contiene el usuario, la parte local del correo o el nombre |
| `PASSWORD_HISTORY_COUNT` | 5 | 5-24 (CIS) | Hashes bcrypt de las N últimas (`password_history`); 0 = sin historial |
| `PASSWORD_MIN_AGE_HOURS` | 0 | 0, o 24 si hay historial (CIS) | Impide encadenar cambios para vaciar el historial |
| `PASSWORD_EXPIRY_DAYS` | 0 | **0** (NIST: no caducar salvo indicio de compromiso) | Al caducar, el usuario entra pero solo puede cambiarla |
| `PASSWORD_EXPIRY_WARNING_DAYS` | 14 | 14 | Aviso en la pantalla y en la campana |
| `TEMP_PASSWORD_EXPIRY_HOURS` | 72 | 24-72 | Contraseña temporal puesta por un administrador: obliga a cambiarla y caduca |

Acciones del administrador: forzar el cambio a un usuario o a todos, poner una contraseña temporal
y desbloquear. Todo queda en `audit_log` (`PASSWORD_CHANGE_FORCED`, `PASSWORD_CHANGE_FORCED_ALL`,
`PASSWORD_TEMPORARY_SET`, `ACCOUNT_UNLOCKED`, `PASSWORD_CHANGED`).

**Portal de clientes.** Al cambiar la contraseña en el portal se aplica la misma política de la
empresa del cliente (`contrasenas.validar_del_portal`, llamada desde
`client_portal_service/clientes.py`): la longitud mayor entre la de la empresa y la del portal,
la complejidad, las comunes y los datos personales. No hay historial, porque el portal no lo
guarda. Los errores salen con códigos propios del portal en sus 8 idiomas
(`portal_contrasena_comun`, `portal_contrasena_con_datos_personales` y
`portal_contrasena_no_cumple_politica`). El cambio obligatorio en el primer acceso es de la
migración 198 (`client_users.must_change_password`), de otra tarea.

## 3 bis. Restablecimiento de contraseña («¿Olvidaste tu contraseña?»)

23-11-2026, incidencia de usuario «No hay función de restablecer contraseña para los usuarios».
Piezas comunes en `app/services/seguridad_de_cuentas/restablecimiento.py`.

**Medición previa.**
- Operador: existían `POST /auth/password/forgot` y `/auth/password/reset`, el enlace en el login
  y `ResetPasswordPage`. Fallaban en cuatro cosas:
  - el `jti` se comprobaba y se borraba en dos pasos, así que dos peticiones simultáneas con el
    mismo enlace pasaban las dos;
  - el aviso y los errores del formulario «olvidé» salían en castellano (texto del servidor);
  - la pantalla no enseñaba la política y el correo solo estaba en castellano;
  - el cubo del límite de intentos guardaba el correo tecleado en claro.
- Portal de clientes: no había nada. Solo «Reenviar acceso» del equipo, que genera una
  contraseña.
- Restablecimiento forzado: solo existía «forzar cambio», sin motivo, sin cerrar sesiones y sin
  enlace.

**Flujo (operador y portal).**
1. Enlace «¿Olvidaste tu contraseña?» en el login. Se escribe el correo (el operador también
   puede escribir el usuario).
2. La respuesta es siempre la misma y tarda parecido (`igualar_tiempo`: suelo de 0,45 s más
   azar). Hay límite de 5/min por IP y de 5 por 15 min por cubo `hash(identificador)|IP`.
3. Si la cuenta existe, está activa y tiene contraseña local, se emite un token firmado de un
   solo uso. Caduca a los 30 min y uno nuevo invalida el anterior (el `jti` vigente va en Redis,
   con respaldo en memoria). Se encola el correo en el idioma del destinatario
   (`restablecer.*` en `textos_de_salida_servicios_m_z.py`: 8 idiomas).
4. La pantalla de nueva contraseña pide las reglas (`/auth/password/reset/policy`,
   `/portal/auth/password/policy`) sin consumir el token y quita el token de la barra de
   direcciones.
5. Al guardar se aplica la política de la empresa:
   - operador: `validar_nueva`, con historial y sin edad mínima;
   - portal: `validar_del_portal`, sin historial y distinta de la actual.

   Después se reclama el `jti` en una sola operación (`reclamar_jti`, script Lua) y se cierran
   TODAS las sesiones:
   - operador: refrescos en `user_sessions` (`password_reset`), que cortan en la siguiente
     petición;
   - portal: corte por cliente (`cerrar_sesiones_del_portal`), con el que
     `token_de_cliente_revocado` rechaza los JWT del portal emitidos antes. Sin esquema nuevo.

   El operador queda además desbloqueado (cubos y `locked_until`). En el portal se quita
   `must_change_password`.

**Enlace del portal.** El enlace va a `<base>/portal/reset-password?token=…&lang=…`. La base es
el dominio propio activo de la empresa (`OrgBranding.custom_domain`, si tiene el portal activo)
o `FRONTEND_URL`. Nunca se toma de la cabecera `Host` de la petición, para evitar el
envenenamiento del enlace.

**Restablecimiento forzado (administrador).**
- Operador: `POST /security/users/{id}/force-password-reset` con `seguridad.administrar`
  (Ajustes › Seguridad de cuentas › Usuarios › «Forzar restablecimiento»).
- Portal: `POST /portal/clients/{id}/force-password-reset` con `clientes.gestionar` (ficha del
  cliente › usuarios del portal).

En los dos, el motivo es obligatorio. Se marca el cambio obligatorio, se cierran todas las
sesiones y, por defecto (`send_link`), se manda el enlace. Nadie se lo puede forzar a sí mismo
(`separacion_de_funciones_misma_persona`), y una cuenta SSO no tiene contraseña que forzar
(`cuenta_sso_sin_contrasena`).

**Auditoría.** Todo va a `audit_log` con IP, agente y empresa:

| Acción | Actor | Recurso |
|---|---|---|
| `PASSWORD_RESET_REQUEST` | el propio usuario | `users` |
| `PASSWORD_RESET_COMPLETE` | el propio usuario | `users` |
| `PASSWORD_RESET_FORCED` | el administrador | `users`, con motivo, enlace enviado y sesiones revocadas |
| `PORTAL_PASSWORD_RESET_REQUEST` | sistema | `client_user` |
| `PORTAL_PASSWORD_RESET_COMPLETE` | sistema | `client_user` |
| `PORTAL_PASSWORD_RESET_FORCED` | el miembro del equipo | `client_user`, con motivo |

**RGPD y retención.**
- Si la cuenta no existe, no se apunta nada: ni auditoría ni log con lo tecleado. El cubo del
  límite de intentos lleva el hash (SHA-256 truncado), no el correo.
- Los logs de fallo de SMTP no llevan el destinatario.
- El estado es efímero en Redis o memoria y no se guarda en base de datos:
  - `jti`: 30 min;
  - cubos: 15 min;
  - corte de sesiones del portal: la vida del token del portal (`CLIENT_TOKEN_EXPIRE_HOURS`)
    más 2 min.
- Las entradas de auditoría siguen la retención del registro de auditoría (§10).

**Errores con código.**
- Operador: `reset_token_no_valido`, `recuperacion_demasiadas_solicitudes` y los `contrasena_*`.
- Portal (8 idiomas): `portal_reset_token_no_valido`,
  `portal_recuperacion_demasiadas_solicitudes`, `contrasena_corta`, `portal_contrasena_*` y
  `portal_contrasena_igual_a_la_anterior`.

**Límite conocido.** El JWT del portal no lleva `iat`. La emisión se deduce de
`exp − CLIENT_TOKEN_EXPIRE_HOURS`, así que un token emitido en el mismo segundo que el corte
sigue valiendo (es el login justo después del restablecimiento).

Pruebas: `tests/test_restablecer_contrasena_2026_11_23.py` y
`frontend/src/__tests__/restablecerContrasenaPortal.test.ts`.

## 3 ter. Portal de clientes: contraseña a mano, eliminar y archivar (23-11-2026)

Petición del usuario: poder poner a mano la contraseña de un usuario del portal y poder borrar
usuarios del portal; si tienen cosas hechas, archivarlos en vez de borrarlos. Antes, por la
revisión M10 del 04b, el equipo no podía escribir la contraseña (solo «Reenviar acceso», que la
genera y la manda por correo), y «Eliminar» borraba siempre: las filas de negocio que apuntaban
al usuario se quedaban sin autor (`ON DELETE SET NULL`).

**Quién.** Las acciones las tiene quien tiene `clientes.gestionar`, la capacidad que ya gestionaba
los usuarios del portal. No se ha abierto a más roles. La supresión RGPD la sigue pidiendo solo
quien tiene `cab.administrar`. Cada acción comprueba además que el usuario del portal sea de la
empresa de quien actúa; si no, responde 404.

**Contraseña a mano.** Hay dos caminos:
- en el alta (pestaña «Usuarios del portal», alta desde un contacto con «Dar acceso al portal» y
  página del portal de clientes), eligiendo «Ponerla a mano»;
- en cualquier momento después, con «Establecer contraseña»
  (`POST /portal/clients/{id}/set-password`).

Cómo funciona:
- El campo tiene mostrar/ocultar, un botón para generar una aleatoria de 20 caracteres
  (mayúsculas, minúsculas, dígitos y especiales, sin caracteres que se confundan) y otro para copiarla.
- Hay dos casillas:
  - «Obligar a cambiarla en el primer acceso» va marcada por defecto y pone
    `client_users.must_change_password`. En la API, si no se manda el campo en el alta, no obliga
    (como antes); en `set-password`, por defecto sí obliga.
  - «Enviar el acceso por correo al titular» usa el correo de siempre (`portal.acceso.*`, en
    los 8 idiomas del portal).
- La contraseña pasa la política de la empresa
  (`usuarios.validar_puesta_por_el_equipo`):
  - longitud mínima: la mayor entre la de la empresa y `MIN_PASSWORD_LENGTH`;
  - longitud máxima y composición;
  - comunes;
  - datos personales: ni el correo ni el nombre del usuario del portal;
  - distinta de la actual. El portal no guarda historial de contraseñas, así que la actual es
    todo su historial.
  - Los errores llevan el código del operador (es/en/zh): `contrasena_*`,
    `portal_usuario_contrasena_con_datos_personales` y
    `portal_usuario_contrasena_igual_a_la_actual`.
- La contraseña solo se guarda con hash (bcrypt). No vuelve en ninguna respuesta. No va a los logs.
  No va a la auditoría.
- Al establecerla se cierran todas las sesiones del portal de ese usuario (corte por cliente de §3 bis
  y borrado de sus `client_sessions`).
- Auditoría:
  - `PORTAL_PASSWORD_SET` con quién, a quién, IP, `must_change_password`, `send_requested`,
    `sent` y `sessions_revoked`;
  - en el alta, `PORTAL_USER_CREATED` con `password_manual`, `must_change_password` y `sent`.
- «Reenviar acceso» se mantiene como alternativa: el sistema genera la contraseña y se la manda
  al titular.
- Editar el usuario (`PATCH /portal/clients/{id}`) ya no cambia la contraseña: antes lo hacía sin
  política, sin cerrar sesiones y sin auditoría. Ahora responde
  `portal_usuario_contrasena_solo_con_su_accion`.

**Eliminar o archivar** (`DELETE /portal/clients/{id}`). Decide el servidor
(`usuarios.eliminar_o_archivar`):
- **Criterio de historial.** Se miran todas las claves ajenas a `client_users.id` que declaran
  los modelos; la lista se saca de los modelos, no se escribe a mano. Hoy son:
  - tickets (solicitante, actor del historial, autor de comentarios);
  - mensajes del portal;
  - peticiones de funcionalidad;
  - UAT (firma e incidencias);
  - encuestas;
  - documentos firmados;
  - demanda (solicitudes, actores, comentarios, adjuntos);
  - conversaciones del portal y de colaboración (mensajes, adjuntos, llamadas, reacciones,
    canales directos, auditoría de colaboración);
  - conversaciones de canal y acciones del asistente del service desk;
  - sesiones del chat de IA del portal.

  Solo NO cuentan como historial (`NO_SON_HISTORIAL`):
  - los permisos de proyecto (`client_user_projects`);
  - las sesiones (`client_sessions`);
  - su ficha de contacto (`client_contacts`, que se queda, sin enlace);
  - lo que ha leído, sus avisos, su presencia y sus suscripciones push;
  - las conversaciones en las que es miembro;
  - las menciones que le hicieron.

  Una tabla nueva que apunte al usuario cuenta como historial por defecto, que es lo seguro.
- **Sin historial: se borra de verdad.** Antes se borran sus filas accesorias y se desenlaza su
  contacto. Así ninguna cascada llega a datos de negocio, porque si existieran, sería historial.
  Se audita `PORTAL_USER_DELETED`, con su nombre y correo en `old_values`.
- **Con historial: se archiva.**
  - `is_active=False`, `archived_at` y `archived_by` (migración `205_portal_usuarios`).
  - No puede entrar, porque el login y cada petición exigen `is_active`.
  - Se cierran sus sesiones y se borran sus suscripciones push y su presencia.
  - Sale de las listas por defecto; se ve con «Ver archivados» (`include_archived=true`).
  - Conserva su historial con su nombre.
  - Se audita `PORTAL_USER_ARCHIVED` con el recuento por `tabla.columna`.
  - La respuesta dice `resultado` (`eliminado` o `archivado`), `historial` y `total`, y la
    pantalla lo explica.
- Un archivado:
  - no se reactiva con «Reactivar»;
  - no recibe contraseña ni reenvío de acceso;
  - no se puede volver a dar de alta con su correo (`portal_usuario_archivado`,
    `portal_usuario_email_archivado`).
- **Restaurar** (`POST /portal/clients/{id}/restore`):
  - respeta el tope de usuarios del portal del cliente;
  - vuelve a entrar con su contraseña;
  - se audita `PORTAL_USER_RESTORED`.

**Distinto de la supresión RGPD.** Eliminar o archivar no es la supresión del art. 17. La
supresión anonimiza la ficha de contacto y el usuario del portal
(`datos_personales_de_contactos.anonimizar`). En la ficha hay una acción aparte, «Supresión RGPD»,
solo para `cab.administrar`. Crea la solicitud de supresión para ese correo, que se procesa en
Enterprise › RGPD.

**GRC.**
- Retención: el archivado conserva el historial mientras la empresa lo necesite. Para borrar los
  datos personales está la supresión RGPD.
- Privilegios: no cambian; sigue siendo `clientes.gestionar`.
- El borrado definitivo solo ocurre cuando no hay nada que conservar.
- Esquema: `client_users.archived_at`, de tipo fecha con zona y nula; `client_users.archived_by`,
  de tipo texto de 36 caracteres y nula. `archived_by` no tiene clave ajena: el rastro completo está
  en `audit_log`.

**Interfaz.**
- `frontend/src/pages/clients/AccionesUsuarioPortal.tsx` reúne los `IconButton variante="caja"`
  de «Establecer contraseña», «Reenviar acceso», «Eliminar o archivar», «Restaurar» y
  «Supresión RGPD», con sus confirmaciones.
- Se usa en la pestaña de usuarios del portal, en los contactos del cliente y en la página del
  portal de clientes.
- Los textos del operador están en es/en/zh (`portalacc.*`). El cliente del portal no ve textos
  nuevos: el correo de acceso y la pantalla de cambio obligatorio ya existían en los 8 idiomas.

Pruebas: `tests/test_portal_usuarios_contrasena_y_archivo.py`.

## 4. Bloqueo de cuenta

| Ajuste | Defecto | Recomendado |
|---|---|---|
| `LOGIN_MAX_ATTEMPTS` | 5 | ≤ 10 (CIS 6.x) y ≤ 100 (NIST 800-63B §3.2.2) |
| `LOGIN_ATTEMPT_WINDOW_SECONDS` | 900 | 900 |
| `LOGIN_LOCKOUT_SECONDS` | 900 | 900 |
| `LOGIN_LOCKOUT_NOTIFY_USER` | sí | sí |

Se sigue usando el cubo `usuario|IP` y el de la cuenta, y ahora se leen con la política de la
empresa del usuario. El bloqueo de la cuenta además se guarda en `users.locked_until`, que vale
para todos los procesos aunque Redis no esté. El administrador desbloquea desde la sección; eso
borra los cubos y `locked_until`. Al bloquearse, el usuario recibe un aviso y el administrador
una alerta.

## 5. MFA

| Ajuste | Defecto | Recomendado |
|---|---|---|
| `organizations.require_mfa` (toda la empresa, **sin gracia**: sin factor no se entra, como antes) | no | sí (ISO A.8.5, CIS 6.3-6.5) |
| `MFA_REQUIRED_ROLES` | `admin` | `admin` como mínimo |
| `MFA_REQUIRED_FOR_SENSITIVE` | sí | sí: quien tenga una capacidad sensible (`CAPACIDADES_SENSIBLES`) |
| `MFA_ALLOWED_METHODS` | `totp,webauthn` | `webauthn` resiste el phishing (NIST AAL3) |
| `MFA_GRACE_DAYS` | 7 | 0-14 |
| `MFA_REMEMBER_DEVICE_DAYS` | 0 | 0-30 |

- **Periodo de gracia.** La primera vez que el login ve a alguien obligado sin segundo factor,
  apunta `users.mfa_grace_started_at`. Durante la gracia entra con un aviso y fecha límite.
  Pasada la gracia, la API solo le deja configurar el MFA (`mfa_configuracion_obligatoria`).
- **Métodos.** Un método no permitido no cuenta como segundo factor ni se puede registrar.
- **Recuperación.** 8 códigos de un solo uso con hash bcrypt (`mfa_backup_codes`).
- **Restablecer el MFA de otro.** `POST /security/users/{id}/reset-mfa` borra TOTP, passkeys,
  códigos y dispositivos de confianza. Revoca sus sesiones y queda auditado (`MFA_RESET_BY_ADMIN`).
- **Quitarse el propio MFA.** Si la política lo exige y no queda otro factor, se niega
  (`mfa_obligatorio_no_desactivable`). Hay que pedirlo a un administrador.
- **Recordar dispositivo.** Cookie `trusted_device` httpOnly. En la base solo va el SHA-256 del
  token (`trusted_devices`). El usuario lo revoca en su página de MFA y el administrador al
  restablecer el MFA.

## 6. Sesiones

| Ajuste | Defecto | Recomendado |
|---|---|---|
| `idle_timeout_enabled` / `idle_timeout_minutes` (ajuste general, ya existía) | no / 30 | sí / 15-30 (NIST AAL2: 30 min) |
| `SESSION_MAX_HOURS` | 0 (sin tope) | 12-24 (NIST AAL2: 24 h) |
| `SESSION_MAX_CONCURRENT` | 0 (sin tope) | 3-5 |

- El token de acceso lleva `sid`, la clave estable de la sesión (`user_sessions.session_key`).
  `get_current_user` comprueba en cada petición que la sesión no está revocada, ni inactiva más
  de lo permitido, ni pasada de su tope. Revocar corta en el acto, sin esperar a que caduque el
  token. La marca `last_seen_at` se escribe como mucho una vez por minuto.
- Al pasar el máximo de sesiones concurrentes se cierra la más antigua (`concurrent_limit`).
- **Cierre de todas:** al cambiar o restablecer la contraseña (menos la actual), al
  desactivar al usuario por cualquier vía (`before_flush` en `app/db/revocar_al_desactivar.py`),
  al restablecer su MFA y por orden del administrador.
- El administrador ve las sesiones activas de la empresa y cierra una o todas las de un usuario
  (`SESSION_REVOKED_BY_ADMIN`).

## 7. Acceso

| Ajuste | Defecto | Notas |
|---|---|---|
| `ACCESS_IP_ALLOWLIST` | vacío (cualquiera) | IP o CIDR separados por comas. Se comprueba al abrir sesión y en cada petición |
| `ACCESS_HOURS` / `ACCESS_DAYS` | vacío / `1,2,3,4,5,6,7` | `HH:MM-HH:MM` en la zona horaria de la empresa; admite cruzar la medianoche |
| `ACCESS_HOURS_EXEMPT_ROLES` | `admin` | Para que un administrador no se quede fuera |
| `ACCESS_BLOCKED_COUNTRIES` | vacío | ISO-3166 alfa-2. **Solo actúa si se conoce el país:** cabecera de país de un proxy de confianza (`CF-IPCountry`) o `GEOIP_LOOKUP_ENABLED=1`, que está apagado por defecto porque manda la IP a un tercero (ver `entrada_y_salida.md`) |

**Excepción del superadmin.** El superadmin de plataforma no tiene empresa en su sesión. No le
afectan la lista de IP, el horario ni el país de ninguna empresa. Lo mismo vale cuando «entra
como» un usuario, porque el token lo firma su sesión. Es deliberado: es la vía de recuperación si
una empresa se deja fuera. Su protección es la de la plataforma: MFA propio, `ENABLE_SUPERADMIN_BYPASS`
apagado y auditoría de «entrar como». Antes de guardar, la sección comprueba que la IP de quien
guarda queda dentro de la lista (`ip_fuera_de_la_lista`) para que el administrador no se cierre
la puerta a sí mismo.

## 8. Superadministrador y `ENABLE_SUPERADMIN_BYPASS`

- Apagado por defecto (`proceso_config.py`). El arranque se niega fuera de `development` o sin SQLite.
- **Nuevo:** al arrancar con el bypass encendido se deja un aviso CRITICAL. Cada uso queda en
  `audit_log` como `SUPERADMIN_BYPASS_LOGIN`, con IP, y como evento SOC. El informe de
  cumplimiento lo mide (`superadmin_bypass`).

## 9. Alertas, informe y recertificación

**Alertas** (campana del administrador, `notify_role("admin", organization_id=...)`, tipo `security_alert`):

- fallos masivos: `SECURITY_ALERT_FAILED_LOGINS` fallos en 15 minutos en la empresa (defecto 20);
- entrada desde una IP nueva para ese usuario (`SECURITY_ALERT_NEW_IP`);
- MFA desactivado o restablecido;
- cambio de política;
- cuenta bloqueada.

Se usan los avisos existentes (`notifications`, con textos en es, en y zh en `textos_de_salida`).

**Informe de cumplimiento** (`GET /grc/compliance-report`, firmado y exportable). Controles nuevos:

- `mfa_policy`
- `passwords_expired`
- `password_policy_strength`
- `accounts_locked`
- `privileged_accounts` (con cobertura MFA de los privilegiados)
- `inactive_accounts_auto_disable`
- `session_limits`
- `access_restrictions`
- `access_review` (última campaña cerrada dentro de `ACCESS_REVIEW_INTERVAL_DAYS`)
- `superadmin_bypass`
- `audit_log_immutable`

**Recertificación de accesos.** El administrador abre una campaña. Por cada usuario activo se crea
un elemento con la foto de su acceso: rol, rol personalizado, capacidades, MFA y último acceso. Se
asigna a su responsable (`manager_id`, o el administrador que abre la campaña si no lo tiene). El
responsable decide «mantener», «revocar» o «modificar» con un comentario obligatorio, que es la
evidencia. Al cerrar la campaña, los «revocar» desactivan la cuenta, si el administrador lo pide.
Se exporta en CSV o JSON (`ACCESS_REVIEW_EXPORTED`).

**Desactivación de inactivas.** Con `ACCOUNT_INACTIVE_DISABLE_DAYS` > 0, el trabajo diario
`seguridad-de-cuentas-diario` desactiva las cuentas sin acceso en ese plazo
(`ACCOUNT_AUTO_DISABLED`), avisa de la caducidad de contraseñas y caduca los dispositivos de
confianza. No se aplica a superadmins ni a cuentas creadas dentro del plazo.

## 10. GRC

- **Capas (prueba global 23-11-2026).** Las rutas de `/security` solo resuelven la guarda, la
  empresa activa y el origen; cada acción (consultar, escribir, auditar y confirmar) vive en
  `app/services/seguridad_de_cuentas/administracion.py`, y las del portal («¿Olvidaste tu
  contraseña?», restablecer, forzar) en `restablecimiento.py` (`pedir_en_el_portal`,
  `restablecer_en_el_portal`, `forzar_en_el_portal`). Misma auditoría, mismos códigos de error.
- **Auditoría.** Todas las acciones nuevas van a `audit_log` con actor, IP, agente y empresa
  (`auditar()` en `seguridad_de_cuentas/auditoria.py`).
- **Inmutabilidad.** La migración 199 instala triggers (`app/db/auditoria_inmutable.py`) en
  Postgres (`plpgsql`) y en SQLite (`RAISE(ABORT)`). Niegan el DELETE y el UPDATE de cualquier
  columna salvo:
  - poner `user_id` a NULL (la clave ajena es `ON DELETE SET NULL` y `user_id` no entra en la huella);
  - encadenar filas antiguas sin `seq` (`encadenar_existentes`).

  La purga de una empresa tras su cuarentena (`baja_de_empresa_service.purgar`) es el único
  borrado. Para ello abre un permiso en `audit_log_purge_permits` dentro de la misma transacción
  y lo cierra al terminar.
- **Retención** (`bloqueo_legal.TIPOS`):
  - `password_history` (desde el alta);
  - `trusted_devices` (revocados o caducados);
  - `security_change_requests` (decididas);
  - `access_review_campaigns` (cerradas, con sus elementos en cascada).

  `user_sessions`, `security_events` y `login_anomalies` ya estaban. El registro de auditoría no
  tiene tipo de retención a propósito: se conserva mientras exista la empresa (RGPD art. 17.3.b y
  e) y se exporta firmado.
- **RGPD.** La copia del interesado lleva su estado de seguridad: fechas de cambio, MFA,
  dispositivos de confianza, sesiones y elementos de recertificación. Las contraseñas y los hashes
  no se incluyen nunca. La supresión borra `password_history` y `trusted_devices`, que entran en
  el patrón de credenciales de `supresion_service`.
- **Separación de funciones** (`SECURITY_SOD_TWO_ADMINS`, defecto no; recomendado sí con 2 o más
  administradores). Con ella:
  - un cambio de política o un restablecimiento de MFA crea una solicitud (`security_change_requests`)
    que aplica otro administrador;
  - nadie aprueba la suya ni restablece su propio MFA.

  Sin segundo administrador activo, la solicitud no se puede aprobar. Lo arregla el superadmin.
- **Matriz GRC.** La capacidad `seguridad.administrar` está en el catálogo y en la sonda. Las rutas
  `/api/v1/security/*` pasan por la matriz GRC y ABAC de `get_current_user`.

Pruebas: `tests/test_seguridad_de_cuentas_2026_11_23.py`.
