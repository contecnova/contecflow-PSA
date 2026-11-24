# Revisión posterior a la implantación (PIR)

Migración `206_pir` (23-11-2026). Una revisión común para **cambios ITSM** (ITIL 4, *Change enablement*) y
**proyectos** (PMBOK, cierre y transición). Antes la PIR eran tres columnas del cambio (`pir_notes`, `pir_success`,
`pir_date`) que solo rellenaba la semilla, sin pantalla; en proyectos no existía.

## 1. Qué es una PIR

Una fila de `pir_revisiones` que cuelga de un cambio (`change_id`) o de un proyecto (`project_id`; si nace de una
puesta en marcha, también del hito `milestone_id`). Lleva:

| Bloque | Contenido |
|---|---|
| Datos | código `PIR-0001` (las migradas, `PIR-H0001`), título, motivo (`implantacion`, `cierre`, `go_live`, `manual`, `migrada`), tipo del origen, obligatoria sí/no, fecha prevista y real, responsable, participantes |
| Criterios de éxito | lista de la plantilla; cada uno **sí / no / parcial** con comentario |
| Resultado | objetivos cumplidos (sí/no/parcial), resultado global (**éxito / éxito parcial / fallo**), resumen |
| Preguntas | las de la plantilla, con su respuesta |
| Efectos | incidencias provocadas (tickets enlazados, de la misma empresa), si hubo marcha atrás y su detalle |
| KPIs | nombre, unidad, antes, después, objetivo |
| Proyectos | beneficios conseguidos frente a previstos (copiados de `project_benefits`, el caso de negocio de Clientes internos; con «Actualizar» el valor real se escribe en el beneficio, auditado) y satisfacción de los interesados (1-5, con la media) |
| Acciones de mejora | `pir_acciones`, con responsable, fecha y la **tarea** que crean |
| Lecciones | entradas del módulo de lecciones con `origen_tipo = "pir"` |

### Estados

`programado → en_curso → enviado → aprobado → cerrado`, más `descartado` (solo si no era obligatoria).

- Guardar el cuestionario pasa `programado` a `en_curso`.
- **Enviar** exige resultado, objetivos, todos los criterios contestados y, en cambios, decir si hubo marcha atrás
  (`pir_incompleta`). Pone la fecha real si no la había.
- **Aprobar** (`pir.aprobar`) y **cerrar**: con segregación (abajo). **Devolver** vuelve a `en_curso` con comentario.
- **Reabrir** (aprobada, cerrada o descartada) pide motivo, cuenta reaperturas y deshace el efecto en el catálogo.
- **Vencida** no se guarda: es `programado`/`en_curso` con la fecha prevista pasada. Sale marcada en listas, ficha,
  CAB e informes y se filtra con `estado=vencido`.

## 2. Programación automática

`app/services/pir/programacion.py`. Solo se programan solas las **obligatorias**; las opcionales, con «Programar
PIR» en la ficha (`pir.gestionar`).

| Origen | Cuándo | Gancho |
|---|---|---|
| Cambio | al pasar a `implemented` (o, con `momento_cambio = cierre`, al cerrarse); un cierre sin PIR previa también la crea | `change_service._aplicar_estado` y el despliegue por fases (`change_management_service`) |
| Proyecto | al completar el hito marcado `is_go_live` (puesta en marcha) y/o al pasar a `completed`/`closed`, según `momento_proyecto` | `milestone_service.complete_milestone`, `project_service.update_and_save_project` |

Fecha prevista: hoy + N días (de la plantilla o de la configuración: 7 en cambios, 30 en proyectos). Responsable: el
dueño del cambio (o el implantador, o el solicitante) o el PM del proyecto. Una programación repetida (mismo origen,
motivo e hito) no duplica. La programación va en un punto de guardado propio: si falla, la transición sigue y queda en
el log.

### Obligatoriedad

1. La plantilla activa del ámbito y tipo (`pir_plantillas.obligatorio`), si lo dice.
2. Si no, la configuración: obligatoria en cambios **normales y de emergencia**, opcional en **estándar**; en
   proyectos, `obligatorio_proyecto` (por defecto no). Se puede decidir por tipo de proyecto con una plantilla de
   ese tipo.

### Trabajo de fondo

Beat `pir-vencidas` (diario, 07:20, por organización, `app.worker.pir_vencidas` → `revisar_vencidas`): aviso al
responsable `aviso_dias_antes` días antes (2) y, al vencer, al responsable y al dueño del cambio o PM. Cada aviso,
una sola vez (`aviso_previo_en`, `aviso_vencido_en`; cambiar la fecha prevista los reinicia).

## 3. Plantillas y configuración

*Configuración → Service desk → Revisión posterior a la implantación* (`/settings/pir`, `pir.administrar`).

- `pir_configuracion` (una fila por empresa; sin fila, valores de fábrica): días por ámbito, aviso previo,
  segregación, cuándo se programa, obligatoriedad por tipo de cambio y de proyecto, y el **proyecto de mejora
  continua** donde nacen las tareas de las acciones de PIR de cambios sin proyecto.
- `pir_plantillas`: por ámbito (`change`/`project`) y tipo (`standard`/`normal`/`emergency` o la clave del tipo de
  proyecto; vacío = cualquiera): nombre, criterios, preguntas, días y obligatoriedad (vacíos = la configuración).
  Gana la del tipo; si no, la del ámbito sin tipo; si no, la de fábrica (ITIL 4 en cambios, PMBOK en proyectos), en
  el idioma de la empresa. La PIR copia su cuestionario al crearse: cambiar la plantilla no altera las ya creadas.

No se usan ajustes en vivo (`RUNTIME_FLAG_GROUPS`) ni variables de entorno: todo está en estas dos tablas.

## 4. Integraciones

- **CAB.** `GET /pir/cab` y el bloque PIR del *Panel del CAB*: cambios cerrados en 90 días, cuántos están
  **cerrados del todo** (sin PIR obligatoria pendiente), con PIR pendiente, vencidas y por aprobar, y la lista de PIR
  de cambios pendientes. `serialize_change` añade `pir_estado` y `pir_obligatoria_pendiente`; la auditoría de gestión
  de cambios (`governance_compliance_service`) cuenta como «emergencia sin PIR» la que no tiene una aprobada o cerrada.
- **Catálogo de cambios estándar** (`cambios_estandar_service`). Una PIR «fallo» aprobada de un cambio estándar suma
  un fallo a su modelo (`anotar_fallo_de_pir`): si el cambio se cerró con éxito, ese éxito pasa a fallo; si se cerró
  como fallo, ya contaba; si aún no se cerró, el cierre posterior no suma (`_pir_ya_contada`). Después se evalúa la
  suspensión por tasa de fallo (la misma regla de siempre, `_evaluar_suspension`). Reabrir o borrar la PIR lo deshace
  (`deshacer_fallo_de_pir`). La PIR lo recuerda en `cuenta_en_modelo`.
- **Informes** (`/pir?tab=informes`, `pir.gestionar`): tasa de éxito por ámbito y tipo (PIR aprobadas o cerradas del
  periodo, por fecha real) y cumplimiento de las obligatorias (a tiempo, tarde, en plazo y vencidas, con la lista;
  las vencidas anteriores al periodo se arrastran).
- **Bandeja y Mi trabajo.** Pestaña *PIR* de `/inbox` y página *Revisiones PIR* (`/pir`, grupo Mi trabajo): las PIR
  en las que soy responsable o participante sin terminar y las enviadas que podría aprobar sin ser implicado.
- **Acciones → tareas.** Cada acción crea una tarea (`task_service.create_task_record`: pertenencia y numeración del
  dominio) en el proyecto de la PIR, en el elegido o en el de mejora continua; sin ninguno, la acción se guarda sin
  tarea y se avisa.
- **Lecciones.** `lecciones.ORIGENES` incluye `pir`; los hechos que se guardan con la lección son el resultado,
  objetivos, marcha atrás, incidencias, criterios y satisfacción (`servicio.hechos_para_leccion`).
- **Avisos** (tipo `system`): asignada, próxima, vencida, aprobada, devuelta, reabierta y acción asignada, en el
  idioma de quien los recibe (`textos_de_salida_pir.py`).

## 5. GRC

- **Auditoría** (`audit_log`, recurso `pir`): `CREATE`, `UPDATE` (campos), `SUBMIT`, `APPROVE`, `REJECT` (devolver),
  `REOPEN`, `DELETE`; también `pir_accion`, `pir_plantilla`, `pir_configuracion` y los cambios de `project_benefit`.
- **Segregación.** Con `segregacion` (por defecto sí), no aprueban ni cierran la PIR el dueño y el implantador del
  cambio, el PM del proyecto ni el responsable de la propia PIR: `exigir_que_no_sea_suyo` da 403
  `sod_no_puedes_aprobar_lo_tuyo` y deja la infracción en GRC (módulo `pir`). La ficha lo explica y oculta *Aprobar*.
- **Retención y bloqueo legal**: tipo `pir_reviews` en `app/db/bloqueo_legal.py` (definido antes de `TIPOS`). Cuenta
  desde el cierre o la aprobación; solo las aprobadas, cerradas o descartadas; se bloquea por PIR, cambio, proyecto o
  responsable. Las acciones se van en cascada; las tareas y lecciones creadas se quedan.
- **Capacidades** (`app/core/capacidades.py`):

  | Capacidad | Roles | Qué abre |
  |---|---|---|
  | `pir.ver` | admin, pm, team_lead, hr, employee | listas, ficha, rellenar las suyas, acciones y lecciones de las suyas (el servicio acota) |
  | `pir.gestionar` | admin, pm, team_lead, hr | programar a mano, reasignar y cambiar la fecha, descartar opcionales, informes |
  | `pir.aprobar` | admin, pm, team_lead | aprobar, devolver, cerrar, reabrir |
  | `pir.administrar` | admin | configuración, plantillas, borrar |

- **Aislamiento.** Todo filtra por la empresa activa (`empresa_activa`); orígenes, responsables, participantes,
  tickets, beneficios y proyectos de las acciones se comprueban en la misma empresa. Sin rol de gestión se ven solo
  las PIR en las que se es responsable, participante o autor. Las tablas llevan `organization_id` (RLS de `env.py`).
- **RGPD** (`app/services/pir/rgpd.py`). Datos personales: ids de responsable y participantes, y nombres libres de
  interesados en la satisfacción. Se van con la retención. Borrar un usuario pone a nulo el responsable y los autores
  (claves ajenas `SET NULL`). La **supresión RGPD** (`supresion_service.suprimir_persona`, antes de seudonimizar la
  ficha) quita su id de la lista JSON `participantes` y tacha («[ERASED]», sin comentario) las entradas de
  `satisfaccion` cuyo interesado es su nombre, usuario o correo; el responsable y los autores se quedan apuntando a la
  ficha ya seudonimizada. Las PIR bajo bloqueo legal (`pir_reviews`) no se tocan y se cuentan en `held`. La
  **exportación RGPD** (`cab_service/gdpr._gdpr_portability_export`) incluye `pir_reviews` (las PIR donde es
  responsable, participante, autora, quien envía, aprueba o cierra, con su papel) y `pir_actions` (sus acciones de
  mejora).

## 6. API (`/api/v1/pir`)

`GET ""` (filtros `origen_tipo`, `origen_id`, `estado` —también `vencido` y `pendiente`—, `resultado`, `solo_mias`,
`solo_obligatorias`, `q`), `GET /mias`, `GET /cab`, `GET /informes/exito`, `GET /informes/cumplimiento`,
`GET|PUT /config`, `GET|POST /plantillas`, `GET /plantillas/fabrica`, `PUT|DELETE /plantillas/{id}`, `POST ""`
(programar), `GET|PATCH|DELETE /{id}`, `POST /{id}/enviar|aprobar|devolver|cerrar|reabrir|descartar`,
`POST /{id}/acciones`, `PATCH /{id}/acciones/{accion}`, `POST /{id}/lecciones`. Errores con código en
`scripts/codemods/errores_con_codigo/pir.json` (`pir_*`).

`/sd/changes/{id}` sigue devolviendo `pir_notes`, `pir_success` y `pir_date`, ahora calculados desde la PIR más
reciente; ya no se escriben con el PATCH del cambio.

## 7. Migración `206_pir`

- Crea `pir_plantillas`, `pir_configuracion`, `pir_revisiones` y `pir_acciones` con sus índices, y
  `project_milestones.is_go_live` (falso por defecto).
- Copia cada cambio con algo en las tres columnas viejas a una PIR `migrada`, `cerrada` (`PIR-H0001`… por empresa;
  éxito/fallo según `pir_success`; resumen = `pir_notes`; fechas = `pir_date`; obligatoria si era normal o de
  emergencia) y **retira** las tres columnas.
- Deshacer real: recrea las columnas con la PIR más reciente de cada cambio, quita `is_go_live` y borra las tablas.
- SQLite (batch) y Postgres; idempotente. Probada sobre una copia de `clarive.db`: subir (1 PIR copiada de 3
  cambios), bajar (el cambio recupera sus columnas), subir y `scripts/comprobar_esquema.py` en verde.
- **Hasta aplicarla**, la app arrancada sigue funcionando en cambios (la ficha da los campos PIR vacíos y los cierres
  del catálogo cuentan como antes), pero las pantallas de PIR y los hitos (`is_go_live`) necesitan la migración.

## 8. Frontend

`frontend/src/components/pir/`: `ListaDePir` (con `FiltrosDeLista`), `FichaDePir` (formulario guiado), `SeccionPir`
(panel del cambio y pestaña *PIR* del proyecto), `PirDelCab`, `BandejaPir`, `InformesPir`, `ConfigPir`;
`pages/PirPage.tsx`; API en `services/api/pir.ts`. El formulario de hito tiene el interruptor *Hito de puesta en
marcha*. Textos en `pir.*` (es/en/zh) y `nav.pir`, `inbox.tab_pir`, `lec.origen_pir`, `ajustes.s_pir`,
`retencion_tipo_pir_reviews`.

## 9. Pruebas

`tests/test_pir.py`: programación automática (cambio, proyecto, API), obligatoriedad por defecto y por plantilla,
flujo y segregación, auditoría, efecto en el catálogo estándar y su vuelta atrás, acciones → tareas, lecciones,
beneficios, aislamiento, CAB, vencidas, bloqueo legal, capacidades y la migración.
