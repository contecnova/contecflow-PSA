# Service Desk — manual

Cómo funciona el Service Desk de Contecflow, para quien lo usa (agentes,
responsables, administradores y clientes del portal) y para quien lo instala y
lo opera. Lo descrito aquí está en el código y tiene pruebas automáticas.
Lo que no se ha podido probar contra un sistema real se dice en cada apartado.

---

## Parte I — Uso

### 1. El ciclo de vida del ticket y sus avisos

Cada cambio de un ticket avisa a quien le toca, venga de donde venga: la
pantalla, el portal, el correo, un SMS, un flujo, una regla de escalado o la
monitorización.

| Momento | Quién recibe aviso |
|---|---|
| Se abre | El solicitante (acuse con el número) y el agente asignado; sin agente, la cola. |
| Se asigna | El agente nuevo. |
| Entra en una cola sin agente | Los miembros de la cola. |
| Un agente responde en público | El solicitante, por correo. |
| El solicitante responde | El agente y los observadores. |
| Comentario interno | El agente y los observadores. **Nunca** el solicitante. |
| Se resuelve | El solicitante, con el texto de la resolución. |
| Cambia de estado o de prioridad | Los observadores (la prioridad, solo en la campana). |
| SLA en riesgo o incumplido | El agente (o la cola) y los responsables de la cola. |
| Escalado | Las personas que diga la regla. |
| P1/P2 nuevo, SLA incumplido o escalado | Además, quien esté **de guardia** en la cola, también por SMS. |

Nadie recibe aviso de su propio cambio. La excepción es el acuse de recibo de
quien abre el ticket por el portal o por correo: es justo para esa persona.

Los agentes reciben siempre el aviso en la campana; el correo a agentes se
puede apagar (*Avisos → A quién se avisa*). Los textos se cambian en
**Service Desk → Configuración → Avisos**, por idioma (español e inglés), con
vista previa. Cada aviso se puede apagar y volver a su texto por defecto.

El número entre corchetes del asunto (`[INC-0042]`) se pone siempre: es lo que
hace que la respuesta del cliente vuelva al mismo ticket.

**Seguir un ticket.** En el detalle, *Seguir* te apunta como observador: recibes
sus avisos sin ser el agente.

**Resolver.** *Resolver* pide el texto de la resolución, porque es lo que recibe
el cliente en el correo.

### 2. SLA

Cada política SLA dice cuántas horas hay para responder y para resolver según
la prioridad, y **cuándo corre el reloj**:

- **24x7**: siempre.
- **Un calendario de servicio**: los de *Calendarios SLA* (menú Soporte), con
  jornada, zona horaria, días laborables y festivos. Varios clientes pueden
  compartir uno.
- **Horario propio**: jornada, días y zona de la propia política.

El reloj se para mientras el ticket está pendiente del cliente o de un tercero.
Cambiar la prioridad recalcula los vencimientos desde la apertura, no desde
ahora.

El estado del SLA (*En plazo*, *En riesgo*, *Incumplido*, *En pausa*) se revisa
cada 5 minutos. *En riesgo* quiere decir que se ha consumido el porcentaje de
aviso (por defecto, el 70 %) **en horas del calendario**: un P1 abierto el
viernes a última hora no está en riesgo el domingo. Cada paso a *en riesgo* o a
*incumplido* avisa una sola vez.

**Qué política se aplica.** La del contrato; si no hay, la del cliente; si no,
la política por defecto. En cada política se ve qué clientes y contratos la
usan, y desde ahí se asigna.

**OLA de cada cola.** El SLA mide lo que se le promete al cliente. El OLA mide
lo que tarda **cada cola** con el ticket, y sirve para saber qué equipo lo
retiene. Se fija en *Configuración → Grupos*, en el campo *OLA (horas)*; si se
deja vacío, la cola no tiene OLA.

- El reloj arranca cuando el ticket entra en la cola, venga de donde venga: al
  abrirlo, por una regla de enrutado, por el escalado o porque alguien lo
  mueve. Si pasa a otra cola, el reloj vuelve a empezar con el OLA de la nueva.
- Corre en el calendario del SLA del ticket y no cuenta el tiempo en pausa
  dentro de esa cola.
- Al vencer, avisa **una sola vez** al agente y a los responsables (★) de la
  cola que lo tenía, aunque el ticket ya se haya movido. La plantilla del aviso
  es *OLA de la cola incumplido* (*Configuración → Avisos*), y el mismo evento
  puede arrancar un flujo (*Se incumple el OLA de su cola*).
- En el ticket se ve como *OLA · cola*, con su vencimiento.
- Cambiar las horas de una cola se aplica en la siguiente revisión, cada 5
  minutos, a los tickets que ya están en ella.
- Los tickets que ya estaban abiertos y en una cola al instalar la migración
  108 empiezan a contar desde ese momento, porque no se sabe cuándo entraron.

### 3. Escalado

*Configuración → Escalado.* Cada regla dice **cuándo** (SLA en riesgo, SLA
incumplido, horas sin moverse, sigue sin agente, se reabre tras resolverse) y
**entonces** (avisar al jefe del agente, avisar a los responsables de la cola,
avisar a unas personas, mover a otra cola o subir la prioridad). Se puede
limitar a unas prioridades o a una cola.

Cada regla salta **una vez por ticket**. La de inactividad vuelve a saltar si el
ticket sigue parado otras tantas horas. Debajo se ven las últimas escaladas.

### 4. Correo entrante

*Configuración → Correo entrante.*

- Cada correo al buzón de soporte abre un ticket; quien escribe se reconoce
  como contacto del portal o como usuario.
- Una respuesta con `[INC-0042]` en el asunto se añade al ticket como
  comentario, sin el correo anterior citado. Si estaba resuelto, se reabre; si
  estaba pendiente del cliente, vuelve a curso; si estaba cerrado, se abre uno
  nuevo enlazado.
- Alguien ajeno que cite un número no puede comentar un ticket que no es suyo:
  se le abre uno nuevo.
- Las respuestas automáticas (fuera de oficina, rebotes, listas) se descartan,
  y el mismo correo no se procesa dos veces.
- Los adjuntos se guardan como documentos del ticket.

La pantalla tiene *Probar conexión*, *Leer ahora* y los últimos correos con lo
que se hizo con cada uno.

### 5. Peticiones del catálogo con aprobación

Un servicio del catálogo puede pedir aprobación e indica **quién aprueba**. El
ticket nace *pendiente de aprobación* y no se puede empezar, resolver ni cerrar
hasta que se decide. El aprobador recibe el aviso y lo ve en la pestaña **Por
aprobar**. Aprobar libera el ticket; **rechazar pide el motivo** y cancela el
ticket. El solicitante recibe la decisión. En el portal se ve *Pendiente de
aprobación*.

### 6. Cambios

*Service Desk → Cambios*, con cuatro vistas: Lista, Calendario, Versiones y
Congelaciones.

- **Enviar al CAB.** Un cambio estándar de bajo riesgo se aprueba solo. El
  resto va al comité: los miembros de la cola configurada como CAB; en una
  emergencia, solo sus responsables. Cada miembro vota en el panel del cambio, y
  **votar en contra pide motivo**. Se aprueba al llegar al quórum (por defecto,
  mayoría) y se rechaza en cuanto ya no se puede alcanzar. Un cambio no se
  aprueba editándolo.
- **Programar.** Solo un cambio aprobado, con inicio y fin, y fuera de las
  **congelaciones** (salvo los de emergencia).
- **Calendario.** Los cambios del mes, las versiones y las congelaciones.
  Marca los **choques**: dos cambios a la vez sobre el mismo elemento de
  configuración. Avisa, no bloquea.
- **Versiones.** Agrupan cambios que salen juntos. Una versión no se publica
  con cambios pendientes de implementar.

### 7. Monitorización y guardias

**Monitorización** (*Configuración → Monitorización*). Cada alerta del sistema
de monitorización abre una incidencia con la prioridad de su gravedad, enlazada
a su elemento de configuración. Si la alerta se repite, no abre otra: suma
avisos. Al recuperarse se anota en la incidencia, y si nadie la estaba
trabajando se resuelve sola.

**Guardias** (*Configuración → Guardias*). Calendarios por cola, con turnos.
Arriba se ve quién está de guardia ahora.

### 8. Base de conocimiento

- **Revisión (opcional).** Con la revisión activada, el autor *envía a
  revisión* y un revisor *publica* o *devuelve* con lo que hay que cambiar.
- **Portal.** Mientras el cliente escribe su petición, ve los artículos que
  podrían resolvérsela. Si uno le sirve, pulsa *Me lo ha resuelto*: no abre la
  petición y el artículo cuenta un ticket evitado.
- **Sugerencia al agente.** *Sugerir respuesta* propone un borrador con IA y
  enseña los artículos relacionados y, si contecmind está configurado, los
  documentos relacionados (con los permisos del agente en contecmind). Si la IA
  no está disponible, lo dice; no inventa un borrador.

### 9. Tiempo y facturación

Al registrar tiempo en un ticket se puede marcar **facturable**. Si el ticket
tiene proyecto, el tiempo pasa a los **partes** del agente con las reglas de
siempre: pertenecer al proyecto, tener tarifa, no imputar en fechas bloqueadas,
respetar los topes y redondear a medias horas. Desde los partes llega a la
factura. Si una regla lo impide, el tiempo se queda en el ticket y la pantalla
dice por qué.

### 10. Página de estado

*Configuración → Página de estado.* Componentes, su estado e incidentes
declarados. La dirección pública es `/status?org=<slug>` y hay un fragmento
para insertarla en una web. Cada organización ve solo la suya.

### 11. Flujos que arrancan solos

En el diseñador de flujos, el nodo de **Inicio** puede declarar *Arranca solo
cuando* (se crea un ticket, cambia de estado, el SLA se incumple…) y una
condición, por ejemplo `priority == p1_critical`. Ese flujo no se arranca dos
veces sobre el mismo ticket, y los cambios que hace no disparan otros flujos.
El nodo *Estado* cambia el ticket de verdad; *Notificar* avisa en la campana o
también por correo, a `$assignee`, `$group`, `$requester`, una lista de usuarios
o un rol.

### 12. Herramientas

La pestaña **Herramientas** reúne la asignación recomendada, la
auto-resolución, la correlación de alertas, el despliegue de cambios y el
asistente de llamadas. Lo que hacen, sin adornos:

- **Asignación recomendada:** por reglas ponderadas (carga, histórico,
  habilidades, guardias). No hay modelo entrenado.
- **Asistente de llamadas:** clasifica por palabras clave los turnos que llegan
  ya transcritos. No hay telefonía ni reconocimiento de voz.
- **Analítica predictiva:** estadística sobre el histórico y reglas.

### 13. CMDB y descubrimiento

Hay **una sola CMDB** (*Soporte → CMDB*). Es la misma en la que se elige el CI
de un ticket, un problema, un cambio o un error conocido, y la que alimentan el
descubrimiento automático y los agentes. Hasta noviembre de 2026 había dos y lo
que se editaba en la pantalla no se podía elegir en un ticket.

- **Inventario.** Cada CI tiene código (`CI-0001`), clase, estado (operativo,
  degradado, mantenimiento, retirado), entorno, criticidad, host, IP y versión.
  Además, los **datos propios de su clase**: sistema operativo y RAM en un
  servidor, motor y puerto en una base de datos, imagen y clúster en un
  contenedor… Al cambiar de clase solo se guardan los datos de la nueva.
  Se busca por nombre, código, host o IP.
- **Relaciones.** Desde 🔗: *depende de*, *aloja a*, *conecta con*, *tiene
  copia en*, *lo monitoriza* y *forma parte de*. Se leen desde el CI que las
  tiene («web-01 aloja a Portal»). Alimentan el análisis de impacto, la
  topología, el grafo 3D y la correlación de alertas, que busca la causa en
  aquello de lo que depende el CI afectado y en el servidor que lo aloja.
- **Historial.** Desde 📋: cada campo que cambia, quién lo cambió y cuándo; lo
  que cambia el descubrimiento aparece como «por el descubrimiento».
- **Borrar** un CI lo oculta del inventario; los tickets, problemas y cambios
  que lo citan lo conservan.
- **Descubrimiento.** Los proveedores (AWS, Azure, GCP, Kubernetes, vSphere,
  SNMP) crean y actualizan CIs en la organización del proveedor, marcados como
  *Descubierto*. Un escaneo completo retira lo que el proveedor ya no
  encuentra; un escaneo SNMP puntual no retira nada. Dos proveedores del mismo
  tipo (dos cuentas AWS) ya no se pisan. Si cambia la configuración de un CI
  se marca **Deriva** hasta que se aprueba la línea base.
- **Agentes.** En la pestaña *Agentes* se registra un agente por servidor y se
  copia su token (solo se enseña una vez). Cada envío del agente actualiza su
  CI, y la tabla dice cuándo fue el último y qué CI le corresponde. Revocar un
  agente rechaza sus envíos siguientes.
- **Quién ve qué.** Cada organización ve sus CIs, sus agentes, su deriva y sus
  duplicados; la deduplicación nunca compara CIs de organizaciones distintas.

### 14. Activos (Soporte → Licencias y activos)

Hay **un solo inventario de activos**: el de *Licencias y activos* (ALM), con
proveedores, contratos, licencias, instalaciones y centros de coste. Hasta
noviembre de 2026 había otro, del Service Desk, sin pantalla.

- **Enlace con la CMDB.** En la ficha de un activo, *Ciclo de vida y CMDB →
  CI*, se elige el elemento de la CMDB que sostiene (el servidor físico del CI
  «web-01», el portátil de un puesto…). Así el análisis de impacto de un CI
  enseña sus activos, y el panel de un CI en la topología los lista.
- **Fechas de ciclo de vida.** Además de la garantía: fin de vida del
  fabricante, fin de leasing, próximo mantenimiento y su contrato.
- **Vencen pronto.** Arriba de la pestaña *Activos*, la lista de fechas que
  vencen en los próximos 30, 60, 90 o 180 días, de la más cercana a la más
  lejana; en rojo lo que vence en una semana.
- **Ticket de renovación.** El botón 🔁 de un activo (o *Abrir ticket de
  renovación* en la lista) abre una petición de servicio con el CI del activo.
  Si ya hay una abierta para ese activo, la enseña en vez de abrir otra.
  Además, cada día a las 07:05 se abre sola para lo que vence dentro de
  `SD_ASSET_REFRESH_DAYS` días (por defecto 7; 0 lo apaga).
- **Historial.** El botón 📋 enseña cada cambio: estado, asignación, ubicación,
  CI, fechas, quién y cuándo.

---

## Parte II — Instalación y operación

### 15. Lo que corre en segundo plano (Celery beat)

| Tarea | Cada | Qué hace |
|---|---|---|
| `sd_procesar_eventos_de_ticket` | al confirmar cada cambio, y 1 min | Avisos, correo, webhooks y flujos de la bandeja `sd_ticket_events`. |
| `sla_breach_scan` | 5 min | Estado del SLA, avisos de riesgo e incumplimiento, y escalado. |
| `sd_leer_buzones` | 2 min | Lee el buzón de soporte de cada organización. |
| `asset_expiry_scan` | diario, 07:05 | Abre el ticket de renovación de los activos que vencen dentro de `SD_ASSET_REFRESH_DAYS`. |

Si el broker no responde al confirmar, la tarea periódica recoge los eventos.
Un evento que falla se reintenta hasta `SD_EVENT_MAX_ATTEMPTS` veces y se queda
con su último error en `sd_ticket_events.last_error`.

### 16. Credenciales (Ajustes → Credenciales)

| Proveedor | Para qué |
|---|---|
| SMTP | Correo saliente de los avisos, por organización. |
| Service Desk mailbox | El buzón: `protocol` = `imap` (host, puerto, usuario, contraseña, carpeta) o `graph` (buzón de Microsoft 365). |
| Microsoft 365 / Graph | Aplicación de Azure con permiso de aplicación **Mail.ReadWrite** (para `graph`). Microsoft 365 no admite usuario y contraseña por IMAP. |
| Inbound webhooks | `inbound_email_secret`: el secreto de la pasarela de correo (cabecera `X-Contecflow-Email-Secret`). |
| Monitoring alerts | `ingest_token`: el token de `POST /api/v1/sd/events/{origen}` (cabecera `X-Contecflow-Event-Token`). |
| Twilio | SMS: la firma de Twilio es **obligatoria**; sin `auth_token` no entra ningún SMS. La organización sale del número que lo recibe (`from_number`). |
| contecmind | `base_url`, `client_id`, `client_secret`. La organización de Contecflow tiene que estar dada de alta como tenant de esta aplicación en contecmind. |

### 17. Ajustes (Ajustes → Config. dinámica)

**SLA:** `SLA_BUSINESS_HOURS_ONLY`, `SLA_BUSINESS_START_HOUR`,
`SLA_BUSINESS_END_HOUR`, `SLA_BUSINESS_DAYS` (jornada sin política; días ISO,
1 = lunes) y `SLA_PREDICTION_WARNING_PCT` (umbral de *en riesgo*).

**Service Desk:**

| Ajuste | Por defecto | Qué decide |
|---|---|---|
| `SD_NOTIFY_REQUESTER_ON_CREATE` / `_ON_REPLY` / `_ON_RESOLVE` | sí | Correos al solicitante. |
| `SD_NOTIFY_AGENTS_BY_EMAIL` | sí | Correo a agentes (la campana, siempre). |
| `SD_INBOUND_ADDRESS` | — | Dirección de soporte: identifica a la organización y es el Reply-To. |
| `SD_REOPEN_ON_REPLY` | sí | Una respuesta reabre un ticket resuelto. |
| `SD_CHANNEL_TICKET_TYPE` | incident | Tipo del ticket que abre un correo o un SMS. |
| `SD_MAIL_MAX_PER_RUN` / `SD_MAIL_MAX_ATTACHMENT_MB` | 50 / 15 | Correos por pasada y tamaño máximo de adjunto. |
| `SD_CAB_GROUP_ID` | — | Cola que hace de CAB. Sin ella, un cambio normal no se puede enviar. |
| `SD_CAB_APPROVAL_RULE` | majority | majority, all o any. |
| `SD_CHANGE_AUTO_APPROVE_MAX_RISK` | 30 | Riesgo máximo con el que un cambio estándar se aprueba solo. |
| `SD_EVENT_SEVERITY_MAP` | JSON | Gravedad de la alerta → prioridad. |
| `SD_EVENT_AUTO_RESOLVE` | sí | Resolver la incidencia al recuperarse la alerta si nadie la tocó. |
| `SD_ONCALL_PRIORITIES` / `SD_ONCALL_SMS` | P1,P2 / sí | Qué avisa a la guardia, y si por SMS. |
| `SD_KB_REQUIRE_REVIEW` / `SD_KB_REVIEWER_GROUP_ID` | no / — | Revisión de artículos y quién revisa (sin cola: administradores). |
| `SD_TIME_TO_TIMESHEET` | sí | El tiempo de un ticket con proyecto pasa a los partes. |
| `SD_ASSET_REFRESH_DAYS` | 7 | Días antes de un vencimiento de un activo en que se abre solo su ticket de renovación; 0 lo apaga. |
| `SD_EVENT_MAX_ATTEMPTS` / `SD_EVENT_BATCH_SIZE` | 5 / 200 | Reintentos y tamaño de pasada de la bandeja. |

La búsqueda semántica de la base de conocimiento usa vectores guardados solo
con `SEMANTIC_EMBEDDINGS_BACKEND=transformer`. Con el respaldo TF-IDF busca por
palabras, porque ese codificador fija su vocabulario en cada proceso y sus
vectores no se pueden guardar.

### 18. Monitorización: formato

`POST /api/v1/sd/events/{origen}` con la cabecera `X-Contecflow-Event-Token`.

- **Alertmanager:** el cuerpo tal cual (`{"alerts": [...]}`); la clave es la
  `fingerprint`, el CI sale de `instance`, `host` o `service`.
- **Genérico:** un objeto o una lista con `key` y `title` obligatorios, más
  `status` (firing/resolved), `severity`, `description` y `ci`.

### 19. Seguridad y organizaciones (cambios de 2026-11)

- `GET /sd/catalog`, `GET /sd/kb`, `GET /sd/kb/{id}` y `POST /sd/kb/{id}/helpful`
  piden un cliente del portal o un usuario. Antes respondían sin login con el
  contenido interno de todas las organizaciones. Ninguna página anónima los
  usaba.
- La página de estado pública va por organización (`?org=<slug>`).
- La numeración (secuencias y números de ticket, problema, artículo e
  incidencia mayor) es única **por organización**. Antes la segunda
  organización no podía numerar.
- Un administrador o PM ve los tickets de su organización, también los del
  portal o el correo sin agente. Un empleado ve los suyos, los que tiene
  asignados y los que debe aprobar.
- **Una sola CMDB (migración 110).** `cmdb_items`, `cmdb_relations` y
  `cmdb_categories` desaparecen; sus filas pasan a `sd_configuration_items` y
  `sd_ci_relations` conservando el id. Un CI con el mismo nombre en la misma
  organización se funde con el que ya había en vez de duplicarse; `runs_on`
  A→B pasa a `hosts` B→A; el historial (`cmdb_changelog`) y los agentes
  (`cmdb_agent_registrations`) apuntan ya a la CMDB que queda. La API vieja
  `/cmdb/items`, `/cmdb/relations` y `/cmdb/categories` ya no existe: todo va
  por `/sd/cmdb` (añade `DELETE /sd/cmdb/{id}`, `GET /sd/cmdb/{id}/changelog` y
  `DELETE /sd/cmdb/relations/{id}`; el listado acepta `q`, `ci_type` y
  `status`).
- **Los CIs se ven por organización.** Antes se acotaban solo por responsable o
  proyecto, así que un CI sin ninguno —todos los descubiertos— no lo veía nadie
  salvo el superadministrador. La migración 110 rellena la organización que
  falta desde el responsable, el proyecto, los tickets que citan el CI (si son
  de una sola organización) o, si la instalación tiene una sola organización,
  esa. Si nada de eso la da, se queda sin ella.
- **Descubrimiento y agentes.** El check-in de un agente retiraba los CIs de
  todos los demás agentes, y un escaneo SNMP puntual los de todos los demás
  dispositivos SNMP. Ya no. Los CIs descubiertos nacen en la organización del
  proveedor (antes, sin organización), y la deriva, la salud de la
  reconciliación, los duplicados y los agentes se acotan por organización.
- **Un solo inventario (migración 111).** `sd_assets` y `sd_asset_history`
  desaparecen; sus filas pasan a `alm_assets` y a la nueva `alm_asset_history`
  conservando el id. Un activo con el mismo número de serie que uno de ALM se
  funde con él. Lo que ALM no tiene como columna (código, pedido, proveedor en
  texto, licencia, etiquetas) queda en las notas. Tipos: `cloud` pasa a `vm` y
  el resto a `other`; estados: `deployed` y `loaned` a `in_use`, `in_stock` y
  `pending_order` a `available`, `disposed` a `retired`. `/sd/assets` ya no
  existe; lo nuevo está en `/alm/assets`: `GET /expiring?days=`,
  `GET /by-ci/{ci}`, `GET /{id}/history` y `POST /{id}/refresh-ticket`.
- **WebSocket (avisos en tiempo real).** Desde agosto de 2026 el saludo de los
  cuatro WebSocket (avisos, avisos del portal, chat de colaboración y edición de
  documentos) respondía 500: las guardas globales de la API (zona horaria, ABAC
  y matriz GRC) pedían una petición HTTP que un WebSocket no tiene. La campana
  no recibía nada en vivo. Ahora las guardas no evalúan los WebSocket, que se
  autentican con su ticket de un solo uso (`GET /ws/ticket`). Hay que
  **reiniciar el servidor** para que lo coja.
- **Renovación de activos.** El escaneo diario buscaba si ya había ticket con un
  `LIKE` sobre el título y lo creaba sin organización, así que no lo veía nadie.
  Ahora el activo guarda su ticket abierto (`refresh_ticket_id`), no abre otro
  mientras siga abierto, y el ticket nace en la organización del activo con el
  numerador de siempre.
- **Lo que no se trajo.** La amortización propia del inventario viejo (vida fija
  de 5 años en el código): ALM ya calcula el valor contable con los años de
  cada activo. Las auditorías de licencias y de software, que contaban butacas
  escritas a mano en el activo: ALM las hace sobre licencias e instalaciones
  (*Cumplimiento*).

### 20. Límites conocidos

- Sin probar contra un IMAP, un Microsoft 365, un Alertmanager, un Twilio o un
  contecmind reales: las pruebas los sustituyen.
- Las clases de CI y sus datos propios están fijas en el código
  (`CIType` en el servidor y `CI_TYPE_FIELDS` en la pantalla); no se pueden
  crear clases desde Administración.
- Un CI que llegó sin organización, responsable ni proyecto, en una instalación
  con varias organizaciones, solo lo ve el superadministrador: la migración 110
  no adivina de quién es (véase el apartado 19).
- El OLA tiene un único objetivo por cola, igual para todas las prioridades.
- No hay contratos de soporte (UC). Los proveedores y sus contratos existen en
  ALM (`alm_vendors`, `alm_contracts`), pero un contrato no tiene objetivos de
  respuesta ni de resolución y no se enlaza con los tickets.
- La búsqueda por vectores compara en Python contra todos los artículos
  publicados. Con decenas de miles de artículos haría falta un índice
  vectorial (pgvector).
- La migración 100 (numeración por organización) y la 097 solo cambian
  restricciones en PostgreSQL; en SQLite el esquema sigue saliendo de la cadena
  como antes.
