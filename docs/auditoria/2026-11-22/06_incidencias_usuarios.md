# Incidencias de usuarios reales (23-11-2026)

Diez incidencias reportadas (la 2 vino vacía), probablemente sobre la versión
subida (`dd130072`). Cada una se ha buscado en el código ACTUAL (sin subir).
Tests nuevos: `tests/test_incidencias_usuarios_2026_11_23.py`,
`frontend/src/__tests__/incidenciasUsuarios20261123.test.ts`,
`frontend/src/__tests__/CambiosSinGuardar.test.tsx`,
`tests/test_restablecer_contrasena_2026_11_23.py`,
`frontend/src/__tests__/restablecerContrasenaPortal.test.ts`.

| # | Causa | ¿Ya corregida? | Arreglo |
|---|---|---|---|
| 1 | El modal de alta de ticket pedía siempre `GET /sd/dynamic-forms/history` (historial del asistente de campos, de administración: antes `require_admin`, ahora `sd.administrar`). Al operador le salía el 403 como aviso global. | Parcial: el texto del 403 ya salía traducido por código (`roles_requeridos`/`capacidad_requerida` en `err_srv`), pero la llamada seguía. | `CreateTicketModal.tsx`: la consulta solo se hace con `sd.administrar` (`enabled`) y sin aviso (`meta.errorToast=false`); el botón y el asistente de campos solo para quien administra. El alta ya no depende de ninguna ruta de administración. |
| 3 | Reglas dinámicas por defecto (`dynamic_forms_service._default_rules`) con etiqueta en castellano fijo, opciones `produccion/preproduccion/desarrollo` y pista `{queue: incident_l1}` pintadas en crudo; la pista además decía «aplicado» sin aplicar nada. | No. | `camposDinamicosSd.ts` traduce campos de serie, opciones y la cola (`sd_campos_dinamicos.*` en es/en/zh; `psd_*` en los 8 idiomas del portal); lo no traducido se muestra legible. Texto «Enrutado sugerido:» (ya no dice «aplicado»). Los valores guardados no cambian. |
| 4 | Modal/Drawer cerraban con clic fuera/Escape/X sin mirar cambios. | No. | Hook `useCambiosSinGuardar` en el kit, integrado en `useDialogo` (Modal, Drawer, PortalModal y diálogos propios); también enlaces internos y `beforeunload`. Ver `components/ui/DESIGN_SYSTEM.md`. |
| 5 | Idioma por defecto `es` en `AppLangProvider`, `idiomaSoportado`, `IDIOMA_POR_DEFECTO` del portal y en la base: `UserPreference.language`, `ClientUser.language` y `ClientPortalConfig.default_language` tenían de default `settings.DEFAULT_LANGUAGE` (castellano), que se guardaba como si fuera la elección del usuario. | No. | Orden: usuario > empresa > navegador (si se ofrece) > inglés. Front: `IDIOMA_DE_RESPALDO='en'`, `idiomaDelNavegador()`, `IDIOMA_POR_DEFECTO='en'` + `IDIOMA_FUENTE='es'`, `idiomaInicialDelPortal()`. Back: `por_empresa.idioma_elegido_de_empresa` (solo lo que la empresa eligió en Configuración, no el `.env`), preferencias y portal devuelven `null` si nadie eligió; las tres columnas sin default (siguen nulables: sin migración). |
| 6 | Operadores: existía, pero el enlace no era de un solo uso real (carrera), textos fijos, sin política visible, correo del límite en claro. Portal: no existía. Forzar: solo `force-password-change` sin motivo ni cierre de sesiones. | Parcial. | Ver `docs/seguridad/politicas_de_cuenta.md` §3 bis. |
| 7 | `client_portal.get_current_client` buscaba al cliente en una sesión sin empresa ni contexto de sistema: con `TENANT_SESION_SIN_CONTEXTO=cerrar` (por defecto desde el 23-11) `TenantIsolationError` → `/portal/auth/me` y las 41 rutas del portal daban 500 tras un login correcto. Además el cliente HTTP del portal no devolvía el testigo CSRF (con `CSRF_DOUBLE_SUBMIT=1`, 403 en toda escritura, incluido el cambio de contraseña obligatorio). | No. | Identificación dentro de `contexto_de_sistema` (como `deps.get_current_client`); `crearClienteDeApi` con credenciales añade `X-CSRF-Token`. **Requisito**: aplicar las migraciones 196-199 (la base local está en 195 y `client_users.must_change_password` no existe: cualquier consulta del portal falla hasta `setup.bat update`). |
| 8 | Configuración › Service desk › Correo entrante › «Credenciales» llevaba a `/settings/integrations` y abría el primer proveedor (SMTP), no el buzón. | No. | `IntegrationCredentialsSection` acepta `?sub=<proveedor>`; el botón va a `/settings/integrations?sub=sd_mailbox`; `SettingsPage` remonta la sección al cambiar `?sub`. Revisados todos los enlaces `/settings/...` de front y back (puesta en marcha incluida): todos existen (test). |
| 9 | `SSOConfig.provider` es `Enum(SSOProvider)` y guarda el NOMBRE (`azure`); el alta pasaba el VALOR `azure_ad` → `LookupError` → 500 (oidc/okta/google no fallaban: nombre = valor). | No. | `enterprise_service/sso.py`: proveedor como miembro del enum y `validar_entrada_sso` (discovery HTTPS sin marcadores y, en Entra ID, host de Microsoft con inquilino; client id GUID; secreto obligatorio para activar y cifrado; dominios normalizados; roles existentes en mapeo y por defecto; claim) con códigos `sso_*` (422). Auditoría del alta con id y secreto enmascarado. |
| 10 | La sonda `sd_mailbox` ya existía (`integration_test_service.py`, `_test_sd_mailbox` y `_PROBES`). Quedaba: resultados en texto fijo, etiquetas de campos en inglés, protocolo libre y números sin validar (un puerto no numérico rompía la lectura). | Sí la sonda; no el resto. | Resultados con `code`+`params` (`buzon_*`, `integracion_sin_prueba`, `integracion_desconocida`) traducidos con `textoDeResultado`; protocolo como desplegable imap/graph; etiquetas `integraciones_prov.*`; `set_credential` valida números, puerto y protocolo con código. |

## GRC

- Auditoría: alta de SSO auditada con su id y el secreto enmascarado (antes sin
  id); restablecimientos de contraseña auditados (ver §3 bis). Las credenciales
  de integración ya se auditaban (hash del cifrado) y no cambia.
- RGPD: el idioma deja de guardarse como «preferencia» si el usuario no lo
  eligió (minimización); filas existentes con `es` puesto por defecto se quedan
  (no se puede distinguir de una elección). Limpieza opcional, a decidir:
  `UPDATE user_preferences SET language=NULL WHERE language='es'` solo si se
  acepta perder elecciones explícitas de castellano.
- Retención y privilegios: sin cambios; el asistente de campos dinámicos sigue
  tras `sd.administrar`.

## Esquema

Ninguno. Las tres columnas de idioma ya eran nulables; solo cambia el default
de Python.
