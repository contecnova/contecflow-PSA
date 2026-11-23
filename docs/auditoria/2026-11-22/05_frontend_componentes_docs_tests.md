# Auditoría 2026-11-22 · 05 · Frontend (sin páginas), documentación y tests

Auditoría de **solo lectura**: no se ha tocado código, no se ha hecho commit y no se han ejecutado tests ni lint. Las mediciones salen de `git ls-files`, `git grep` y scripts de Node de un solo uso (en el directorio temporal, fuera del repo) que leen los ficheros versionados. Lo que no se ha comprobado lleva la marca «sin verificar».

## Resumen

| Zona | Medido | Estado |
|---|---|---|
| `frontend/src/components` | 353 ficheros versionados (248 .tsx/.ts sin contar tests). Ficheros sin ningún import: 0 | Sano. Sin componentes muertos a nivel de fichero |
| `frontend/src/hooks` | 49 ficheros. **~170 hooks exportados que nadie usa** fuera de tests (de 184 exports muertos en hooks/utils/services/ui) | Capa de hooks de React Query casi muerta |
| `services/api` | `_core.ts` tiene 1.951 líneas. Un solo `axios.create` operador, más `clienteBase` para el portal y las vistas públicas | Bien encauzado, con 3 fallos de sesión y CSRF (ver A.1) |
| i18n operador (es/en/zh) | 22.898 claves en es. **A en y zh les faltan 3** (`demanda.retirar`, `demanda.retirada`, `demanda.motivo_retirada`). Hay 2 claves usadas que no están definidas | Casi completo |
| i18n portal (8 idiomas) | 1.287 claves en cada idioma, 0 faltantes, 0 sobrantes | Completo |
| Claves sin uso (aprox.) | 3.443 claves de es sin literal en el código (tras excluir grupos con claves dinámicas). 466 de 1.287 en el portal | Mucha deuda de claves muertas (cota superior, ver A.4) |
| Permisos | `permisos/capacidades.ts` (81) = `app/core/capacidades.py` (81), idénticos. Solo 2 usos de `role ===`, ambos legítimos (rol de mensaje o contacto) | Correcto |
| Estilos | 264 CSS. Colores literales: 245 en `index.css` (definición de tokens) y 1 de respaldo. `font-size` literal: 21 (19 en `demanda.css`) frente a 3.394 con `var()` | Muy disciplinado. `demanda.css` se sale |
| Documentación | 37 .md versionados: 15 al día, 6 parcialmente desfasados, 4 desfasados, 12 históricos | Cifras y cabeza de Alembic caducadas |
| Tests backend | 533 ficheros en `tests/` (529 con tests), **4.887** `def test_`. 81 líneas de skip/xfail en 33 ficheros | Mucho volumen, aserciones laxas, sin CI |
| Tests frontend | 111 `.test.ts(x)`, unos 507 `it/test`. 0 `it.skip` | No hay tests del interceptor de sesión ni de la cola offline |

**Críticos: 0. Altos: 7. Medios: 17. Bajos: 13** (detalle en «Hallazgos por severidad»).

---

## A) Componentes y servicios

### A.1 Seguridad en el cliente y sesión (`services/api/_core.ts`, `context/AuthContext.tsx`)

**Lo que está bien (comprobado):**
- Los tokens viajan solo en cookies httpOnly (`withCredentials: true`, `_core.ts:33`). No se guarda ningún token de sesión en `localStorage`: los 27 `setItem` revisados son preferencias, la pista `cf_authed` o ids.
- Hay un refresco único en vuelo (`_core.ts:78-88`) y una renovación anticipada con la cookie `session_expires_at` (`_core.ts:96-131`).
- Se envía la cabecera `X-CSRF-Token` en los métodos que escriben (`_core.ts:64-70`, `:235-237`).
- `dangerouslySetInnerHTML`: 0 usos. `eval`/`new Function`: 0. ESLint los prohíbe (`eslint.config.js:194-201`).
- Las capacidades del frontend coinciden 1:1 con el backend, y `tieneCapacidad` deniega por defecto (`permisos/capacidades.ts:51`).

**Problemas:**

1. **Al recargar con el acceso caducado se pierde la sesión aunque el refresco siga siendo válido** (alta).
   - Las cookies `access_token` y `session_expires_at` duran `ACCESS_TOKEN_EXPIRE_MINUTES` = 15 min (`app/api/cookies_de_sesion.py:34,53`, `app/core/config.py:72`). La cookie de refresco dura 30 días (`config.py:76`).
   - Al recargar, `AuthContext.tsx:146` llama a `/auth/me`. El interceptor excluye `/auth/me` del refresco (`_core.ts:176`), así que el 401 borra `cf_authed` y deja al usuario fuera (`AuthContext.tsx:148-150`).
   - `get_current_user` no usa la cookie de refresco (no hay `refresh_token` en `app/api/deps.py`).
   - Impacto: quien vuelve tras más de 15 min sin la pestaña abierta tiene que volver a entrar, aunque «recordar sesión» dure 30 días.
   - Arreglo: en el arranque, ante un 401 de `/auth/me`, intentar `refrescarSesion()` una vez y repetir la llamada.
   - **Estado:** ✅ arreglado 23-11-2026: ante un 401 de `/auth/me` en el arranque, `AuthContext` llama a `refrescarSesionAlArrancar()` (`_core.ts`) y repite una vez.

2. **El refresco no manda `X-CSRF-Token`** (alta latente).
   - `refrescarSesion` usa `axios.post` directo (`_core.ts:83-84`), no la instancia `api`, así que no pasa por el interceptor que añade la cabecera.
   - `/auth/refresh` no está exento (`app/core/csrf.py:46-65`) y usa la cookie `refresh_token`, que se considera autenticación por cookie (`csrf.py:104-110`).
   - Con `CSRF_DOUBLE_SUBMIT=1` (`app/core/config_groups/proceso_config.py:31`), todos los refrescos darían 403 y todas las sesiones caducarían a los 15 min. Lo mismo pasa con `navigator.sendBeacon` de presencia (`pages/ChatPage.tsx:213`) y con `Layout.tsx:1024`, que sí pasa por `api`.
   - Arreglo: añadir la cabecera en `refrescarSesion` (o usar `api.post` con un indicador para no entrar en bucle) y un test.
   - **Estado:** ✅ arreglado 23-11-2026: (otro agente, misma fase) `refrescarSesion` manda `X-CSRF-Token`.

3. **El CSRF no protege el portal de clientes** (media, backend detectado desde el cliente).
   - El portal autentica con la cookie `portal_access_token` (`app/api/v1/endpoints/client_portal.py:255-260`).
   - `_uses_cookie_auth` solo mira `access_token`/`refresh_token` (`csrf.py:106`), así que ninguna escritura del portal pasa por la comprobación de Origin ni por el doble envío.
   - Lo mitiga que la cookie es `samesite="lax"`.
   - Arreglo: incluir `portal_access_token` en `_uses_cookie_auth`.
   - **Estado:** ✅ arreglado 23-11-2026 (fase de backend): `csrf.py` cuenta `portal_access_token` como cookie de sesión y el login del portal emite el testigo CSRF.

4. **Al cerrar sesión no se vacía la caché de React Query** (alta).
   - `logout` (`AuthContext.tsx:215-226`) y el manejador de sesión caducada (`:171-177`) solo borran dos claves de almacenamiento y el usuario. No hay `queryClient.clear()` ni recarga (búsqueda de `.clear()`, `removeQueries` y `resetQueries`: 0 en `src` salvo un `Set`).
   - `gcTime` es de 5 min (`main.tsx:144`).
   - Impacto: en un puesto compartido, el siguiente usuario, o el mismo usuario tras cambiar de empresa por SPA, puede ver durante un instante datos en caché del anterior (de otro tenant).
   - Arreglo: `queryClient.clear()` en `auth:logout-start` y en `auth:session-expired`.
   - **Estado:** ✅ arreglado 23-11-2026: evento `auth:session-cleared` en logout y sesión caducada → `queryClient.clear()` (`main.tsx`).

5. **La cola offline de imputaciones no es por usuario** (alta).
   - `services/offlineQueue.ts:53-60` guarda el `form` en IndexedDB sin usuario ni empresa. `syncPending` (`:120-150`) lo publica con la sesión que haya al reconectar.
   - Si A imputa sin conexión, cierra sesión y entra B, las horas de A se guardan como de B.
   - Además, tras 3 fallos se descartan en silencio (`:131-135`).
   - Arreglo: guardar `user_id`/`org_id` en cada entrada, sincronizar solo las del usuario actual, borrar la cola al cerrar sesión y avisar de lo descartado.
   - **Estado:** ✅ arreglado 23-11-2026: entradas con `_dueno_user`/`_dueno_org`; solo se cuenta y sube lo del usuario y empresa actuales; tras 3 fallos quedan `abandonada` y se avisa (`offline:imputaciones-abandonadas` → toast).

6. **La caché BI offline no es por usuario ni por empresa** (media).
   - La clave es constante (`pages/BIPage.tsx:50`, `periodKey = 'mtd'`) en `services/biOfflineDb.ts:30-36`, con un TTL de 8 h. No se borra al cerrar sesión.
   - Sin conexión, otro usuario del mismo navegador vería los KPI financieros del anterior.
   - Arreglo: incluir `org_id:user_id` en la clave y borrar la base de datos al cerrar sesión.
   - **Estado:** ✅ arreglado 23-11-2026: clave `empresa:usuario:…` (`establecerAmbitoBi`) y `borrarCacheBi()` al salir.

7. **Datos personales en `localStorage`** (baja).
   - `client_user` del portal (`pages/portal-client/portalClientContext.tsx:285,300`) sí se borra al cerrar sesión (`:309`).
   - El token de LiveKit se guarda en `sessionStorage` (`pages/ChatPage.tsx:1168`): es de vida corta pero queda al alcance de un XSS.
   - **Estado:** ✅ arreglado 23-11-2026: `client_user` con try/catch; credenciales de llamada: se leen una vez y se borran si la ventana no abre. El token sigue en sessionStorage el instante de abrir la ventana (riesgo bajo aceptado).

8. **`document.write` con `node.outerHTML`** (`pages/BIProjectDetailPage.tsx:84`) (baja). El contenido viene del DOM que React ya ha escapado; el título sí se sanea. Es aceptable, pero `react/no-danger` no lo cubre.
   - **Estado:** ✅ arreglado 23-11-2026 (segunda ronda): sin `document.write`; se imprime el nodo en la propia página con `@media print` (ver M11 del 04).

9. **Refresco de todas las consultas tras cualquier escritura** (`services/api/refrescoTrasEscritura.ts:1-16,55`) (media).
   - Cada POST/PUT/PATCH/DELETE invalida todas las consultas, salvo la lista de exclusión.
   - Impacto: tormenta de peticiones en pantallas con muchas consultas y riesgo de 429 (el limitador avisa en `_core.ts:200-208`).
   - Arreglo: invalidar por prefijo de recurso derivado de la URL.
   - **Estado:** ✅ decidido 23-11-2026 (segunda ronda): se mantiene. Medido en `refrescoTrasEscritura.ts`: las escrituras seguidas se agrupan (60 ms) y solo se vuelven a pedir las consultas montadas (`refetchType: 'active'`); las demás quedan obsoletas sin petición. La invalidación por prefijo exigiría un mapa URL → claves que, si se queda corto, vuelve a dejar pantallas sin refrescar (el fallo que motivó este diseño).

### A.2 Código muerto (medido)

- **Ficheros sin importar** en components, hooks, utils, services, lib, context, permisos, i18n, charts, constants y types: **0**. Solo aparecen `i18n/todosLosIdiomas.mjs`, que usan los scripts, y dos `.d.ts`.
- **Exports sin ningún uso** (ni externo ni interno, sin contar tests): **184**. De ellos, unos 170 son hooks de React Query que las páginas no usan, porque llaman a `services/api` directamente.

  | Fichero | Hooks muertos |
  |---|---|
  | `useApprovals.ts` | 17 |
  | `useImputations.ts` | 13 |
  | `useAnalytics.ts` | 11 |
  | `useTraining.ts` | 10 |
  | `useExpenses.ts` | 9 |
  | `useTasks.ts`, `useTickets.ts`, `useProjects.ts` | 8 cada uno |
  | `useRateCards.ts` | 7 |
  | `useChanges.ts`, `useLicenses.ts`, `useMilestones.ts`, `useForecasts.ts` | 6 cada uno |
  | `useAssets`, `useContracts`, `useDashboard`, `useProblems`, `useRisks`, `useSubcontractors`, `useVendors` | 5 cada uno |
  | `useAbsences`, `useAlerts`, `useClients`, `useEpics`, `useOKRs`, `useUsers` | 4 cada uno |

  Fuera de los hooks: `meetingsAIApi` (`_core.ts`), `ORIGENES_REUNION` (`api/reuniones.ts`), `loadColor` e `initials` (`utils/helpers.ts`) y `SOLO_MES` (`utils/periodo.ts`).
  `hooks/index.ts` reexporta 219 nombres y nadie importa ese barril.
- **Scripts rotos:** `frontend/scripts/check_portal_i18n_missing.js` y `.cjs` (dos copias casi iguales) leen `src/i18n/portalTranslations.js`, que no existe (ahora es `.ts` más `i18n/portal/*.ts`).
- **Script `test:e2e` sin destino:** `package.json:71` lanza `playwright test`, pero no hay `playwright.config.*` ni ningún `.spec.ts` versionado. El e2e real está en Python (`tests_e2e/`).
- **`scripts/i18n_baseline.json`** es de 2026-04-29, tiene 3.027 claves y 8 idiomas del operador, cuando hoy son 3. `check:i18n:ci` lo usa como línea base (`scripts/check_i18n_no_new_debt.mjs:5`), así que la comparación no tiene sentido.

### A.3 Duplicados

- Hay dos mecanismos de confirmación: `components/ui/Confirm.tsx` (8 ficheros lo usan) y `context/ConfirmContext.tsx` (122). Baja: unificar en el contexto.
- `comun.tsx` se repite en 6 carpetas de dominio y `Controles.tsx` en 2 (`ui/` y `cmdb/software/riesgo/`). Son ayudas locales, sin solape funcional comprobado (sin verificar en detalle).
- El desenvoltorio de sobres `{items,meta}` y `{data,meta}` está duplicado en `_core.ts:141-161` y `portal-client/portalClientContext.tsx:48-65`. Media: extraerlo a `clienteBase.ts`.

### A.4 i18n

- **Operador (es/en/zh):**
  - es tiene 22.898 claves; en y zh, 22.895. Las 3 que faltan en en y zh las usa `components/demanda/DetalleDemanda.tsx:163`, y en en/zh se ve la clave «humanizada». Media, por la regla de que es/en/zh son obligatorios.
  - Claves vacías: es 2, en 2, zh 4 (sin verificar cuáles importan).
  - 1 clave en en y zh es idéntica al texto español (`meetings_ai.demo_participants`).
- **Claves usadas y no definidas** (tras quitar los prefijos dinámicos):
  - `app_errors.app_unexpected_desc` en `main.tsx:106`: el texto de la pantalla de error global en producción. Media.
  - `almint.urgencia` en `pages/MisEquiposPage.tsx:236`. Baja.
  - `dashboard.title`, `welcome` y `unknown` solo aparecen en un test con su propio diccionario.
- **Portal (8 idiomas):** 1.287 claves en cada uno; paridad total.
- **Claves sin uso:** 3.443 de 22.898 no aparecen como literal (ni la clave completa ni la hoja) fuera de los grupos con claves dinámicas. Los grupos con más son `sw` 273, `automations` 189, `grc` 183, `alm_uso` 161 y `sd_mercado` 157. Es una cota superior, porque hay construcciones dinámicas que el patrón no detecta (por ejemplo `externos.papel_${rol}`). En el portal, 466 de 1.287. Baja: hace falta un script que lo mida bien.
- **Literales sin traducir en componentes y contextos:**
  - Casi nada. Las siglas (CVSS, EPSS, KEV, CAPEX, CSV) son aceptables.
  - **Hardcode real:** el aviso de límite de peticiones en `context/AuthContext.tsx:186-188` («Demasiadas peticiones…»), solo en castellano. Media.
  - `constants/business_config.json` tiene etiquetas y placeholders en castellano. La descripción pasa por `t()` con respaldo (`pages/EnterprisePage.tsx:530`); los `fields[].label` no (sin verificar dónde se pintan).

### A.5 Estilos y tokens

- `index.css` (2.229 líneas) define los tokens. Fuera de él, solo hay 1 color literal y es un respaldo dentro de `var()` (`components/ui/SelectRico.css:65`).
- **`components/demanda/demanda.css`** tiene 19 `font-size` en px (líneas 4-65) y radios y espaciados literales: es el único módulo nuevo que no usa `var(--font-*)`. Lo mismo, en menor medida, `cmdb/software/riesgo/riesgo.css:9` (56px), `reuniones/Reuniones.css:97` y `pages/DataGovernancePage.css:30`. Baja.
- Colores hexadecimales en TS: 62 en 9 ficheros. Los legítimos están en `constants/theme.ts` (30) y `charts/useChartTheme.ts` (16). `components/layout/UserProfilePanel.tsx:46-53,312` tiene la paleta de acento escrita en el componente. Baja: moverla a `constants/theme.ts`.
- No hay `stylelint`: la regla de tokens en CSS no la vigila ninguna herramienta (solo `scripts/kit/comprobarCss.mjs` y tests de texto). Baja.
- `style={{}}` en componentes: 132 en 50 ficheros, vigilado por la regla propia `contec/solo-variables-css-en-style`.

### A.6 ESLint propio y kit

- `scripts/eslint/solo-variables-css-en-style.mjs` y `kit-sin-marcado-propio.mjs` están registrados (`eslint.config.js:7-23`) y tienen tests (`reglaEstiloSoloVariables.test.ts`, `reglasDelKit.test.ts`).
- Las reglas de accesibilidad están casi todas en `warn` (`eslint.config.js:221-235`), y `lint:a11y:strict:core` solo mira 5 ficheros (`package.json:62`). Media: hay deuda de accesibilidad sin freno.
- **`frontend/vite.config.js` contiene dos bytes NUL literales** (líneas 32 y 34, el prefijo de módulo virtual `\0` de Rollup escrito como carácter crudo). `file` lo detecta como «data», y git y grep lo tratan como binario: los diffs no se ven en revisión. Baja: escribir `'\0'`.
- Supresiones: `@ts-nocheck` 0, `@ts-ignore` 0, `any` 2, `eslint-disable` 32 en 27 ficheros.

### A.7 Otros

- **RGPD:** las fuentes se cargan de Google por defecto (`src/fuentes.ts:17-23`, si no se define `VITE_FONTS_CSS_URL`). Cada visita envía la IP del usuario a Google; la CSP lo permite (`app/main.py:799-823`). Media: la privacidad por defecto pide servirlas desde el propio host.
- **Pantalla de error global:** en producción muestra una clave sin definir (ver A.4).


### Estado de la parte A (23-11-2026)

| Hallazgo | Estado |
|---|---|
| A.2 hooks muertos y barril | ✅ arreglado 23-11-2026: borrados 25 ficheros de hooks sin ningún importador y `hooks/index.ts`; quitados los exports muertos de `useAnalytics` (11), `useProjects` (9) y `usePipeline` (1); `meetingsAIApi`, `initials` y el reexport de `ORIGENES_REUNION`. Quedan `loadColor` y `SOLO_MES` (los usan tests) y `_reiniciarAvisosEnVivo` (ayuda de test). |
| A.2 scripts `check_portal_i18n_missing.{js,cjs}` | ✅ arreglado 23-11-2026: borrados (leían un fichero inexistente). |
| A.2 `test:e2e` sin destino | ✅ arreglado 23-11-2026: quitados `test:e2e*` e `install:playwright` de `package.json` (el e2e real es `tests_e2e/` en Python); README actualizado. |
| A.2 `i18n_baseline.json` obsoleto | ✅ regenerado 23-11-2026 (segunda ronda): lo usa `check:i18n:ci` (medido), así que se rehace con es/en/zh y fecha; `check_i18n_no_new_debt.mjs` pasa. |
| A.3 dos mecanismos de confirmación | ✅ arreglado 23-11-2026 (segunda ronda): los 9 usos de `ui/Confirm.tsx` pasan a `confirmar()` de `ConfirmContext`; `ui/Confirm.tsx` y su test, retirados. |
| A.3 desenvoltorio de sobres duplicado | ✅ arreglado 23-11-2026 (segunda ronda): `clienteBase.desenvolverSobre`, usado por `_core.ts` y por el portal; test `services/desenvolverSobre.test.ts`. |
| A.4 3 claves `demanda.*` en en/zh | ✅ arreglado 23-11-2026. Paridad medida: es/en/zh con el mismo número de claves y 0 vacías en zh. |
| A.4 `app_errors.app_unexpected_desc` | ✅ arreglado 23-11-2026: definida en es/en/zh. |
| A.4 `almint.urgencia` | ✅ arreglado 23-11-2026: `almint.urgencia_label`. |
| A.4 aviso de 429 en castellano | ✅ arreglado 23-11-2026: `authcontext.demasiadas_peticiones*`. |
| A.4 claves vacías | ✅ arreglado 23-11-2026: borradas `alm.action_assign_hint`, `settingsadvanced.service_desk_voz_ml_auto_resolucion` y `approvals.steps_suffix_plural`; `grc.los` con texto en zh. |
| A.4 `business_config.json` en castellano | ✅ verificado 23-11-2026 (segunda ronda): se pintan en `EnterpriseIntegraciones.tsx` con `t('pagina_ent.int_campo_<tipo>_<campo>', label)` y `int_desc_<tipo>`; medido: 0 claves de campo sin traducir en es/en/zh. El texto del JSON solo es respaldo; los `label` de tipo son marcas. |
| A.4 claves sin uso (cota) | ⏸ pendiente: no entra en esta ronda (no estaba en la lista de tareas); hace falta un script que resuelva las claves dinámicas antes de borrar nada. |
| A.5 `demanda.css` y otros `font-size` en px | ✅ arreglado 23-11-2026 (segunda ronda): 18 `font-size` de `demanda.css` a `var(--text-*)` (mismo tamaño) y `riesgo.css` a `var(--text-56)`; `Reuniones.css` y `DataGovernancePage.css` ya no tenían ninguno (medido). Radios y espaciados de `demanda.css` se quedan (8 px no tiene token exacto). |
| A.5 paleta de acento en `UserProfilePanel` | ✅ arreglado 23-11-2026 (segunda ronda): `PALETA_DE_ACENTO` y `ACENTO_POR_DEFECTO` en `constants/theme.ts`. |
| A.6 bytes NUL en `vite.config.js` | ✅ arreglado 23-11-2026: `'\0'` escrito como escape (mismo valor); `file` ya lo ve como texto. |
| A.6 reglas a11y en `warn` | ✅ arreglado 23-11-2026 (segunda ronda): todas en `error`. Medido antes: 25 avisos reales en 20 ficheros (10 `<th />` vacías → texto para lectores de pantalla `common.col_acciones`/`col_seleccion`; 1 `treeitem` sin `aria-selected`; 4 `<label>` con el Checkbox del kit y 12 `<td>`/`<option>` falsos positivos → opciones de la regla). Después: 0 en `src`. |
| A.7 Google Fonts por defecto (RGPD) | ✅ arreglado 23-11-2026 (segunda ronda): `@fontsource/dm-sans`, `geist` y `geist-mono` (mismas familias y pesos: 400-800 y 400-500) importados en `fuentes.ts`; sin peticiones a Google y CSP sin Google (`app/main.py`, nginx, vite). La IP del visitante ya no llega a Google. CJK: igual que antes (fuente del sistema). |
| C.2 tests del interceptor/offline | ✅ escritos 23-11-2026 (segunda ronda), sin ejecutar (los pasa el coordinador al final): `services/interceptorCsrf.test.ts` (cabecera CSRF solo al escribir, sobres) y `services/colaOfflinePorUsuario.test.ts` (cola por dueño). |

---

## B) Documentación

Repo con **147 revisiones de Alembic y una sola cabeza, `195_flujo_de_demanda`**. La cadena es lineal; faltan números (002-059, 061-069, 176, 187) sin romperla.

| Documento | Tema | Estado | Desfases principales (comprobados) |
|---|---|---|---|
| `README.md` | Manual completo (inglés) | Parcial → ✅ actualizado 23-11-2026 | :16 «123 migrations, head 169», cuando hay 147 y la cabeza es 195. :21 «256 claves en 24 grupos», cuando son 392 en 31 (`settings_service/_catalogo.py:14`). :5528/:6512 «46 tareas, 42 beat, 715 líneas», cuando son 58, 53 y 881 (`app/worker.py`). Faltan en beat `reuniones-retencion` (worker.py:300), `demanda-plazos`, `alm-*`, `evm-curva-s-diaria`, `externos-caducidad`, `reuniones-sondeo` y `cmdb-software-diario`. :5008-5011 cuenta 9 y «estos cinco» tipos de retención, cuando hay 24 (`app/db/bloqueo_legal.py:152-217`). §7.4 «~100 `audit_log(`», cuando son unas 310. :278/:831/:1010/:1104/:4224 citan `*_service.py` que hoy son paquetes. :5120 dice que solo procesar, rechazar y exportar del RGPD exigen admin, pero también listar y crear (`cab.py:363,395`). :5150 «a deletion… is detected»: borrar las últimas filas solo se detecta frente a una exportación previa |
| `DOCS.md` | Registro de cambios y arquitectura | Al día | Referencias históricas a ficheros que ya no existen (:209, :231, :588). Aceptable en un registro de cambios |
| `AUDITORIA_TRASPASO.md` | Traspaso de auditoría | Histórico → ✅ marcado como histórico 23-11-2026 | :10 fecha 2026-08-31. :40 «3.467 tests», cuando hay 4.887. :33 «verificar antes de cada commit» choca con la regla actual de no probar hasta el final |
| `alembic/NAMING_CONVENTION.md` | Nombres de migración | Desfasado → ✅ actualizado 23-11-2026 | :62-73 exige prefijo hexadecimal, pero desde la 086 todo es `NNN_nombre_en_castellano` |
| `.github/agents/nexus.agent.md` | Agente de Copilot | Desfasado → ✅ actualizado 23-11-2026 | :79, :87-89 y :137 hablan de `.jsx`, pero hay 0 .js/.jsx y 749 .ts/.tsx. :215-216 citan ficheros renombrados |
| `frontend/MIGRATION_TS.md` | Migración a TS | Parcial → ✅ actualizado 23-11-2026 | «461 ficheros», cuando son 749. Cita `wsUtils.ts`, `logger.ts`, `useDeliverables.ts`, `useCountUp.ts` y `types/api.ts`, que no existen |
| `frontend/kit-migracion-plan.md` | Plan del kit (generado) | Al día | Lo genera `scripts/kit_pendientes.mjs` |
| `frontend/src/components/ui/DESIGN_SYSTEM.md` | Guía del kit | Al día | Sin verificar en detalle |
| `docs/A11Y_WCAG_AUDIT.md` | WCAG | Al día | Los scripts existen (`package.json:60-62`) |
| `docs/AI_ML_ARCH_DECISIONS.md` | Decisiones de IA/ML | Histórico → ✅ marcado como histórico 23-11-2026 | :65 cita `tests/integration/test_ai_provider_chokepoint.py`, que no existe |
| `docs/APPROVAL_ENGINE.md` | Motor de aprobaciones | Al día | Sin verificar en detalle |
| `docs/ASISTENTE_DE_REUNIONES.md` | Reuniones e IA | Parcial → ✅ actualizado 23-11-2026 | :171 avisa de «dos cabezas», ya resuelto |
| `docs/AUDIT_2026_07_FULL`, `AUDIT_2026_08_SECOND_PASS`, `AUDIT_63_INITIAL_MIGRATION`, `CASCADE_DELETE_AUDIT`, `CIRCULAR_IMPORTS`, `RESPONSE_WRAPPER_MIGRATION`, `SEARCH_PERFORMANCE` | Auditorías y planes antiguos | Histórico → ✅ marcado como histórico 23-11-2026 | Todos avisan de que pueden no reflejar el código |
| `docs/CLIENTES_INTERNOS`, `CMDB_SOFTWARE_Y_VULNERABILIDADES`, `FLUJO_DE_DEMANDA`, `PROVEEDORES_Y_EXTERNALIZACION` | Módulos recientes | Al día | Las rutas y las migraciones 189-195 coinciden |
| `docs/SERVICE_DESK.md`, `GUIA_DE_DISENO.md` | Service Desk y diseño | Al día | Las rutas citadas existen |
| `docs/COLLABORATION_E2E_ENCRYPTION_OPTIONAL.md` | Propuesta E2E | Histórico → ✅ marcado como histórico 23-11-2026 | Declara que no está implementado |
| `docs/COMPARATIVA_CONTECMIND_CONTECINTELLIGENCE.md` | Comparativa | Parcial → ✅ actualizado 23-11-2026 | :75 «five record types», cuando son 24 |
| `docs/CONFIGURACION.md` | Configuración del operador | Al día | — |
| `docs/CONFIGURACION_INVENTARIO.md` | Inventario anterior | Histórico → ✅ marcado como histórico 23-11-2026 | :8 `deps.py:188-205`, hoy en 177-195 |
| `docs/CONFIG_LOCATION_FULL_TABLE.md`, `CONFIG_LOCATION_MAP.md` | Mapa de ajustes | Desfasado → ✅ actualizado 23-11-2026 | El cuerpo describe 191 ajustes. Hasta el aviso (:5-9) está mal: dice «476 campos, 256 claves en 24 grupos» y hay unos 634 campos (288 en `config.py` y 346 en `config_groups`, contados con regex) y 392 claves en 31 grupos |
| `docs/CONFIG_MIGRATION_INVENTORY.md` | Plan env→UI | Histórico → ✅ marcado como histórico 23-11-2026 | — |
| `docs/DESPLIEGUE.md` | Despliegue | Parcial → ✅ actualizado 23-11-2026 | :11 «cabeza 169, 123 revisiones». La tabla B.2 (:311) no tiene notas de 170-195 |
| `docs/INDEX_TUNING.md` | Índices | Al día | Los `ix_*` citados existen |
| `docs/OBSERVABILIDAD.md`, `OBSERVABILITY_PROMETHEUS.md` | Métricas | Al día | Las métricas existen |
| `docs/WORKER_TASKS.md` | Tareas del worker | Parcial → ✅ actualizado 23-11-2026 | Faltan las mismas entradas de beat que en el README (`reuniones-retencion`, `demanda-plazos`…) |

**Recuento:** 15 al día, 6 parcialmente desfasados, 4 desfasados, 12 históricos (37 en total).

### B.1 GRC: documentación frente a código

| Tema | Código | Documentación | Hallazgo |
|---|---|---|---|
| Registro de auditoría | Cadena HMAC + Ed25519 (`cadena_auditoria.py`), encadenada en `before_insert` (`models/enterprise.py:70`) con `pg_advisory_xact_lock` | README §7.4 | ✅ arreglado 23-11-2026 (migración 199, `app/db/auditoria_inmutable.py`): triggers en Postgres y SQLite niegan UPDATE/DELETE (excepciones: `user_id` a NULL, encadenar filas sin `seq`, purga de empresa con permiso); README §7.4 y la sección de la cadena corregidos; control `audit_log_immutable` en el informe. Antes: **Media.** No hay trigger ni REVOKE que impida UPDATE/DELETE sobre `audit_logs` (la migración 137 solo añade columnas e índices). El README:5150 sobrevende la detección de borrados (lo matizan :5151 y `cadena_auditoria.py:17-20`) |
| Retención del registro | Sin entrada en `TIPOS` (art. 17.3) | README:5009 | ✅ documentado 23-11-2026: sin tipo de retención a propósito (se conserva mientras exista la empresa, RGPD art. 17.3.b/e; sale en la exportación firmada o con la purga de la empresa tras la cuarentena). README y `docs/seguridad/politicas_de_cuenta.md` §10. Antes: **Media.** Crece sin límite y sin un plazo legal documentado ni archivado |
| RGPD | Dos circuitos: `/gdpr/requests` (`cab.py:358-423`) y `/bi/gdpr/*` (`bi_gdpr.py:73-356`: consentimiento, DSR, `erasure-execute`, `portability-export`, `field-masks`) | Solo el primero (README:5120) | **Alta.** Hay un segundo registro de solicitudes y plazos que el auditor no ve. Unificar o documentar y enlazar |
| Autoservicio del interesado | Crear una DSR o un consentimiento exige `require_admin` (`bi_gdpr.py:80,187`, `cab.py:395`) | — | **Media.** El interesado no puede ejercer sus derechos solo (sin verificar si el portal lo cubre por otra vía) |
| Retención | 24 tipos en `bloqueo_legal.TIPOS`, mínimo configurable (`retencion.py:91-119`), trabajo diario (`worker.py:213`) y `reuniones-retencion` (`worker.py:300`) | README dice 5-9 tipos; WORKER_TASKS no incluye `reuniones-retencion` | **Media.** Generar la lista a partir de `TIPOS` |
| Bloqueo legal | `before_flush` (`models/governance.py:94`); la baja de empresa lo respeta (`baja_de_empresa_service.py:191`); la supresión devuelve 409 con bloqueo (`supresion_service.py:68`) | Documentado | Correcto |
| Privilegios | Endpoints GRC con `require_admin` (`governance.py:252-294`, `enterprise.py:30-65`). `enforce_abac` falla en abierto (`abac_enforce.py:129`), documentado en README:968. Capacidades frontend = backend (81 = 81) | Documentado | Correcto. Falla en abierto por diseño (riesgo aceptado y documentado) |
| Ajustes GRC en `.env.example` | `RETENTION_MIN_DAYS` (config.py:149), `AUDIT_EXPORT_MAX_ROWS` (:142), `TENANT_DELETION_QUARANTINE_DAYS` (:140) | Ausentes de `.env.example` | **Media** |
| `.env` versionado | `git ls-files` → `.env`; `.gitignore:1-4` lo justifica y README:6495 también | Documentado | **Alta (decisión del usuario).** Choca con la norma «no subir .env». Quien lea el repo tiene los secretos de desarrollo |

**Estado de B.1 (23-11-2026), solo lo tratado en documentación:**

- **Registro de auditoría** (README §7.4): ✅ la frase que sobrevendía la detección de borrados está corregida (el borrado de entradas con otras posteriores se detecta; el de las últimas, solo frente a una exportación previa) y el README dice ahora que no hay trigger ni `REVOKE` sobre `audit_logs`. El hallazgo de código (añadirlos) sigue abierto.
- **Retención del registro** (README, «Retención y bloqueo legal»): ✅ documentado que el registro de auditoría no tiene entrada en `TIPOS`, crece sin límite y no se archiva. La decisión de plazo legal sigue abierta.
- **RGPD, dos circuitos**: ✅ el README documenta el segundo circuito `/bi/gdpr/*` (`bi_gdpr.py`, panel GDPR de Gobernanza de datos), enlazado con `/gdpr/requests`, con la advertencia de que una solicitud de un circuito no aparece en el otro y de que el informe de cumplimiento solo lee `gdpr_requests`. Unificarlos sigue abierto.
- **Autoservicio del interesado**: ✅ el README dice ahora que listar, crear, procesar, rechazar y exportar en `/gdpr/requests` exigen admin (antes solo procesar, rechazar y exportar). Sigue abierto si el portal lo cubre por otra vía.
- **Retención (tipos)**: ✅ el README cuenta 33 tipos en `bloqueo_legal.TIPOS` (medido con `ast` el 23-11-2026; el informe decía 24 y el README 5-9) y los lista; `docs/WORKER_TASKS.md` y la tabla 8.2 del README incluyen `reuniones-retencion` y el resto de entradas de beat que faltaban (53 entradas, 57 tareas).
- **Ajustes GRC en `.env.example`**: ✅ añadidos `RETENTION_MIN_DAYS` (30), `AUDIT_EXPORT_MAX_ROWS` (100000) y `TENANT_DELETION_QUARANTINE_DAYS` (30), comentados, con los valores por defecto de `app/core/config.py`.

---

## C) Cobertura de tests

### C.1 Qué hay (medido)

- **Backend `tests/`:** 533 .py, 529 con tests, **4.887** `def test_`. La base es SQLite en memoria (`tests/conftest.py`, `TEST_DB_URL="sqlite://"`, `TESTING=1`). Está bien aislado, pero no es Postgres.
- **Zonas con tests por nombre de fichero:**
  - GRC: `test_grc`, `grc_coverage`, `grc_enforcement`, `grc_por_empresa`, `revision_grc`, `pendientes_grc`.
  - RGPD: `test_rgpd_2026_11`, `bi_gdpr`.
  - Retención y bloqueo legal: 2.
  - Auditoría: 14 (casi todos `test_auditoria_2026_11_*`).
  - Permisos y ABAC: 8. RLS y tenant: 23.
  - Worker: 2.
- **`tests_e2e/`** (Playwright con pytest): 15 .py y 39 tests de humo (auth, dashboard, OKR, proyectos, service desk, aprobaciones, WCAG, todas las páginas, portal BI).
- **Frontend (vitest, `vite.config.js:117-120`, entorno jsdom):** 111 `.test.ts(x)` y unos 507 `it/test`.
  - Reparto: `__tests__` 89, i18n 7, pages 6, utils 5, hooks 3, components 1.
  - El único test de `services/api` cubre `unwrapList` (`src/__tests__/services/api.test.ts:9-45`).

### C.2 Zonas importantes sin tests

- **Backend `app/api`:** 49 de 202 módulos sin ninguna referencia por nombre en los tests. Es una cota: los tests de endpoint llaman por URL.
  - Prioridad alta: `abac_admin`, `bi_gdpr` (solo indirecto), `bi_governance`, `routers/auth_saml` y `routers/auth_sessions` (permisos, RGPD, autenticación).
  - Otros sin referencia: `portal_conversations`, `portal_interno`, `proveedores_portal`, `report_builder`, `pdf_export` y 15 módulos de `service_desk` (`cab_workflow`, `change_calendar`, `oncall`, `sla_y_ciclos`…).
- **Backend `app/services`:** 106 de 698 sin referencia. Entre ellos `ws_service`, `ws_manager`, `stripe_service` (facturación; existe `test_auditoria_2026_11_capas_y_stripe`, alcance sin verificar), `risk_service`, `risk_scoring`, `sprint_service`, `imputation_service`, `billing_reports`, `security_observability` y 29 de service desk.
- **Frontend sin tests:**
  - El interceptor 401 y el refresco (`_core.ts:79-212`), la renovación anticipada (`:96-131`) y la cabecera CSRF.
  - `offlineQueue.ts`, `biOfflineDb.ts` y `AuthContext` (logout y sesión caducada).
  - 46 de 49 hooks.
  - `services/` (55 ficheros) solo tiene 3 tests de servicios.
- **Infraestructura:** RLS real (`tests/test_rls_postgres.py:17`), pgvector y paridad de esquema con Alembic (`test_alembic_schema_parity.py:234,242`) se saltan sin Postgres. **El aislamiento multi-tenant real no se prueba en la ejecución por defecto.**
- **No hay CI** (`.github/` solo contiene `agents/nexus.agent.md`). Nada obliga a pasar la suite.

### C.3 Tests saltados (81 líneas en 33 ficheros)

| Fichero:línea | Motivo declarado | Severidad |
|---|---|---|
| `tests/test_imputations_enhanced.py:43,74,96,121,151,189,242,326,476,520,558` (11 `skip`) y 12 `pytest.skip` internos | «audit #90: depends on seeded Project. Refactor pending» | **Alta.** Las imputaciones (horas, facturación) no tienen cobertura real |
| `tests/test_i18n_complete.py:143` | `xfail(strict=False)`: «non-English files are partial (hundreds-to-thousands of keys behind en.mjs)». **Ya no es cierto:** zh tiene todas las claves de en. Lo que falta son 3 claves de es en en y zh, y el test compara contra en, no contra es | Media. Probablemente pasa como XPASS en silencio. Convertir en `strict=True` comparando contra es |
| `tests/test_abac_resources.py:105,226` | `users.organization_id` NOT NULL (escenario imposible) | Baja. Borrar |
| `test_rls_postgres.py:17`, `test_kb_vectores_pgvector.py:15`, `test_alembic_schema_parity.py:234,242`, `test_api_contract_schemathesis.py:19,32,34,46`, `importorskip` en `test_docker_stack.py:20`, `test_ia_revision_2026_11.py:100`, `test_periodo_restos.py:90,269` | Falta infraestructura o un paquete opcional | Media. Se saltan sin avisar |
| `tests_e2e/conftest.py:71,79` | Sin `ADMIN_PASS` o con el login roto, **se salta toda la suite e2e** | Media |
| Dependientes del seed: `test_ai_context_service.py` (7, l. 71-146), `test_documents.py:127,313,348`, `test_training.py:86,105,133`, `test_users.py:119`, `test_raci.py:186,204,257,277`, `test_task_service.py:44`, **`test_grc.py:64`**, `test_v235_features.py:169`, `test_security_observability.py:349,352`, `test_custom_fields.py:308`, `test_report_builder.py:194`, `test_textos_por_clave_2026_11_19.py:68`, `test_auditoria_2026_11_segunda.py:56` | «el seed no trae X» | Media. Fixtures que creen los datos y fallen en vez de saltar |
| Frontend | 0 `it.skip`, `describe.skip` o `.todo` | — |

### C.4 Tests frágiles o inútiles (recuentos por grep)

- **Aserciones laxas `status_code in (...)`:** 507 en 146 ficheros. Caso extremo: `tests/test_webhooks.py:142`, `in (200, 202, 207, 400, 422, 500, 503)`, que acepta un 500. **Alta en conjunto:** no detectan regresiones. Empezar por GRC, auth y RGPD.
- **Leen el código como texto o AST** (`ast.parse`, `read_text`, `getsource`): 82 ficheros, por ejemplo `test_auditoria_2026_11_arquitectura_c1..c4`, `test_alembic_schema_parity.py:155` y `test_ai_chat_service_execute_tool.py:8`. También en el frontend: `estilosEnLinea.test.ts`, `kitCssSinRestos.test.ts` y `disenoSinEmojis.test.ts`. Son guardarraíles de arquitectura: útiles, pero se rompen al refactorizar y no prueban el comportamiento. Media.
- **`assert hasattr`:** 14 (por ejemplo `test_ajustes_declarados.py:116,124`). **`assert callable`:** 3. **`assert True`:** 1. **`assert X is not None`** como línea: 111 en 63 ficheros (no se sabe cuántos son la única aserción). Baja/media.
- **125 funciones con nombre de tipo «existe» o «importa»** en 80 ficheros (sin verificar cuántas son solo de existencia).
- **Dependencia del seed o de `dev_test`:** 268 apariciones en 75 ficheros.
- **Tiempo:** `time.sleep` 6 (1 fichero) y `datetime.now/utcnow()` 11 en 5 ficheros (riesgo de flakiness).
- **Mocks** (`patch`, `MagicMock`, `monkeypatch`): 1.760 en 262 ficheros. Tautologías concretas: sin verificar.
- **Configuración:**
  - `pytest.ini` lleva `-p no:warnings`, que oculta las DeprecationWarning. No tiene `--cov`, `--timeout` ni umbral.
  - Vitest no tiene cobertura configurada. `make test-coverage` no tiene umbral.

---

## Hallazgos por severidad

### Críticos (0)

Ninguno comprobado.

### Altos (7)

| # | Hallazgo | Evidencia | Impacto | Arreglo |
|---|---|---|---|---|
| H1 | Al recargar se pierde la sesión con el refresco vigente | `AuthContext.tsx:146-150`, `_core.ts:176`, `cookies_de_sesion.py:34,53`, `config.py:72,76` | Re-login cada vez que pasan más de 15 min sin pestaña abierta | Intentar el refresco ante un 401 de `/auth/me` en el arranque |
| H2 | El refresco no manda `X-CSRF-Token` | `_core.ts:83-84`, `csrf.py:46-65,104-110,151-168` | Con `CSRF_DOUBLE_SUBMIT=1`, todas las sesiones caen a los 15 min | Añadir la cabecera y un test |
| H3 | El logout no limpia la caché de React Query | `AuthContext.tsx:171-177,215-226`; 0 `queryClient.clear` | Datos de otro usuario o tenant visibles en un puesto compartido | `queryClient.clear()` en logout y en sesión caducada |
| H4 | La cola offline de imputaciones no es por usuario y descarta en silencio | `offlineQueue.ts:53-60,120-150` | Horas imputadas a otro usuario; pérdida de datos | Etiquetar las entradas con usuario y empresa, purgar al cerrar sesión y avisar |
| H5 | Circuito RGPD `/bi/gdpr/*` sin documentar, paralelo a `/gdpr/requests` | `bi_gdpr.py:73-356`, `cab.py:358-423`, README:5120 | Las solicitudes del interesado quedan repartidas en dos registros | Unificar o documentar |
| H6 | 11 tests de imputaciones saltados y 507 aserciones de estado laxas | `test_imputations_enhanced.py:43…558`, `test_webhooks.py:142` | Facturación y horas sin red de seguridad; regresiones invisibles | Fixtures propias; aserciones exactas |
| H7 | Sin CI y sin Postgres en la suite (RLS, pgvector y Alembic se saltan) | `.github/` sin workflows; `test_rls_postgres.py:17` | El aislamiento multi-tenant real no se comprueba | Gate documentado con Postgres (decide el usuario cuándo) |

Además, el `.env` versionado (`.gitignore:1-4`, README:6495) es alto por la norma del usuario, pero es una decisión intencionada y documentada: queda a su criterio.

### Medios (17)

1. El CSRF no cubre la cookie del portal `portal_access_token` (`csrf.py:106`, `client_portal.py:255`).
2. La caché BI offline tiene una clave constante y no se borra al cerrar sesión (`BIPage.tsx:50`, `biOfflineDb.ts:30`).
3. Tras cualquier escritura se invalidan todas las consultas (`refrescoTrasEscritura.ts:55`).
4. Faltan 3 claves de `demanda.*` en en y zh (`DetalleDemanda.tsx:163`).
5. `app_errors.app_unexpected_desc` no está definida y es la pantalla de error global (`main.tsx:106`).
6. Aviso de 429 escrito en castellano en el código (`AuthContext.tsx:186-188`).
7. Google Fonts se carga por defecto (RGPD) (`fuentes.ts:17-23`).
8. ~170 hooks muertos y un barril `hooks/index.ts` que nadie importa.
9. Desenvoltorio de sobres duplicado (`_core.ts:141-161` y `portalClientContext.tsx:48-65`).
10. Las reglas de accesibilidad están en `warn` y la comprobación estricta solo cubre 5 ficheros (`eslint.config.js:221-235`, `package.json:62`).
11. El xfail de i18n está obsoleto y compara contra en en vez de es (`test_i18n_complete.py:143`).
12. Skips por seed (unos 30), incluido `test_grc.py:64`.
13. Skip silencioso de toda la suite e2e (`tests_e2e/conftest.py:71,79`).
14. ✅ 23-11-2026 (migración 199). Registro de auditoría sin protección de base de datos contra UPDATE/DELETE, y el README sobrevende la detección (README:5150).
15. Sin autoservicio RGPD para el interesado (`bi_gdpr.py:80,187`, `cab.py:395`).
16. Documentación de retención y jobs GRC desfasada: 24 tipos frente a 5-9 en el README; faltan `reuniones-retencion` y `demanda-plazos` en WORKER_TASKS.
17. Cabeza de Alembic desfasada en README:16, DESPLIEGUE:11 y ASISTENTE:171; faltan las notas B.2 de 170-195. Ajustes GRC ausentes de `.env.example`.

### Bajos (13)

1. Token de LiveKit en `sessionStorage` (`ChatPage.tsx:1168`).
2. `document.write` en `BIProjectDetailPage.tsx:84`.
3. Dos mecanismos de confirmación (`ui/Confirm.tsx` y `ConfirmContext`).
4. `demanda.css` y otros 3 CSS con `font-size` literal.
5. Paleta de acento escrita en `UserProfilePanel.tsx:46-53`.
6. Sin stylelint.
7. Bytes NUL literales en `vite.config.js:32,34`.
8. Scripts `check_portal_i18n_missing.{js,cjs}` rotos y duplicados.
9. `test:e2e` (Playwright TS) sin configuración ni specs.
10. `i18n_baseline.json` obsoleto (8 idiomas, abril).
11. 3.443 claves i18n probablemente sin uso y 466 del portal (cota).
12. `NAMING_CONVENTION.md`, `nexus.agent.md`, `MIGRATION_TS.md` y `CONFIG_LOCATION_*` desfasados.
13. Tests de solo existencia (`hasattr` 14, `callable` 3, `assert True` 1) y 2 skips ABAC imposibles.

---

## Código muerto

| Elemento | Medida | Evidencia |
|---|---|---|
| Hooks de React Query sin uso | ~170 exports en 30 ficheros | Script de imports sobre `git ls-files src` (tests excluidos); ver A.2 |
| Barril `hooks/index.ts` | 219 reexports, 0 importadores | Ídem |
| `meetingsAIApi`, `ORIGENES_REUNION`, `loadColor`, `initials`, `SOLO_MES` | 5 exports | Ídem |
| `scripts/check_portal_i18n_missing.js` y `.cjs` | 2 scripts rotos | Leen `src/i18n/portalTranslations.js`, que no existe |
| `test:e2e` (Playwright TS) | 1 script npm sin destino | `package.json:71`; 0 `playwright.config`, 0 `.spec.ts` |
| `scripts/i18n_baseline.json` | Línea base obsoleta | 2026-04-29, 8 idiomas |
| Claves i18n | ~3.443 (operador) y 466 (portal), cota superior | Script de literales; las claves dinámicas pueden reducirlo |
| Tests | 2 skips imposibles (`test_abac_resources.py:105,226`) | Escenario que la restricción NOT NULL impide |
| Componentes | 0 ficheros sin importar | — |

## Hardcode

| Elemento | Evidencia | Severidad |
|---|---|---|
| Texto de 429 en castellano | `context/AuthContext.tsx:186-188` | Media |
| Google Fonts como origen por defecto | `src/fuentes.ts:17-18`; CSP en `app/main.py:799-823` | Media (RGPD) |
| Clave de caché BI constante `'mtd'` | `pages/BIPage.tsx:50` | Media |
| Paleta de acentos en el componente | `components/layout/UserProfilePanel.tsx:46-53,312` | Baja |
| `font-size` y espaciados en px | `components/demanda/demanda.css:4-65` (19), `riesgo.css:9`, `Reuniones.css:97`, `DataGovernancePage.css:30` | Baja |
| Etiquetas del catálogo de integraciones en castellano | `constants/business_config.json:3-5` (los `fields[].label` sin `t()`) | Baja (sin verificar dónde se pintan) |
| Tiempos de sesión y IA en el cliente | `_core.ts:39` (`TIMEOUT_DE_IA_MS=150000`), `:103-104` (margen de 60 s, mínimo de 5 s) | Baja: deberían salir de la configuración o de `constants/timings.ts` |
| URLs y prefijos de API | Centralizados en `services/api/urls.ts` (`PREFIJO_API_SERVIDOR`, `VITE_API_URL`) | Correcto |
| Ajustes GRC ausentes en `.env.example` | `RETENTION_MIN_DAYS`, `AUDIT_EXPORT_MAX_ROWS`, `TENANT_DELETION_QUARANTINE_DAYS` (`config.py:140-149`) | Media |

## Estado por hallazgo (segunda ronda, 23-11-2026)

Cada fila de «Hallazgos por severidad», C.3, C.4, «Código muerto» y «Hardcode» con su estado. ✅ hecho · ⏳ en curso por otro agente · ⏸ pendiente con motivo.

| Hallazgo | Estado |
|---|---|
| H1 sesión al recargar | ✅ (A.1.1) |
| H2 refresco sin CSRF | ✅ (A.1.2); test `services/interceptorCsrf.test.ts` |
| H3 caché de React Query al salir | ✅ (A.1.4) |
| H4 cola offline por usuario | ✅ (A.1.5); test `services/colaOfflinePorUsuario.test.ts` |
| H5 circuito RGPD `/bi/gdpr/*` | ✅ documentado y enlazado (B.1). ⏸ unificar los dos registros: cambio de backend y de datos, decide el usuario |
| H6 tests de imputaciones saltados y aserciones laxas | ✅ medido: 0 aserciones `status_code in (...)` que admitan 5xx (quedan 505 sin 5xx); 0 skips por seed en los ficheros de C.3 (fixtures propias) |
| H7 sin CI ni Postgres | ⏸ decide el usuario (sin CI por norma de trabajo: «sin controles automáticos») |
| `.env` versionado | ⏸ decisión intencionada y documentada del usuario |
| M1 CSRF del portal | ✅ (A.1.3) |
| M2 caché BI | ✅ (A.1.6) |
| M3 refresco tras escritura | ✅ decidido (A.1.9) |
| M4 3 claves `demanda.*` | ✅ |
| M5 `app_errors.app_unexpected_desc` | ✅ |
| M6 aviso de 429 | ✅ |
| M7 Google Fonts | ✅ (A.7, segunda ronda) |
| M8 hooks muertos y barril | ✅ (A.2) |
| M9 sobres duplicados | ✅ (A.3, segunda ronda) |
| M10 a11y en `warn` | ✅ (A.6, segunda ronda) |
| M11 xfail de i18n | ✅ quitado; `test_i18n_complete.py` compara en/zh contra es sin xfail |
| M12 skips por seed | ✅ fixtures propias (incluido `test_grc.py`) |
| M13 skip silencioso del e2e | ✅ con `ADMIN_PASS` puesto, un login roto es `pytest.fail` (`tests_e2e/conftest.py`); sin contraseña se salta con motivo explícito |
| M14 registro de auditoría sin trigger/REVOKE | ✅ README corregido (B.1). ⏸ añadir trigger o `REVOKE`: migración de backend, otro frente |
| M15 autoservicio RGPD | ✅ documentado (B.1). ⏸ decide el usuario |
| M16 documentación de retención y jobs | ✅ (B, B.1) |
| M17 cabeza de Alembic y ajustes GRC en `.env.example` | ✅ (B, B.1) |
| B1 token de LiveKit en sessionStorage | ✅ (A.1.7, riesgo bajo aceptado) |
| B2 `document.write` | ✅ (A.1.8) |
| B3 dos confirmaciones | ✅ (A.3) |
| B4 `font-size` en px | ✅ (A.5) |
| B5 paleta de acento | ✅ (A.5) |
| B6 sin stylelint | ⏸ decide el usuario (herramienta nueva; hoy vigilan `scripts/kit/comprobarCss.mjs` y `kit_pendientes --comprobar`) |
| B7 bytes NUL | ✅ |
| B8 scripts de i18n del portal rotos | ✅ |
| B9 `test:e2e` sin destino | ✅ |
| B10 `i18n_baseline.json` | ✅ (A.2, segunda ronda) |
| B11 claves sin uso | ⏸ (A.4): no estaba en las tareas de esta ronda |
| B12 docs desfasados | ✅ (B) |
| B13 tests de solo existencia y skips ABAC imposibles | ✅ los 2 skips imposibles, borrados. ⏸ revisar uno a uno los `hasattr`/`callable`: fuera de esta ronda |
| C.3 `test_imputations_enhanced.py` | ✅ fixtures propias |
| C.3 `test_i18n_complete.py:143` | ✅ |
| C.3 `test_abac_resources.py` | ✅ borrados |
| C.3 infraestructura/paquetes opcionales | ✅ se quedan, con motivo explícito |
| C.3 `tests_e2e/conftest.py` | ✅ (M13) |
| C.3 dependientes del seed | ✅ |
| C.4 aserciones laxas | ✅ (H6) |
| C.4 tests que leen código | ⏸ son guardarraíles de arquitectura a propósito; los adapta quien trocea (24 ficheros adaptados en esta ronda) |
| C.4 `hasattr`/`assert True` | ⏸ (B13) |
| C.4 `time.sleep`/`now()` | ⏸ fuera de esta ronda |
| C.4 `-p no:warnings`, sin cobertura ni umbral | ⏸ decide el usuario (cambia la salida de la suite) |
| Código muerto: hooks, barril, exports, scripts, `test:e2e` | ✅ |
| Código muerto: `i18n_baseline.json` | ✅ regenerado |
| Código muerto: claves i18n | ⏸ (B11) |
| Código muerto: skips imposibles | ✅ |
| Hardcode: 429, Google Fonts, clave BI, paleta, `font-size` | ✅ |
| Hardcode: `business_config.json` | ✅ verificado (A.4) |
| Hardcode: tiempos de sesión e IA en el cliente | ⏸ bajos; ya son constantes con nombre en `_core.ts` |
| Hardcode: ajustes GRC en `.env.example` | ✅ |

