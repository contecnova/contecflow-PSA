# Proveedores y externalización

Diseño e implementación del 19-11-2026. Migración `189_proveedores_y_externalizacion` (sobre la 188 del asistente de reuniones).
Ampliación del mismo día: migración `191_proveedores_portal_y_aprobacion` (sobre la 190 de la CMDB de
software): portal del proveedor, aprobación por importe con el motor común, fuentes de medición y
selectores con datos reales (§13-§16).

Petición: un subcontratista puede ser una **persona** (freelance), una **empresa
que aporta personas**, una **empresa a la que se externaliza trabajo** o una
**empresa que presta un servicio gestionado** (SOC, service desk, nóminas…). Cada
caso se asigna, se mide y se paga de forma distinta, y todos son terceros con su
GRC.

## 1. Inventario medido (antes de este cambio)

| Pieza | Dónde | Qué hacía | Qué cambia |
|---|---|---|---|
| Proveedor | `subcontractors` (`app/models/enterprise.py`) | Nombre, empresa, contacto, NIF, moneda. Sin tipo: persona y empresa eran lo mismo. | Tipo (`kind`), modos de relación, ciclo de vida, responsable interno, datos de GRC y enlace opcional a `alm_vendors`. |
| Persona externa | `subcontractor_workers` + su `User` rol `subcontractor` (migración 178, `app/services/externos/`) | Recurso planificable con acceso que caduca, responsable interno, coste por tarifa. | Sin cambios de fondo. El freelance **es** su única persona y se crea en el mismo alta. |
| Tarifas | `subcontractor_rates` | Coste/venta por hora por perfil. | Siguen siendo los perfiles; las líneas de precio «por recurso» las referencian. |
| Asignación a proyecto | `subcontractor_assignments` (`externos/asignaciones.py`) | Persona + tarifa + pedido → miembro del proyecto. Admitía asignación **sin persona** (la empresa). | La de persona queda igual. La de empresa sin persona deja de crearse: es un **paquete de trabajo** (outsourcing). La migración convierte las existentes. |
| Horas | `imputations` (externo con acceso) y `subcontractor_timelogs` (sin acceso) | Coste por tarifa en `cost_amount`. | Las horas son el consumo de las líneas «por recurso». |
| Facturas del proveedor | `subcontractor_invoices` + `externos/conciliacion.py` | Factura contra horas × tarifa. | Se añade la conciliación contra la **previsión del periodo** (todas las líneas de precio). La de horas sigue. |
| Contratos de soporte (UC) | `alm_contracts` (`resolution_hours`, `response_hours`) + reloj UC del ticket | Plazo del proveedor de software mientras el ticket está `pending_third`. | Sin cambios. Un servicio gestionado puede apuntar a su contrato ALM si existe. |
| Colas del service desk | `sd_agent_groups` (+ OLA) | Grupos de agentes internos. | Un servicio gestionado se enlaza a **su cola**: los tickets de esa cola son su consumo y su SLA. |
| Coste de proyecto | `costes_de_proyecto.partidas_externas` | Gastos + partes de subcontrata. | Se suman las líneas aprobadas de los estados de cuenta que no son horas (precio cerrado, por unidad, cuota, créditos, bonus, gastos) con proyecto. Las horas ya están en las imputaciones: nunca dos veces. |
| Catálogos editables | `settings_service/catalogos_de_clave.py` | Tipos de proyecto, sectores, categorías de gasto. | Dos catálogos más: **tipos de servicio** y **unidades de cobro** (Configuración). |
| Retención / bloqueo legal | `app/db/bloqueo_legal.py` | 12 tipos. | `supplier_documents` (caducados) y `supplier_access_grants` (revocados). |
| RGPD | `cab_service/gdpr.py`, `supresion_service.py` | Copia y supresión de la persona. | La copia incluye su ficha de proveedor (freelance) y sus accesos; la supresión borra teléfono, notas y dirección de su ficha. |
| Informe de cumplimiento | `informe_de_cumplimiento.py` | 22 controles. | 4 controles de terceros (ver §7). |
| Formación y evaluaciones | `training_service`, `performance_service` | Cualquiera, también externos. | Un externo solo entra si su proveedor lo activa (`training_enabled`). |

## 2. Modelo de relación

`subcontractors.kind`:

- **`freelance`** — persona física. Su alta crea en un paso el proveedor, su
  persona (`subcontractor_workers`) y su usuario (rol `subcontractor`, con o sin
  acceso). Es **el recurso**: aparece en Recursos, capacidad, calendario
  (horario efectivo), tarifas y es asignable a tareas y proyectos. No se le
  asigna nada «como empresa». `freelancer_worker_id` apunta a su persona. Sin
  formaciones ni evaluaciones internas salvo `training_enabled`.
- **`company`** — persona jurídica. Lo que se puede hacer con ella lo dicen sus
  **modos** (`engagement_modes`, combinables y acotables por contrato):
  - **`staff_augmentation`** (empresa con personas): la empresa **no** es
    asignable; sus personas sí, como recursos externos vinculados a ella.
  - **`outsourcing`** (trabajo externalizado): la empresa **es** asignable como
    unidad a tareas, fases, hitos, entregables o proyectos completos mediante
    **paquetes de trabajo**. Sin personas, capacidad ni formaciones; con
    entregables, hitos, aceptación (UAT), informes de avance y SLA.
  - **`managed_services`** (servicio gestionado): catálogo de **servicios
    contratados** (SOC, service desk externalizado, infraestructura, nóminas,
    copias, redes…) con alcance, SLA/KPI, su cola del service desk e informes
    periódicos.

Un freelance también puede tener `outsourcing` (un entregable a precio cerrado),
pero el paquete se asigna a su persona, no a la empresa. Ciclo de vida
(`lifecycle_status`): `onboarding` → `active` ⇄ `suspended` → `offboarded`.

### Reglas de asignación (una sola fuente: `app/services/proveedores/asignabilidad.py`)

Las aplica un `before_flush` sobre `Task` (vale para pantallas, operaciones
masivas, IA, automatizaciones e importaciones):

| Caso | Regla | Error |
|---|---|---|
| `assignee_id` y `supplier_id` a la vez | Excluyentes | 422 `proveedor_asignacion_exclusiva` |
| `supplier_id` de un freelance | Se asigna a su persona | 422 `proveedor_freelance_asigna_persona` |
| `supplier_id` sin modo `outsourcing` | Se asigna a sus personas | 422 `proveedor_no_asignable` |
| `supplier_id` suspendido o dado de baja | No admite trabajo nuevo | 422 `proveedor_no_activo` |
| `supplier_work_package_id` de otro proyecto o proveedor | Debe casar | 422 `proveedor_paquete_no_valido` |
| `assignee_id` = persona de un proveedor suspendido/de baja o persona de baja | No asignable | 422 `proveedor_persona_no_asignable` |

Vistas de carga, capacidad, planificador, nivelación y SmartMatch: solo
`users` (internos + personas externas). Una empresa de outsourcing nunca entra
(no tiene `User`). Visibilidad: la persona externa sigue con la política de
mínimo privilegio (`politica_de_visibilidad`); las rutas de proveedores son de
gestores (lectura) y de admin/PM (escritura y finanzas).

## 3. Contratos y modelos de cobro

`supplier_contracts` (uno o varios por proveedor; plantillas con
`is_template`): tipo (`msa`, `sow`, `service`, `framework`, `freelance`), modos
que cubre, estado (`draft`, `active`, `suspended`, `expired`, `terminated`),
fechas, renovación y preaviso, moneda del proveedor, **mínimo comprometido** y
su periodo, **tope** total, pedido de compra (número e importe), presupuesto y
proyecto o centro de coste al que se imputa, condiciones de pago, gastos
repercutibles y su tope, responsable interno, documento.

`supplier_pricing_lines` (combinables en un contrato):

| `model` | Cobro | Medición automática |
|---|---|---|
| `per_resource` | hora / día / mes por perfil (`rate_id`) | Horas imputadas (+ partes manuales sin duplicar) de sus personas; día = horas / jornada de la empresa; mes = personas con asignación activa, prorrateado. |
| `fixed_price` | Precio cerrado de proyecto, fase, hito o entregable (`work_package_id`) | Al **aceptar** el paquete en el periodo (hitos aceptados). |
| `per_unit` | ticket, incidente, petición, dispositivo/mes, usuario/mes, llamada… (`unit`) | Ticket/incidente/petición: resueltos en su cola en el periodo. Dispositivo/usuario: el último recuento registrado o las unidades contratadas del servicio. Resto: consumo registrado. |
| `subscription` | Cuota fija mensual/trimestral/anual con unidades incluidas y exceso | Prorrateada por meses del periodo; el exceso sobre `included_units` a `overage_price`. |
| `expense` | Gastos repercutidos | Consumo registrado (importe), con tope del contrato. |
| `bonus` | Bonus por objetivo | Regla del servicio (`bonus_rules`). |

Además, por línea: **escalados por volumen** (`tiers`, graduados), **mínimo** y
**tope** por periodo, vigencia. Por servicio: **créditos por SLA**
(`credit_rules`: por debajo de X % de cumplimiento, Y % de crédito sobre lo
facturado por ese servicio) y **bonus** (`bonus_rules`).

### Del consumo al margen

1. **Medición** (`consumo.py`): automática (horas, tickets, hitos aceptados) y
   manual (`supplier_usage_records`: dispositivos, llamadas, gastos…; también
   importada).
2. **Previsión** (`facturacion.prever`): cálculo de todas las líneas del
   contrato en un periodo, con mínimos, topes, escalados, créditos y bonus.
3. **Estado de cuenta** (`supplier_statements`): se cierra el periodo y se
   guarda la previsión con su detalle.
4. **Conciliación** con la factura del proveedor (`subcontractor_invoices`):
   diferencia en moneda del contrato; dentro de
   `PROVEEDORES_TOLERANCIA_CONCILIACION_PCT` queda `reconciled`, fuera
   `disputed`.
5. **Aprobación** con segregación: no aprueba quien cerró el periodo ni quien
   registró la factura (409 `proveedor_segregacion_aprobacion`). La factura
   pasa a `approved`. Con un flujo del motor de aprobaciones para el tipo
   `supplier_statement` que encaje (por importe), «Aprobar» lo envía a la
   bandeja y la decisión se toma allí (§14).
6. **Coste**: las líneas aprobadas que no son horas y tienen proyecto entran en
   `costes_de_proyecto.partidas_externas` como `subcontrata` (rentabilidad,
   EVM y evolución del margen las cuentan). Las horas ya estaban en las
   imputaciones.

Moneda: cada línea en la del contrato; el coste de proyecto se convierte a la
de la empresa con el tipo de la fecha (`get_fx_rate`).

## 4. Outsourcing: paquetes de trabajo

`supplier_work_packages`: alcance `project`, `phase`, `milestone`,
`deliverable` o `tasks`, con su proyecto, fechas previstas, precio cerrado,
criterios de aceptación, sesión UAT opcional, responsable interno y estado
(`planned` → `in_progress` → `delivered` → `accepted` / `rejected`, o
`cancelled`). Las tareas externalizadas llevan `tasks.supplier_id` y
`tasks.supplier_work_package_id` (sin `assignee_id`). Aceptar exige la UAT
superada (`passed`/`conditional`) si el paquete tiene sesión, marca aceptado el
entregable o completado el hito de su alcance y deja el precio en la siguiente
previsión. Informes de avance: `supplier_reports` (también los periódicos de
servicio) con avance, resumen, valores de KPI y riesgos; el responsable interno
los revisa.

## 5. Servicios gestionados

`supplier_services`: tipo (catálogo `supplier_service_types`), alcance,
estado, fechas, **cola del service desk** (`agent_group_id`) y elemento de
catálogo opcional, SLA de respuesta y resolución en horas y objetivo de
cumplimiento (%), KPIs (`kpis`: clave, nombre, objetivo, unidad, sentido),
unidades contratadas (`contracted_units` + `unit`), frecuencia de informe,
créditos y bonus por SLA, contrato ALM (UC) opcional y **fuente de medición**
de dispositivos/usuarios (§15). El elemento de catálogo y el contrato ALM se
eligen en la ficha con datos reales (§16).

Integración con el service desk: los tickets con `assigned_group_id` = su cola
son del proveedor. Su SLA se mide sobre los tickets resueltos en el periodo
(`sla_response_breached`, `sla_resolution_breached`); si el servicio tiene
plazos propios, se miden contra `first_response_at`/`resolved_at`. Ese
cumplimiento alimenta créditos/bonus y el cuadro de mando.

## 6. Cuadro de mando del proveedor (`rendimiento.py`)

Por periodo: cumplimiento de SLA de sus servicios, entregas a tiempo (paquetes
aceptados no más tarde de lo previsto), tasa de rechazo, desviación de factura
(estados conciliados frente a disputados), horas frente a contratadas,
documentos vigentes y riesgo. Puntuación 0-100 ponderada con tono del umbral
`sla` de la empresa (`app/core/umbrales.py`).

## 7. GRC de terceros (`grc.py`)

- **Evaluación de riesgo y due diligence** (`supplier_risk_assessments`):
  criterios 1-5 (acceso a datos, criticidad, dependencia, financiero,
  ubicación/transferencias, seguridad), puntuación, nivel
  (`low`/`medium`/`high`/`critical`) y próxima revisión
  (`PROVEEDORES_REVISION_RIESGO_MESES`, la mitad para alto y crítico). La
  última se copia a la ficha (`risk_level`, `next_review_date`).
- **Documentos** (`supplier_documents`): contrato de encargado de tratamiento
  (RGPD art. 28), NDA, ISO 27001, SOC 2, ENS, seguros (RC, ciber) con
  cobertura, cuestionario de seguridad, certificados de Hacienda y Seguridad
  Social, otros. Caducidad con aviso `PROVEEDORES_AVISO_DOCUMENTO_DIAS` antes
  (trabajo diario `externos-caducidad`, que ya existe).
- **Requisitos**: con `data_access` exige DPA vigente; con riesgo alto o
  crítico, además certificación de seguridad (ISO 27001/SOC 2/ENS) y seguro; NDA
  siempre. Activar un contrato sin lo exigido: 409
  `proveedor_requisitos_grc_pendientes` (lista lo que falta).
- **Registro de accesos** (`supplier_access_grants`): sistema o categoría de
  datos, nivel, si hay datos personales, quién concede, caducidad, revocación.
- **Baja (offboarding)**: termina contratos y servicios, cancela paquetes
  abiertos, revoca accesos, da de baja a sus personas (`externos.ciclo.dar_de_baja`:
  ALM, sesiones, miembros de proyecto) y deja el proveedor `offboarded`.
  Suspender bloquea trabajo nuevo y quita el acceso a sus personas sin darlas
  de baja.
- **Retención y bloqueo legal**: `supplier_documents` (caducados, desde la
  caducidad) y `supplier_access_grants` (revocados, desde la revocación).
- **RGPD del freelance**: es persona física. La copia de sus datos incluye su
  ficha de proveedor y sus accesos; la supresión limpia su ficha (teléfono,
  dirección, notas) además de la supresión general.
- **Auditoría**: toda escritura deja `audit_log` (tablas `supplier_*`).
- **Segregación**: aprobación de estados de cuenta (§3.5).
- **Informe de cumplimiento**: `third_party_dpa` (proveedores con acceso a
  datos sin DPA vigente), `third_party_documents` (documentos caducados de
  proveedores activos), `third_party_reviews` (revisiones de riesgo vencidas) y
  `third_party_access` (accesos sin caducidad o de proveedores dados de baja
  sin revocar).

## 8. Pantallas

- **Subcontratistas** (`/subcontractors`): alta con tipo (freelance en un paso
  con su persona; empresa con modos), insignias de tipo, modos, estado y
  riesgo. Ficha con pestañas: Resumen, Personas (no en outsourcing puro),
  Contratos y precios, Servicios, Paquetes de trabajo, Consumo y facturación
  (consumo, previsión, estados de cuenta, conciliación y aprobación, facturas),
  Rendimiento y Cumplimiento (documentos, riesgo, accesos, suspender, baja).
- **Tareas**: «Externalizar a» (proveedores de outsourcing) excluyente con el
  asignado.
- **Configuración**: catálogos de tipos de servicio y unidades de cobro,
  plantillas de contrato y los umbrales (`PROVEEDORES_*`). El módulo no tiene
  botón «Configurar»: si a una acción le falta un catálogo (tipos de servicio,
  unidades de cobro), su aviso lo explica y enlaza a `/settings/proveedores`
  solo a quien tiene `proveedores.config` (`FaltaConfigurar`). El flujo de
  aprobación de estados de cuenta se diseña en Aprobaciones → Flujos.
- **Ruta y menú**: `/subcontractors` se abre con `proveedores.ver` (gestores,
  la misma guarda que `/api/v1/suppliers`), no con `finanzas.ver`; el menú lo
  muestra en «Clientes y finanzas» a quien la tiene. `/supplier-portal` con
  `proveedores.portal` (externos), en «Mi trabajo».
- **Portal del proveedor** (`/supplier-portal`, §13).

## 9. API (`/api/v1/suppliers`)

Lectura: gestores (`requiere_capacidad("proveedores.ver")`). Escritura,
finanzas y GRC: `requiere_capacidad("proveedores.gestionar")`; plantillas:
`proveedores.config`. Explícitas en cada firma (mismos roles que antes). Migración 191 (más abajo): referencias, contactos del
portal, adjuntos, medición. El portal del proveedor tiene su prefijo
(`/api/v1/supplier-portal`, §13).

```
GET   /suppliers/meta                             enumeraciones
GET   /suppliers/overview                         cuadro global
GET   /suppliers/assignable?project_id=           outsourcing asignables
POST  /suppliers/freelance                        alta en un paso
GET   /suppliers/{id}/profile                     ficha completa
PATCH /suppliers/{id}/classification              tipo, modos, GRC de ficha
POST  /suppliers/{id}/suspend | reactivate | offboard
GET/POST /suppliers/{id}/contracts
PATCH /suppliers/contracts/{cid}
POST  /suppliers/contracts/{cid}/activate | terminate
GET/POST /suppliers/contract-templates ; PATCH/DELETE /suppliers/contract-templates/{tid}
POST  /suppliers/{id}/contracts/from-template/{tid}
POST  /suppliers/contracts/{cid}/pricing          (también para plantillas)
POST  /suppliers/contract-templates/{tid}/pricing ; PATCH/DELETE /suppliers/pricing/{lid}
GET/POST /suppliers/{id}/services ; PATCH /suppliers/services/{sid}
POST  /suppliers/services/{sid}/end ; GET /suppliers/services/{sid}/sla?desde&hasta
GET/POST /suppliers/{id}/work-packages ; PATCH /suppliers/work-packages/{wid}
POST  /suppliers/work-packages/{wid}/start | deliver | accept | reject | cancel
POST  /suppliers/work-packages/{wid}/tasks        {task_ids}
GET   /suppliers/by-project/{project_id}
GET/POST /suppliers/{id}/reports ; POST /suppliers/reports/{rid}/review
GET/POST /suppliers/{id}/usage ; DELETE /suppliers/usage/{uid}
GET   /suppliers/contracts/{cid}/forecast?desde&hasta
POST  /suppliers/contracts/{cid}/statements       {period_start, period_end}
GET   /suppliers/{id}/statements
POST  /suppliers/statements/{stid}/reconcile      {invoice_id}
POST  /suppliers/statements/{stid}/approve | dispute
GET   /suppliers/{id}/compliance
POST  /suppliers/{id}/documents ; PATCH/DELETE /suppliers/documents/{did}
GET/POST /suppliers/{id}/risk-assessments
POST  /suppliers/{id}/access-grants ; POST /suppliers/access-grants/{gid}/revoke
GET   /suppliers/{id}/scorecard?desde&hasta
# Migración 191
GET   /suppliers/references?project_id&sub_id         datos de los selectores (§16)
GET   /suppliers/{id}/portal-contacts                 personas y marca de contacto del portal
PUT   /suppliers/{id}/portal-contacts/{worker_id}     {supplier_portal}
POST  /suppliers/reports/{rid}/attachments            fichero (evidencia) de un informe
GET   /suppliers/reports/{rid}/attachments/{doc}/open enlace firmado (auditado)
POST  /suppliers/metering/preview                     {metering_source, metering_config, unit}
POST  /suppliers/services/{sid}/metering/measure      «Medir ahora» (CMDB)
POST  /suppliers/services/{sid}/metering/ingest       {quantity | items, as_of, system} (SIEM, MDM…)
POST  /suppliers/{id}/metering/import                 {rows: [{service_id, as_of, quantity, system}]}
```

Catálogos: `/settings/supplier-service-types` y `/settings/supplier-billing-units`
(mismo contrato que `/settings/expense-categories`).

## 10. Migración 189 y conservación de datos

Columnas nuevas en `subcontractors`, `tasks` y `subcontractor_invoices`
(`created_by`); diez tablas `supplier_*` y dos catálogos. Clasificación de lo
existente:

- **Freelance** si tiene exactamente una persona activa y el nombre de la
  persona coincide con el del proveedor (sin mayúsculas ni acentos) o el NIF
  es de persona física (DNI/NIE). `freelancer_worker_id` = esa persona.
- Si no, **empresa**. Modos: `staff_augmentation` si tiene personas;
  `outsourcing` si tiene asignaciones sin persona.
- `lifecycle_status`: `active` o `offboarded` según `is_active`.
- Un contrato `framework` «migrado» por proveedor con alguna tarifa,
  asignación o factura, con una línea `per_resource`/hora por tarifa activa y
  el pedido de compra de sus asignaciones.
- Cada asignación sin persona pasa a un paquete de trabajo de alcance
  `project` (con su pedido como precio) y se marca inactiva.

Downgrade: borra tablas y columnas; las asignaciones convertidas se reactivan.

## 11. Ajustes

| Clave | Tipo | Por defecto | Uso |
|---|---|---|---|
| `PROVEEDORES_TOLERANCIA_CONCILIACION_PCT` | float | 2 | Diferencia admitida factura/previsión |
| `PROVEEDORES_AVISO_DOCUMENTO_DIAS` | int | 30 | Aviso de caducidad de documentos |
| `PROVEEDORES_REVISION_RIESGO_MESES` | int | 12 | Próxima revisión (la mitad si alto/crítico) |

## 12. Pruebas

`tests/test_proveedores_y_externalizacion.py` (reglas de asignación, alta de
freelance, cálculo de cada modelo de cobro con escalados/mínimos/topes/créditos,
conciliación y segregación, aceptación con UAT, GRC y baja, migración de
clasificación). Frontend: `frontend/src/__tests__/proveedores.test.tsx`.

Migración 191: `tests/test_proveedores_portal_aprobacion_medicion.py` (bandeja
por importe, rechazo, segregación en la bandeja, disputa que cancela, sin flujo;
portal: sin marca, marca con acceso vigente y auditada, solo lo suyo y sin datos
internos, informes y evidencias, suspendido y caducado; medición CMDB con
retirados fuera, propietarios y software instalado, unidad obligatoria, API con
agregación y sin identificadores, fuente distinta, importación fila a fila,
trabajo diario, mes cerrado; referencias y validación; migración encadenada).
Frontend: `frontend/src/__tests__/proveedoresPortalYMedicion.test.ts`.

## 12 bis. Notas de implementación

- Suspender quita el acceso a sus personas (sesiones revocadas) sin darlas de baja; reactivar no lo
  devuelve solo: el responsable lo concede de nuevo en la ficha de cada persona.
- La baja no borra nada: deja `lifecycle_status = offboarded` y el histórico (contratos, estados de
  cuenta, documentos) para auditoría y retención.
- Estado de un documento: `valid`, `expiring` (dentro de `PROVEEDORES_AVISO_DOCUMENTO_DIAS`) o `expired`.
  Requisitos de grupo que pueden faltar: `security_certification` e `insurance`.
- Avisos de la previsión (`warnings[].code`): `minimo_comprometido`, `tope_alcanzado`, `pedido_superado`,
  `tope_de_gastos`, `sin_cola`, `sin_medicion`. Origen de cada línea (`source`): `hours`, `tickets`,
  `accepted_packages`, `usage`, `contracted_units`, `subscription`, `rule`, `contract`.
- Cuadro de mando: `tone` con los nombres del kit (`success`/`warning`/`danger`), dimensiones 0-100 y peso 0-1.
- El alta de empresa en pantalla es `POST /enterprise/subcontractors` y después
  `PATCH /suppliers/{id}/classification` (tipo, modos, razón social).

## 13. Portal del proveedor (migración 191)

Para las personas externas de un proveedor (`subcontractor_workers` con su
`User` de rol `subcontractor`, el rol «externo»). Servicio:
`app/services/proveedores/portal.py`; API: `/api/v1/supplier-portal`
(`app/api/v1/endpoints/proveedores_portal.py`); pantalla:
`frontend/src/pages/proveedores/PortalDelProveedor.tsx` (`/supplier-portal`,
capacidad `proveedores.portal`, solo rol `subcontractor`, en «Mi trabajo»).

**Quién entra (mínimo privilegio).**

- La empresa marca a la persona como **contacto del portal**
  (`subcontractor_workers.supplier_portal`) en la ficha → Cumplimiento →
  «Portal del proveedor» (`PUT /suppliers/{id}/portal-contacts/{worker_id}`,
  admin/PM, auditado en `subcontractor_workers`). Exige usuario con acceso
  vigente (422 `proveedor_portal_requiere_acceso`) y proveedor activo.
- El acceso caduca con el de la persona (`access_until`, trabajo diario
  `externos-caducidad`): con el acceso retirado o caducado,
  `get_current_user` responde 401 (`externos.ciclo.acceso_vigente`). Suspender
  el proveedor ya quita el acceso a sus personas; dado de baja, el portal
  desaparece.
- Guarda de todas las rutas: capacidad `proveedores.portal` (solo rol
  `subcontractor`; un interno recibe 403). Sin la marca: `GET /me` →
  `{enabled: false}` y el resto 403 `proveedor_portal_sin_acceso`.
- **Solo lo suyo**: ninguna ruta recibe el id del proveedor; sale de la ficha
  de la persona que llama. Lo de otro proveedor es 404.
- **Sin datos internos**: ni responsables, ni notas internas, ni quién cerró o
  aprobó, ni el detalle interno del cálculo (horas por persona). Los importes
  son los del propio proveedor (sus contratos y estados de cuenta).

**Qué hace.**

| Ruta | Qué |
|---|---|
| `GET /supplier-portal/me` | Si es contacto, de qué proveedor, si puede escribir (proveedor activo) |
| `GET /supplier-portal/work-packages` | Sus paquetes de trabajo (alcance, fechas, precio, avance, rechazo) |
| `GET /supplier-portal/services` y `/services/{sid}/sla` | Sus servicios con SLA objetivo, último recuento y SLA medido en su cola |
| `GET /supplier-portal/reports`, `POST /supplier-portal/reports` | Sus informes; subir avance (`progress`, de un paquete), informe periódico (`periodic`), parte de servicio (`service_log`) o evidencia de SLA (`sla_evidence`), con enlaces |
| `POST /supplier-portal/reports/{rid}/attachments` | Fichero de evidencia (mientras el informe no está revisado) |
| `GET /supplier-portal/reports/{rid}/attachments/{doc}/open` | Enlace firmado de un adjunto suyo |
| `GET /supplier-portal/usage?desde&hasta` | Consumo medido del periodo por contrato activo (la previsión) y consumos registrados |
| `GET /supplier-portal/statements` | Sus estados de cuenta |

Los informes llegan a la ficha marcados «Desde el portal»
(`supplier_reports.submitted_via = portal`), con su tipo (`report_type`) y sus
evidencias (`attachments`); el responsable interno del paquete o servicio (o
del proveedor) recibe un aviso y los revisa como siempre. Los ficheros van al
almacén de documentos (`s3_service.file_storage`) con `validate_upload`,
antivirus y tamaño máximo (`MAX_FILE_SIZE_MB`); el `Document` no tiene
proyecto: en `/documents` solo lo ven su autor y administración. Escribir con
el proveedor suspendido: 409 `proveedor_no_activo` (la pantalla queda en solo
lectura).

**GRC.** Auditoría: cada informe (`supplier_reports`), adjunto
(`supplier_report_attachments`, también el bloqueado por antivirus), apertura
de un adjunto (`DOWNLOAD` + `DocumentAccessLog`) y cada consulta de importes
desde el portal (`VIEW_FINANCIAL` en `supplier_usage_records` y
`supplier_statements`). RGPD: el portal no muestra datos personales de nadie de
la empresa; los informes guardan quién los subió (`submitted_by`, se anula si
se suprime el usuario). Retención: los adjuntos siguen la del repositorio de
documentos.

## 14. Aprobación por importe con el motor común (migración 191)

Tipo nuevo `supplier_statement` registrado como los demás:
`approval_engine/fuentes.py` (`TIPOS`, `aplicar`, `comprobar_antes`),
`_FINANCIAL_ENTITY_TYPES` (motor y API: auditoría financiera),
`grc_sod.MODULO_GRC_DE_ENTIDAD` → `invoices` (regla «quien crea facturas no las
aprueba») y la bandeja (`ApprovalsPage`: icono y texto
`approvals.entity_supplier_statement`; el diseñador de flujos lo ofrece).

- **Diseño**: Configuración → Aprobaciones → Flujos, tipo «Estado de cuenta de
  proveedor», con condiciones (`amount_gt`, `amount_gte`, `amount_lt`,
  `amount_lte`, `project_id`), niveles, grupos, quórum y plazos del motor.
  El importe del contexto es el de la factura conciliada (o el esperado) en
  la **moneda de la empresa** (`get_fx_rate` a la fecha de fin del periodo);
  también van `statement_currency`, `amount_in_statement_currency`,
  `project_id`, `subcontractor_id`, `contract_id`.
- **Aprobar** (`POST /suppliers/statements/{id}/approve`, estado
  `reconciled`): si hay flujo que encaje (`elegir_flujo`), se abre la solicitud
  (`fuentes.abrir`) y el estado pasa a `pending_approval` con
  `approval_request_id` (auditoría `SUBMIT`). Si una política la aprueba sola,
  queda aprobado en el acto. Sin flujo que encaje, aprobación directa con
  segregación (como antes).
- **En la bandeja**: antes de anotar una aprobación, la segregación del estado
  (`facturacion.comprobar_en_bandeja`: ni quien cerró el periodo ni quien
  registró la factura; 409 `proveedor_segregacion_aprobacion`), además de la del
  motor (solicitante, reglas SoD). Decisión final aprobada → estado y factura
  `approved` (`via: approval_engine` en la auditoría); rechazada → `disputed`
  con la nota.
- Mientras está en la bandeja, conciliar o aprobar desde la ficha da 409
  `proveedor_aprobacion_en_bandeja`; disputarlo lo saca de la bandeja (la
  solicitud queda `cancelled`). La ficha muestra «En aprobación» y enlaza a la
  bandeja.

## 15. Fuentes de medición de dispositivos y usuarios (migración 191)

`app/services/proveedores/medicion.py`. Para servicios gestionados cobrados por
`device_month` o `user_month` (otra unidad: 422 `proveedor_medicion_sin_unidad`).
Cada fuente cumple la interfaz `FuenteDeMedicion` (`clave`, `automatica`,
`validar(config)`, `contar(servicio, config, fecha)`) y se registra en
`FUENTES`; una fuente nueva (MDM, consola cloud) es una clase más.

| `metering_source` | Cómo | Cuándo |
|---|---|---|
| `manual` | Como antes: consumo registrado o importado; sin él, las unidades contratadas | — |
| `cmdb` | Cuenta en `sd_configuration_items` (activos y no retirados) con los filtros de `metering_config`: `ci_types`, `ci_classes`, `environment`, `vendor`, `location`, `project_id`, `seen_within_days` (último descubrimiento) y `software_product_id` (solo elementos con ese producto instalado y no retirado en `sw_instances` de la CMDB de software). `count`: `devices` (elementos) u `owners` (propietarios distintos = usuarios). Solo LEE la CMDB | Cada día (trabajo `externos-caducidad`) y con «Medir ahora» (`POST /suppliers/services/{sid}/metering/measure`) |
| `external` | Un sistema externo (SIEM, consola del proveedor, MDM; `metering_config.system`) manda el recuento por API (`POST /suppliers/services/{sid}/metering/ingest`, con un token de API de un gestor) o se importa (`POST /suppliers/{id}/metering/import`, o pegado en la ficha) | Cuando llega |

- **Agregación del mes** (`aggregation`): `last` (el último recuento), `max` o
  `average`. Cada muestra se acumula en un único consumo por servicio, mes y
  origen (`supplier_usage_records.source` = `cmdb`, `api` o `import`) con su
  `detail` (muestras, máximo, mínimo, media, último, sistema) y
  `source_system`; la cantidad del consumo es la agregada y la previsión la
  usa como cualquier recuento (`consumo.medir`). Un mes ya cerrado en un estado
  de cuenta no se toca (409 `proveedor_consumo_en_estado_de_cuenta`).
- La vista previa (`POST /suppliers/metering/preview`) dice cuántos contaría hoy
  sin guardar (con hasta 10 códigos de ejemplo de la CMDB).
- El servicio guarda el último recuento (`metering_last_at`,
  `metering_last_quantity`) y el último error (`metering_last_error`): un
  servicio que falla no para a los demás en el trabajo diario.
- Validaciones: fuente desconocida 422 `proveedor_medicion_no_valida`; filtro
  no válido 422 `proveedor_medicion_filtro_no_valido`; agregación 422
  `proveedor_medicion_agregacion_no_valida`; recuento externo en un servicio con
  otra fuente 409 `proveedor_medicion_fuente_distinta`; fecha futura 422
  `proveedor_medicion_fecha_futura`; «Medir ahora» sin fuente automática 409
  `proveedor_medicion_sin_fuente`.
- **RGPD**: solo se guarda el número. Si el sistema externo manda los
  identificadores (`items`: equipos, usuarios), se cuentan sin duplicados y se
  descartan. La CMDB se cuenta por elementos o propietarios; solo se devuelven
  códigos de elemento como ejemplo, nunca personas.
- **Auditoría**: cada muestra (`supplier_usage_records`, CREATE/UPDATE con
  origen, sistema, fecha, muestra, cantidad del mes y agregación) y cada cambio
  de fuente (`supplier_services`).

## 16. Selectores con datos reales (migración 191)

`GET /suppliers/references?project_id&sub_id` (`referencias.py`, gestores,
acotado a la empresa): presupuestos vigentes (ni rechazados ni sustituidos),
centros de coste activos, contratos ALM activos (primero los del mismo
proveedor ALM, ★), elementos del catálogo del service desk, sesiones UAT del
proyecto y, para la medición, tipos y clases de la CMDB y productos de
software. Solo id y etiqueta: sin importes ni datos personales.

- Contrato: **presupuesto** (filtrado por el proyecto elegido) y **centro de
  coste** (también en plantillas).
- Servicio: **elemento del catálogo** y **contrato ALM**.
- Paquete: **sesión UAT** (las del proyecto; con alcance entregable, las de ese
  entregable).

El backend los valida (404 `no_encontrado` con `que` = `presupuesto`,
`centro_de_coste`, `proyecto`, `elemento_de_catalogo`, `contrato_alm`,
`sesion_uat`).

## 17. Migración 191 y ajustes

Solo columnas nuevas (ver la cabecera de
`alembic/versions/191_proveedores_portal_y_aprobacion.py`), cada una solo si no
existe; los informes de servicio que ya había pasan a `periodic`. Downgrade:
quita las columnas. Sin ajustes nuevos: la tolerancia y los avisos siguen en
`PROVEEDORES_*`; el tamaño de los adjuntos es `MAX_FILE_SIZE_MB`.
