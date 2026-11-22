# Clientes internos: showback, chargeback, portal interno y gobierno (22-11-2026)

La herramienta gestiona clientes externos a los que se factura. Con este cambio
gestiona además **unidades de la propia compañía** (departamentos, unidades de
negocio, filiales, centros de coste) con el mismo modelo de cliente: se les
informa lo que cuestan (showback), se les carga sin factura legal (chargeback)
o se les factura con precio de transferencia (intercompañía), y entran con su
SSO a un **portal interno** para ver sus proyectos, firmar, pedir y valorar.

Migración `193_clientes_internos`. Backend: `app/services/clientes_internos/`,
`app/api/v1/endpoints/clientes_internos.py` (`/internal-clients`) y
`app/api/v1/endpoints/portal_interno.py` (`/internal-portal`).

## 1. Inventario medido (antes de este cambio)

Medido en el código y en una copia de `clarive.db` (22-11-2026).

| Pieza | Qué había | Qué se hace con ella |
|---|---|---|
| `clients` (`app/models/clients.py`) | 2 filas; sin tipo de cliente; `account_manager_id`, `sla_policy_id`, moneda | Se añade `kind` (externo/interno). Los existentes quedan **externos** (server_default). |
| `departments` / `areas` (`app/models/settings.py`) | 8 departamentos, 0 áreas; `manager_id` | Vínculo de la unidad (`department_id`, `area_id`); el jefe de departamento es responsable. |
| `alm_cost_centers` | 0 filas; `department_id`, `manager_id`, `budget_annual` | Vínculo (`cost_center_id`) y criterio para imputar ALM. |
| `organizations` | 2 empresas (multiempresa = grupo) | `group_organization_id`: la empresa del grupo para intercompañía. |
| `users.department` (texto) | 8 de 9 usuarios con departamento | **Los usuarios de la unidad salen de aquí**: sin alta manual. |
| `budgets` (`app/models/mfa.py`) | 1 fila; ya tiene `cliente_id`, `year`, `estado`, versiones | Presupuesto anual de la unidad = presupuesto aprobado con `cliente_id` de la unidad. Nada nuevo. |
| `app/core/umbrales.py` | métrica `presupuesto` (aviso/crítico) | Semáforo de consumo frente a presupuesto. Sin ajustes nuevos. |
| `user_cost_profiles` + `cost_service.cost_per_hour` | 0 perfiles; `imputations.cost_amount` guarda horas × coste | Coste por horas (método `horas_coste`). |
| `rate_tables` / `rate_entries` (`cost_rate`, `billing_rate`) | 0 tablas | Tarifa interna (método `tarifa_interna`): `rate_entries.billing_rate` por perfil (`job_title`). |
| `projects.contract_amount` + `billing_type=fixed_price` | precio cerrado | Método `precio_cerrado`: por hitos aprobados; sin hitos, lineal por meses. |
| `sd_service_items` (catálogo SD) | sin precio | `internal_price`: precio del catálogo interno por petición atendida. |
| `alm_costes.lineas` | coste diario de licencias/equipos con `client_id`, `cost_center_id`, titular | Licencias y equipos de la gente de la unidad, de su centro o cargados a ella. |
| `sw_products` / `sw_instances` (CMDB de software) | 0 productos; `owner_user_id`, `instances.client_id`, `sw_product_licenses` | Aplicaciones de las que la unidad es propietaria y su TCO. |
| `invoices` + `facturas.create_invoice` | 2 facturas | Intercompañía: factura real con la facturación de siempre. |
| `portfolio_proposals` / `cartera_service` | 0 propuestas; `client_id` | Respaldo de «pedir proyecto» si el flujo de demanda no está o no tiene tipos para el portal interno. |
| Flujo de demanda (`app/services/demanda/`, `docs/FLUJO_DE_DEMANDA.md`, migración 195) | lo construye otro agente; punto de entrada `demanda/entrada.py` con `Solicitante(kind="internal_user")` | **Entrada de «pedir proyecto/servicio» del portal interno** (§5.4). |
| `uat_sessions` | firma `client_signed_by` → `client_users` | `internal_signed_by` → `users` (firma del empleado). |
| `project_milestones` | `approved_by` → `users`, `billing_status` | El responsable firma el hito desde el portal. |
| `client_nps` | NPS 0-10, `respondent` texto | `survey_type` (nps/csat) y `respondent_user_id`. |
| `training_courses` | cursos | El plan de adopción enlaza cursos. |
| `approval_engine` + `fuentes.TIPOS` | bandeja común, SoD (`exigir_que_no_sea_suyo`) | Tipo nuevo `internal_charge`: exceso de presupuesto. |
| Portal del proveedor (`proveedores/portal.py`) | portal para usuarios internos con capacidad | Patrón del portal interno (mismo SSO, capacidad propia, alcance en servicio). |
| Portal de clientes (`client_portal_service`) | token de `client_users` | No se usa para internos: ellos ya tienen `User` y SSO. Se reutilizan sus modelos (UAT, encuestas). |

## 2. Modelo

Un solo `Client` con:

- `kind`: `externo` (por defecto) | `interno`.
- `internal_type`: `departamento` | `unidad_negocio` | `filial` | `centro_coste`.
- Estructura: `department_id`, `area_id`, `cost_center_id`, `group_organization_id`.
- `business_owner_id`: responsable de negocio.
- Finanzas: `finance_mode` (`showback` | `chargeback` | `intercompania`),
  `cost_method` (`horas_coste` | `tarifa_interna` | `precio_cerrado` | `catalogo`),
  `internal_rate_table_id`, `transfer_markup_pct`, `erp_account`.

Validación (`unidades.validar`): `kind` e `internal_type`/`finance_mode`/`cost_method`
en sus listas; un externo no lleva campos internos (se limpian); intercompañía
exige `group_organization_id` distinto de la empresa propia; `tarifa_interna`
exige tabla de tarifas; margen entre −100 y 1000 %. Errores con código
(`interno_*`).

Tablas nuevas (migración 193): `internal_client_roles`, `internal_shared_costs`,
`internal_charges`, `internal_charge_lines`, `project_benefits`,
`internal_adoption_items`.

## 3. Quién es de la unidad (sin altas manuales)

`unidades.miembros(db, unidad)`: usuarios activos de la empresa cuyo
`users.department` es el nombre de:

- el departamento de la unidad;
- el departamento del centro de coste de la unidad;
- cualquier departamento del área de la unidad;

más el responsable de negocio y las designaciones de `internal_client_roles`.

Papeles en la unidad (`unidades.papel`):

| Papel | Quién | Ve costes | Firma hitos/UAT | Aprueba excesos |
|---|---|---|---|---|
| `responsable` | `business_owner_id`, jefe del departamento/área/centro, designado `delegado` | sí | sí | sí |
| `finanzas` | designado `finanzas` | sí | no | no |
| `usuario_clave` | designado `usuario_clave` | no | UAT sí | no |
| `miembro` | el resto de la gente de la unidad | no | no | no |
| `direccion` | rol `admin` o capacidad `interno.gestionar` | todo | — | — |

Mínimo privilegio: cada persona ve **solo sus unidades**; la dirección y
finanzas (capacidad `interno.gestionar`) ven todas.

## 4. Coste y finanzas internas (`costes.py`, `cargos.py`)

Coste de una unidad en un periodo = suma de líneas por fuente:

- `horas`: imputaciones en proyectos de la unidad. Según `cost_method`:
  `horas_coste` → `imputations.cost_amount` (o horas × `cost_per_hour`);
  `tarifa_interna` → horas × `billing_rate` de la entrada de la tabla cuya
  etiqueta coincide con el `job_title` (si no, la primera entrada; si no, coste).
- `precio_cerrado`: proyectos `fixed_price` con `contract_amount`: parte de los
  hitos aprobados en el periodo; sin hitos, lineal por meses entre inicio y fin
  (estos proyectos no suman horas).
- `catalogo`: tickets resueltos en el periodo de la unidad con servicio del
  catálogo con `internal_price`.
- `licencias` / `activos`: `alm_costes.lineas` con `client_id` de la unidad, su
  `cost_center_id` o titular persona de la unidad.
- `software`: aplicaciones propias (instancias con `client_id` de la unidad o
  producto con propietario de la unidad): coste de sus licencias enlazadas no
  contado ya en `licencias`, y horas del proyecto del producto.
- `reparto`: servicios compartidos (`internal_shared_costs`) repartidos por
  criterio: `usuarios` (miembros), `tickets` (tickets del periodo), `licencias`
  (asignaciones ALM vigentes de su gente), `software` (instancias propias),
  `fijo` (`fixed_shares` en %).

Intercompañía: total × (1 + `transfer_markup_pct`/100).

**Cargos** (`internal_charges`): `POST /charges/generate` crea el borrador del
mes con sus líneas. Estados: `borrador` → (`por_aprobar`) → `emitido` →
`exportado`; `anulado`.

- Showback: el documento es un informe (no se exporta al ERP).
- Chargeback: nota de cargo interna **sin IVA ni serie legal** (número
  `NC-AAAAMM-NNN`); exportable a CSV de asiento (debe: cuenta de la unidad;
  haber: cuenta de TI).
- Intercompañía: al emitir crea una factura en `invoices` con
  `create_invoice` (IVA de la empresa, cliente = la unidad) y la enlaza.

**Presupuesto** (`presupuesto.py`): presupuestos aprobados vigentes
(`estado=aprobado`, no sustituidos) con `cliente_id` de la unidad y el año.
Consumo = coste del año hasta hoy; tono con `umbrales.tono_de("presupuesto")`.
Emitir un cargo que deja el consumo por encima del 100 % pasa a `por_aprobar`:
lo aprueba el responsable (o la bandeja si hay flujo para `internal_charge`),
nunca quien generó ni quien emitió el cargo (`exigir_que_no_sea_suyo` + SoD).

## 5. Portal interno (`/internal-portal`, capacidad `interno.portal`)

Página `/mi-departamento` dentro de la aplicación (mismo login SSO). Todo se
acota en `portal.py` a las unidades de quien llama.

1. Proyectos y avance, hitos pendientes de firma (responsable firma o rechaza).
2. UAT: sesiones de sus proyectos; el usuario clave o el responsable firma
   (`internal_signed_by`).
3. Tickets de la unidad y SLA/OLA medido (resolución en plazo).
4. **Pedir proyecto o servicio**: `demanda/entrada.py` (flujo de demanda,
   canal portal interno) con `Solicitante(kind="internal_user")`. Si ese
   módulo no está o la empresa no tiene ningún tipo de solicitud activo en el
   canal `internal_portal` (flujo sin configurar), cae a la cartera (`cartera_service.guardar`, propuesta
   con `client_id` de la unidad). Contrato esperado del flujo de demanda:
   `entrada.crear(db, solicitante, datos) -> dict` y
   `entrada.listar(db, solicitante) -> list`. Servicios del catálogo: el
   catálogo del service desk de siempre.
5. Coste, presupuesto y cargos (solo `responsable`/`finanzas`).
6. Satisfacción: NPS o CSAT (una respuesta por persona y mes).
7. Plan de adopción y beneficios de sus proyectos (lectura).

## 6. Gobierno (`gobierno.py`)

- UAT con usuarios clave (designación `usuario_clave`).
- Firma de hitos por el responsable (segregación: no firma quien pidió la
  aprobación del hito).
- SLA/OLA por unidad: tickets del periodo, % en plazo de resolución, OLA
  incumplidos, tono `sla`.
- NPS/CSAT interno con tono `nps`.
- Plan de adopción y formación (`internal_adoption_items`, enlace a cursos).
- Caso de negocio y beneficios (`project_benefits`: línea base, objetivo,
  real; % de consecución).

## 7. GRC

- Datos de empleados: los miembros se deducen de RR. HH. (base legal: relación
  laboral, art. 6.1.b RGPD); no se copian a ninguna tabla. Las respuestas de
  satisfacción con `respondent_user_id` y las designaciones son datos
  personales: retención propia en `bloqueo_legal.TIPOS`
  (`internal_satisfaction`, `internal_client_roles`). Los cargos son registro
  contable: tipo `internal_charges` (desde la emisión).
- Visibilidad por unidad (§3); dirección y finanzas todo.
- Segregación en cargos (§4) y en firma de hitos.
- Auditoría (`audit_log`) de: cambios de campos internos del cliente, roles,
  generación/emisión/aprobación/exportación/anulación de cargos, repartos,
  beneficios, firmas de hitos y UAT.
- Controles nuevos en el informe de cumplimiento
  (`clientes_internos/cumplimiento.py`): unidades sin responsable, unidades
  sin presupuesto, cargos emitidos sin aprobación cuando excedían presupuesto
  (debe ser 0), cargos aprobados por quien los emitió (debe ser 0), chargeback
  sin cuenta ERP.

## 8. Cuadros de mando

- Dirección (`GET /internal-clients/overview`): coste por unidad y por fuente,
  presupuesto frente a real con semáforo, cartera (proyectos activos y
  peticiones abiertas) por unidad.
- Mi departamento (`GET /internal-portal/units/{id}/summary`).

## 9. Permisos (`app/core/capacidades.py`)

| Capacidad | Roles | Qué abre |
|---|---|---|
| `interno.portal` | internos | Portal interno (lo de sus unidades) |
| `interno.gestionar` | admin, pm | Cuadro de dirección, costes, cargos (borrador), beneficios, adopción, roles |
| `interno.cargos` | admin | Emitir, exportar y anular cargos; servicios compartidos |

## 10. API

Gestión `/api/v1/internal-clients` (`interno.gestionar` salvo nota):

```
GET    /overview?year=                          cuadro de dirección
GET    /options                                 selectores de la ficha (finanzas.ver)
GET    /{cid}/members                           personas deducidas y su papel
POST   /{cid}/roles   {user_id, role}           designar (usuario_clave|finanzas|delegado)
DELETE /{cid}/roles/{rid}
GET    /{cid}/cost?desde=&hasta=                líneas y totales por fuente
GET    /{cid}/tco?year=                         aplicaciones propias y su TCO
GET    /{cid}/budget?year=                      presupuesto, consumo, %, tono
GET    /{cid}/sla?desde=&hasta=                 SLA/OLA
GET    /{cid}/satisfaction                      NPS/CSAT
GET    /{cid}/adoption   POST /{cid}/adoption   PATCH|DELETE /adoption/{id}
GET    /projects/{pid}/benefits  POST /projects/{pid}/benefits  PATCH|DELETE /benefits/{id}
GET    /charges?client_id=&period=&status=
POST   /charges/generate {client_id, period}    borrador
GET    /charges/{id}
POST   /charges/{id}/issue                      interno.cargos
POST   /charges/{id}/approve {note}             responsable de la unidad (SoD)
POST   /charges/{id}/reject  {note}             responsable de la unidad
POST   /charges/{id}/cancel  {note}             interno.cargos
GET    /charges/export?period=                  CSV de asientos (interno.cargos)
GET|POST /shared-costs  PATCH|DELETE /shared-costs/{id}   interno.cargos
GET    /shared-costs/{id}/allocation?period=
```

Portal `/api/v1/internal-portal` (`interno.portal`):

```
GET  /me
GET  /units/{cid}/summary
GET  /units/{cid}/projects
GET  /units/{cid}/milestones           POST /milestones/{mid}/sign {approve, note}
GET  /units/{cid}/uat                  POST /uat/{sid}/sign {result: passed|failed, notes}
GET  /units/{cid}/tickets
GET  /units/{cid}/sla
GET  /units/{cid}/cost?year=           (responsable/finanzas)
GET  /units/{cid}/charges              (responsable/finanzas)
GET  /units/{cid}/requests             POST /units/{cid}/requests {title, description, kind, estimated_budget?, wanted_start?, wanted_end?}
POST /units/{cid}/satisfaction {score, comment, survey_type}
GET  /units/{cid}/adoption
GET  /units/{cid}/benefits
```

Clientes (`/api/v1/clients`): `GET ?kind=externo|interno`; la ficha lleva los
campos internos y `members_count`.

## 11. Pantallas

- Clientes: filtro Externos/Internos; formulario con «Tipo» y, si es interno,
  subtipo, estructura, responsable y finanzas; textos adaptados («Unidad
  interna», «Coste», «Presupuesto» en vez de «Cliente», «Facturación»).
- Cartera y paneles: filtro externos/internos por `kind` del cliente.
- `/internal-clients`: cuadro de dirección, cargos, beneficios, adopción.
- `/mi-departamento`: portal interno.
- Configuración única → Finanzas → «Clientes internos»: servicios compartidos
  y criterios de reparto. Avisos contextuales: unidad sin responsable, sin
  presupuesto, sin tabla de tarifas con método `tarifa_interna`, chargeback sin
  cuenta ERP.
- i18n es/en/zh (operador).

## 12. Pruebas

`tests/test_clientes_internos.py` (servicio: validación, miembros, coste,
cargos, presupuesto/aprobación con SoD, portal acotado, retención y controles)
y `frontend/src/__tests__/clientesInternos.test.ts` (estáticas). No se han
ejecutado: lo decide el usuario al final.

## 13. Cierre de pendientes (22-11-2026)

- **Filtro externos/internos** (`client_kind=externo|interno`; sin cliente
  cuenta como externo): `GET /portfolio-intake/proposals` (las propuestas
  traen `client_name` y `client_kind`), `GET /profitability/summary` y
  `/profitability/projects`, `GET /dashboard/projects-health` y
  `GET /portfolios/{id}/dashboard`. Ayudantes en `unidades.py`
  (`filtrar_proyectos`, `filtrar_por_proyecto`, `del_tipo`). En pantalla, el
  componente `frontend/src/components/FiltroTipoDeCliente.tsx` (Select del kit)
  en Cartera, Rentabilidad, Panel de proyectos y el panel de una cartera.
- **Precio del catálogo interno**: `internal_price` en el formulario del
  servicio (Configuración → Service desk → Catálogo, `Input` del kit) y en la
  vista interna del catálogo (`catalog_service._servicio`); no va al portal.
- **Cuenta de TI del asiento**: ajuste por empresa `INTERNAL_IT_ERP_ACCOUNT`
  (grupo `presupuestos`, vacío por defecto; validación en
  `valores_de_negocio`: vacío o 1-40 letras, cifras, espacio, `.`, `_`, `/`,
  `-`). Se edita en Configuración → Finanzas → Clientes internos. Sin ella, la
  exportación responde 409 `interno_sin_cuenta_ti` y el cuadro de dirección
  avisa (`warnings`) si hay unidades con chargeback. La cuenta de cada unidad
  (`erp_account`) se valida con la misma regla (`interno_cuenta_erp_no_valida`).
