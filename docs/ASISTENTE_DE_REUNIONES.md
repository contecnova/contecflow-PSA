# Asistente de reuniones: Teams, Zoom, Meet, bot invitado y grabación propia

19-11-2026. Diseño escrito antes de implementar; al final, «Estado» dice lo hecho.

## 1. Lo que había (medido)

| Pieza | Fichero | Medido |
|---|---|---|
| Modelo | `app/models/ai_chat.py` `AIMeeting`, `AIMeetingAction` | 2 tablas. Reunión: título, fecha, plataforma (texto libre), duración, participantes (JSON de nombres), transcripción (texto, tope 50 000 caracteres), resumen, decisiones y riesgos (JSON), `status` `processing/done/failed`, `pdf_path` sin uso. Acción: descripción, responsable por nombre (+ id si casa), fecha en texto, `due_date` sin rellenar nunca, tarea creada. |
| Servicio | `app/services/ai_modules/meetings.py` (257 líneas) | Solo procesa una transcripción **pegada**: map-reduce con `call_ai`, salida en el idioma del usuario, responsable resuelto por nombre dentro de la empresa, acciones → tareas (`TSK-`). Sin hablantes ni marcas de tiempo, sin preguntas abiertas, sin enlace a cliente. |
| API | `app/api/v1/endpoints/ai_modules.py` | 4 rutas (`/ai-modules/meetings`, `/process`, `/{id}`, `/{id}/create-tasks`), montadas también sin prefijo (`/meetings`). **Listado y detalle sin acotar**: cualquiera con sesión ve todas las reuniones de su empresa (el filtro de tenant solo separa empresas). |
| Pantalla | `frontend/src/pages/MeetingsAIPage.tsx` (285 líneas) | Lista, detalle, modal «pegar transcripción», «crear tareas». Ruta `/meetings-ai` con la capacidad `proyectos.trabajo`. |
| Voz a texto | `app/services/stt/` | Factoría con 4 proveedores (OpenAI, Azure, Google, whisper local) y respaldo ordenado (`STT_PROVIDER`, `STT_FALLBACK_PROVIDERS`), tope diario de gasto y registro de uso. Texto plano: sin hablantes ni segmentos. |
| Trozos de audio | `app/services/collaboration/_transcription.py` | `transcribe_audio_chunk` (subtítulos de llamadas del chat) y `summarize_text`. |
| Traducción | `app/services/traduccion/servicio.py` | `traducir(db, org, textos, destino, canal=…)` con caché, glosario y tope. 11 canales; ninguno de reuniones. |
| Idioma de salida | `app/services/formato_regional.py` | `idioma_de_salida`, `instruccion_de_idioma_para`. |
| Microsoft Graph | `m365_service.py` (variables de entorno de la instalación) y `bi_o365_service.py` (credenciales **por empresa** en `app_settings`, secreto cifrado con `encrypt_value`) | Ninguno lee reuniones en línea, transcripciones ni grabaciones. |
| Calendario | `app/models/cab.py` `CalendarEvent` | Eventos sincronizados con `project_id`, `user_id`, `location`, `description`. |
| GRC | `app/db/bloqueo_legal.py`, `app/services/retencion.py`, `cab_service/gdpr.py`, `supresion_service.py`, `informe_de_cumplimiento.py` | Ninguno conoce las reuniones. La supresión genérica sí reescribe copias exactas de nombre/correo en cualquier tabla, pero no lo que la persona **dijo**. |

Conclusión: se reutiliza el modelo `ai_meetings` (se amplía), el análisis map-reduce, la creación de tareas, la factoría STT, la traducción con caché, el patrón de credenciales cifradas por empresa y todo el GRC existente. No se duplica nada de eso.

## 2. Las tres vías

1. **Recoger al terminar desde la plataforma.**
   - **Teams** (Microsoft Graph, credenciales de aplicación de la empresa): modo *sondeo* (cada 15 min, el calendario `calendarView` de quien tenga activado «recoger mis reuniones de Teams», reuniones en línea ya terminadas → `onlineMeetings?$filter=JoinWebUrl eq …` → `transcripts` → contenido VTT) o modo *suscripción* (`POST /subscriptions` a `communications/onlineMeetings/getAllTranscripts`, aviso firmado con `clientState`, renovable). Grabaciones: se anota que existen; no se descargan (el audio ya está en Microsoft y la transcripción basta).
   - **Zoom** (Server-to-Server OAuth + secreto del webhook): evento `recording.completed` firmado (`x-zm-signature`, HMAC-SHA256 `v0:{ts}:{cuerpo}`, ventana de 5 min) → fichero `TRANSCRIPT` (VTT) con el `download_token`. Validación de la URL (`endpoint.url_validation`) respondida con el HMAC del `plainToken`.
   - **Google Meet** (API REST de Meet v2, cuenta de servicio con delegación de dominio, JWT RS256 firmado con PyJWT): sondeo de `conferenceRecords` terminados de quien lo active → `transcripts/*/entries` con participante, texto, inicio y fin.
2. **Bot invitado como participante** (Teams, Zoom, Meet, Webex): interfaz `ProveedorDeBots` (`app/services/reuniones/bots/base.py`) y un adaptador concreto **Recall.ai** (`recall.py`): crear bot con la URL (o `join_at` desde un evento de calendario), mensaje en el chat al entrar, estado por webhook firmado (formato Svix: `webhook-id`, `webhook-timestamp`, `webhook-signature v1,<base64 HMAC>`), descarga de la transcripción con hablantes al terminar, salir de la llamada, borrar los medios en el proveedor. **Desactivado por defecto**; activarlo exige la referencia del contrato de encargo de tratamiento (art. 28 RGPD).
3. **Grabar desde la aplicación** (presencial o cualquier herramienta): micrófono o audio de la pestaña (`getDisplayMedia` con audio) en el navegador; `MediaRecorder` corta cada 30 s y sube el trozo; cada trozo se transcribe con la factoría STT existente y se añade con su marca de tiempo. Al terminar, análisis.

4. **Llamadas del chat interno** (añadida el 19-11-2026; origen `chat_call`, `app/services/reuniones/llamadas.py`). La llamada es LiveKit y cada navegador ya sube **su propio** audio a `POST /collaboration/calls/{id}/transcribe-chunk` para los subtítulos en vivo; ese camino alimenta al asistente, así que hay **hablantes reales, cada uno con su usuario**, sin diarización.
   - Botón «Asistente» en la llamada → aviso de grabación obligatorio → `POST /meeting-assistant/calls/{id}/activate`. Se publica el aviso en la conversación y quedan como participantes los miembros de la llamada (y quien entre después, `join_call`).
   - Consentimiento por participante dentro de la propia llamada (banner con Consiento / No consiento; `GET /meeting-assistant/calls/{id}` da `my_consent`). De quien dice «no» no se guarda ni texto ni audio.
   - Con el asistente activo, el trozo se transcribe con los STT permitidos para reuniones (`transcribir_si_graba`), no con el camino de subtítulos (que puede usar un externo sin contrato). Solo cuenta lo dicho después de activar: los subtítulos anteriores no se importan (no hubo aviso).
   - Al colgar (`/end`, encolado como el resumen de siempre) o con «Parar» (`/stop`): análisis, acta automática y mensaje en la conversación con el enlace `/meetings-ai?meeting=<id>` (tarjeta `meeting_minutes`).
   - Vinculación: `conversation_id`, `call_id` y el proyecto del canal (y su cliente). Mismo GRC: visibilidad por participantes, retención, RGPD y auditoría (`RECORDING_START`, `call.assistant_started` en la auditoría del chat).

Las cuatro acaban en el mismo sitio: segmentos (hablante, inicio, fin, texto, idioma) + análisis.

## 3. Estados de una reunión

`programada` (bot creado, aún no entra) → `bot_unido` (en la sala, sin grabar o en sala de espera) → `grabando` (bot grabando o grabación propia en curso) → `procesando` (transcribiendo/analizando) → `lista`; o `error` (con `error_code`). `esperando_consentimiento` cuando la empresa exige consentimiento y falta el de algún participante: no se analiza hasta tenerlo. Los valores antiguos se migran: `processing` → `procesando`, `done` → `lista`, `failed` → `error`.

## 4. Modelo de datos (migración `188_asistente_de_reuniones`, encadenada a `186`)

**`ai_meetings` (se amplía):** `origin` (`transcript`, `upload`, `recording`, `bot`, `teams`, `zoom`, `meet`), `external_id` (id en la plataforma; único por empresa+origen para no importar dos veces), `join_url`, `client_id`, `calendar_event_id`, `ends_at`, `original_language`, `open_questions` (JSON), `error_code`, `notice_confirmed_by`/`notice_confirmed_at` (aviso de grabación), `consent_required`, `bot_provider`, `bot_id`, `bot_status`, `audio_expires_at`, `transcript_expires_at`, `transcript_purged_at`, `minutes_document_id` (acta), `updated_at`.

**`ai_meeting_actions` (se amplía):** `ticket_id`.

**Tablas nuevas** (`app/models/reuniones.py`, todas con `organization_id` y RLS):

| Tabla | Para qué |
|---|---|
| `ai_meeting_participants` | Asistentes y hablantes: `user_id` (si es de la empresa), nombre, correo, rol (`organizador`, `asistente`, `hablante`), consentimiento (`null` sin respuesta, `true`, `false`), cómo y cuándo, idioma. |
| `ai_meeting_segments` | Transcripción por turno: orden, hablante, `participant_id`, `user_id`, `start_ms`, `end_ms`, texto, idioma. |
| `ai_meeting_translations` | Caché del resumen, decisiones, riesgos, preguntas y segmentos traducidos a un idioma (una fila por reunión e idioma; se borra si cambia el análisis). |
| `ai_meeting_audio` | Trozos de audio: orden, clave en el almacén, bytes, tipo, `offset_ms`, transcrito sí/no, caduca. |
| `ai_meeting_events` | Línea de tiempo: cambios de estado, bot, consentimiento, escuchas, descargas, borrados (además de `audit_logs`). |
| `ai_meeting_user_prefs` | Por persona: recoger Teams, recoger Meet, mandar el bot a mis reuniones del calendario, idioma preferido. |

**Configuración por empresa:** `app_settings` clave `reuniones.config` (JSON), como `bi_o365_service`. Los secretos (`client_secret` de Teams y Zoom, secreto del webhook de Zoom, `clientState` de Graph, clave de la cuenta de servicio de Google, clave de API y secreto del webhook del proveedor de bots) se guardan cifrados con `app.core.encryption.encrypt_value`; `GET` solo devuelve `*_set: true/false`.

## 5. Flujos

- **Análisis** (`app/services/reuniones/analisis.py`): reutiliza `map_reduce_analysis` con el texto `[mm:ss] Hablante: texto`. JSON pedido: `title`, `summary`, `decisions`, `risks`, `open_questions`, `actions[{description, assignee_name, due_date (AAAA-MM-DD si se deduce), due_date_text}]`. Responsable: primero participante con usuario cuyo nombre casa, luego `_resolver_responsable` (dentro de la empresa).
- **Idioma:** el original sale del STT o del detector (`traduccion.deteccion`). El detalle se pide con `?language=xx` (por defecto `idioma_de_salida` de quien mira): resumen, decisiones, riesgos, preguntas, acciones y segmentos se traducen con `traducir(..., canal="meetings")` y se guardan en `ai_meeting_translations`. Canal nuevo `meetings` en Traducción; si la empresa no lo activa, se ve el original y la pantalla lo dice.
- **Vinculación automática** (`vinculacion.py`): evento de calendario con la misma URL o el mismo título ±2 h → su `project_id`; correos de asistentes externos → `ClientContact` → `client_id`; código de proyecto en el título; proyecto en el que más asistentes internos son miembros (solo si hay uno claro). Nunca pisa lo que la persona eligió.
- **Acciones con un clic:** tarea (la función de siempre, ahora con `due_date`), ticket del service desk (`Ticket` con número de `next_ticket_number`, origen `meeting`), acta (documento `meeting_notes` con una versión HTML generada, vinculada al proyecto y cliente).
- **Buscar y preguntar:** `GET /meeting-assistant/search?q=` sobre título, resumen y segmentos de las reuniones **visibles**; `POST /meetings/{id}/ask` responde con `call_ai` sobre esa reunión; herramienta de Nexus `search_meetings` con política (`GET /meeting-assistant/search`).
- **Trabajos** (`app/worker.py`, por organización): `reuniones_sondeo` (cada 15 min: Teams/Meet de quien lo activó, bots de calendario de la próxima hora, renovación de la suscripción de Graph) y `reuniones_retencion` (diario).

## 6. API (`/api/v1/meeting-assistant`)

| Método y ruta | Quién | Qué |
|---|---|---|
| `GET /meetings` | `reuniones.usar` | Listado visible (`status`, `project_id`, `q`). |
| `POST /meetings` | `reuniones.usar` | Alta: `origin=recording` (con `notice_confirmed`), `transcript` (texto pegado) o `upload`. |
| `GET /meetings/{id}?language=` | visible | Detalle traducido. |
| `PATCH /meetings/{id}` | gestor | Título, proyecto, cliente. |
| `DELETE /meetings/{id}` | gestor | Borra (409 con bloqueo legal). Auditado. |
| `POST /meetings/{id}/audio` | gestor | Trozo (`file`, `seq`, `offset_ms`). |
| `POST /meetings/{id}/finish` · `/reprocess` | gestor | Analiza. |
| `GET /meetings/{id}/audio` · `/audio/{chunk}` | asistente o `reuniones.ver_todas` | Lista y escucha (`?download=1` descarga). Cada escucha/descarga auditada. |
| `DELETE /meetings/{id}/audio` | gestor | Borra el audio. Auditado. |
| `GET /meetings/{id}/transcript?format=txt\|vtt\|json` | visible | Descarga auditada. |
| `PATCH /meetings/{id}/segments/{sid}` | gestor | Renombrar hablante o asignarlo a una persona. |
| `POST /meetings/{id}/participants` · `DELETE …/{pid}` | gestor | Asistentes. |
| `POST /meetings/{id}/consent` | el propio asistente, o el gestor para uno externo (verbal/escrito) | Consentimiento sí/no. «No» tacha sus segmentos. |
| `PATCH /meetings/{id}/actions/{aid}` | gestor | Responsable, fecha, texto. |
| `POST /meetings/{id}/actions/{aid}/task` · `/ticket`, `POST /meetings/{id}/actions/tasks`, `POST /meetings/{id}/minutes` | gestor | Tarea, ticket, tareas en bloque, acta. |
| `POST /meetings/{id}/ask` | visible | Preguntar a la IA sobre la reunión. |
| `GET /search?q=` | `reuniones.usar` | Búsqueda en lo visible. |
| `POST /bots` · `POST /meetings/{id}/bot/leave` | `reuniones.usar` (y bots activados) | Invitar el bot / sacarlo. |
| `POST /import` | `reuniones.usar` | Traer una reunión concreta de Teams/Zoom/Meet. |
| `GET/PUT /me/preferences` | `reuniones.usar` | Preferencias propias. |
| `GET/PUT /config`, `POST /config/test/{conector}`, `POST /config/teams/subscription` | `reuniones.config` | Configuración (auditada, sin secretos). |
| `GET /gdpr/person`, `POST /gdpr/person/erase` | `reuniones.config` | Copia y supresión de una persona (usuario o correo). |
| `POST /webhooks/meetings/{recall\|zoom\|teams}/{org_id}` | público, firmado | Avisos de las plataformas (CSRF exento por `/api/v1/webhooks/`; en `PUBLIC_ROUTES` del test con su motivo). |

Las 4 rutas antiguas de `/ai-modules/meetings` siguen, ahora acotadas a lo visible.

## 7. Permisos (matriz `app/core/capacidades.py`)

- `reuniones.usar` — internos (`admin`, `pm`, `team_lead`, `hr`, `employee`): grabar, procesar, invitar el bot, ver **sus** reuniones. Sonda estricta `GET /meeting-assistant/meetings` (un externo recibe 403).
- `reuniones.ver_todas` — `admin`: ver y escuchar todas las de la empresa (supervisión).
- `reuniones.config` — `admin`: sección de Configuración y RGPD por persona.

**Visible** = quien la creó, participantes con usuario, responsables de sus acciones, el jefe de proyecto (`projects.pm_id`) del proyecto vinculado, o `reuniones.ver_todas`. **Gestor** = quien la creó, el jefe de proyecto o `reuniones.ver_todas`. Fuera de lo visible: 404 (no se confirma que exista). La ruta `/meetings-ai` pasa de `proyectos.trabajo` a `reuniones.usar`.

## 8. GRC

| Requisito | Cómo |
|---|---|
| Aviso de grabación | Grabación propia: no empieza sin `notice_confirmed` (queda quién y cuándo). Bot: mensaje en el chat al entrar (texto configurable). Plataformas: lo avisa la propia plataforma; queda el origen. |
| Exigir consentimiento | `consent.require_consent` por empresa. Con él, una reunión con participantes sin «sí» queda en `esperando_consentimiento` y no se analiza ni se traduce. Un «no» tacha sus segmentos (`[sin consentimiento]`) antes de analizar. |
| Visibilidad | §7; listados, búsqueda, Nexus y descargas usan la misma función `consultas.visibles`. |
| Retención separada | `retention.audio_days` (por defecto 7, mínimo 1) y `retention.transcript_days` (por defecto 365, mínimo 1). Trabajo diario: borra audio caducado y, de la transcripción, segmentos, texto y traducciones (el resumen y las acciones se quedan: son el registro de trabajo). Además `meetings` es un tipo de la retención general (`bloqueo_legal.TIPOS`), para borrar reuniones enteras. |
| Bloqueo legal | `meetings` en `TIPOS` (campos `id`, `project_id`, `client_id`, `created_by`): no se borra ni a mano (409) ni por retención; el trabajo de retención propio tampoco purga audio ni transcripción de una reunión bloqueada. |
| RGPD | Acceso/portabilidad: `_gdpr_portability_export` añade sus reuniones (como asistente o hablante), lo que dijo, sus consentimientos y sus acciones; también para quien solo tiene correo (externo). Supresión: `suprimir_persona` tacha sus segmentos, anonimiza su fila de participante, borra el audio de esas reuniones y las traducciones en caché, y pide al proveedor de bots borrar los medios. Bajo bloqueo legal, 409 (la regla de siempre). |
| Auditoría | `audit_logs`: configuración (antes/después, sin secretos), escuchar (`LISTEN`), descargar audio o transcripción (`DOWNLOAD`), borrar reunión o audio (`DELETE`), consentimiento (`CONSENT`), bot (`BOT_INVITE`), RGPD (`GDPR_EXPORT`, `GDPR_ERASE`). Además en `ai_meeting_events`. |
| Nada a terceros sin activar y sin contrato | Cada conector nace apagado. El bot exige `bots.contract_reference` para activarse (422 si falta). La transcripción con un STT **externo** (OpenAI, Azure, Google) exige `transcription.allow_external_stt` y su `external_stt_contract`; si no, solo whisper local (y si no hay, error `reuniones_sin_stt_permitido`). |
| Secretos cifrados | `encrypt_value`; nunca salen por la API ni a la auditoría. |
| Webhooks firmados | Recall (Svix HMAC + ventana 5 min), Zoom (HMAC `v0`, ventana 5 min), Graph (`clientState` con `compare_digest`). Sin secreto configurado: 403. |
| Informe de cumplimiento | Controles `meetings_external_processors` (bot o STT externo activo sin contrato → attention), `meetings_retention` (audio o transcripción vencidos sin purgar → attention), `meetings_consent` (analizadas sin consentimiento cuando se exige → attention; info si no se exige). |

## 9. Errores (con código, `MENSAJES_DEL_OPERADOR` + `err_srv` es/en/zh)

`reunion_no_encontrada`, `reuniones_sin_aviso`, `reuniones_no_grabando`, `reuniones_sin_consentimiento`, `reuniones_sin_stt_permitido`, `reuniones_bots_desactivados`, `reuniones_proveedor_sin_contrato`, `reuniones_conector_desactivado`, `reuniones_conector_sin_credenciales`, `reuniones_plataforma_no_encontrada`, `reuniones_firma_no_valida`, `reuniones_url_no_valida`, `reuniones_formato_no_valido`, `reuniones_audio_demasiado_grande`, `reuniones_retencion_no_valida`, `reuniones_sin_proyecto`, `reuniones_sin_transcripcion`.

## 10. Pantallas

- `/meetings-ai` (rehecha): lista con estado y origen; botones **Grabar** (micrófono o pestaña, aviso obligatorio, cronómetro, subida por trozos), **Invitar el bot** (URL), **Traer de Teams/Zoom/Meet**, **Pegar transcripción**; detalle con selector de idioma, resumen, decisiones, riesgos, preguntas abiertas, acciones (tarea/ticket con un clic, responsable y fecha), transcripción con hablante y marca de tiempo, participantes y consentimiento, audio (escuchar/descargar/borrar), acta, preguntar a la IA, buscar. «Configurar» para quien tiene `reuniones.config`; «Mis preferencias».
- Configuración → IA e idiomas → **Asistente de reuniones** (`/settings/reuniones`): consentimiento, retención, traducción, transcripción externa, Teams, Zoom, Meet y bot.

## 11. Pruebas (escritas, no ejecutadas)

`tests/test_asistente_de_reuniones.py`: visibilidad, aviso obligatorio, trozos de audio con STT simulado, análisis simulado, consentimiento, traducción simulada, acciones → tarea/ticket/acta, retención con y sin bloqueo legal, RGPD (copia y supresión como hablante), firmas de Recall/Zoom/Graph, Teams/Zoom/Meet con HTTP simulado, bot con proveedor simulado, contrato obligatorio, informe de cumplimiento, Nexus. Frontend: `frontend/src/__tests__/asistenteDeReuniones.test.tsx`.

## 12. Estado (19-11-2026)

Implementado entero; **sin ejecutar** tests, tsc, eslint ni vitest (decisión del usuario: se prueban al final).
Comprobado solo `py_compile` de lo tocado y que `import app.main` arranca (y `configure_mappers`).

| Pieza | Ficheros |
|---|---|
| Modelos | `app/models/reuniones.py` (6 tablas); `app/models/ai_chat.py` (`AIMeeting` +20 columnas y relaciones, `AIMeetingAction.ticket_id`); registro en `app/models/__init__.py` |
| Migración | `alembic/versions/188_asistente_de_reuniones.py` (encadenada a `186`; ver «Avisos») |
| Servicios | `app/services/reuniones/`: `config`, `consultas`, `servicio`, `analisis`, `vinculacion`, `traduccion`, `transcripcion`, `almacen`, `eventos`, `webhooks`, `trabajos`, `rgpd`, `cumplimiento`, `llamadas` (cuarta vía), `conectores/{teams,zoom,meet}.py`, `bots/{base,recall}.py` |
| API | `app/api/v1/endpoints/reuniones.py` (`/meeting-assistant/*` y `/webhooks/meetings/*`), registrada en `app/api/v1/routers/ai_domain.py`; rutas antiguas acotadas en `ai_modules.py` y `ai_modules/meetings.py` (estados nuevos) |
| Permisos | `app/core/capacidades.py` (`reuniones.usar`, `reuniones.ver_todas`, `reuniones.config`); `frontend/src/permisos/{capacidades,navegacion}.ts` |
| Errores | 17 códigos en `MENSAJES_DEL_OPERADOR` (`app/core/codigos_de_error.py`) y `err_srv` es/en/zh. Ningún error nuevo sin código (`scripts/errores-sin-codigo.json` sigue `{}`) |
| GRC | `meetings` en `app/db/bloqueo_legal.py` (retención general + bloqueo); `cab_service/gdpr.py` (copia con `meetings`, personas solo con correo); `supresion_service.py` (tacha lo dicho antes de seudonimizar); `informe_de_cumplimiento.py` (3 controles); canal `meetings` en `traduccion/ajustes.py` |
| Chat | `app/api/v1/endpoints/collaboration/calls.py` (unirse → participante; trozo → `transcribir_si_graba` + `registrar_fragmento`; colgar → `llamadas.cerrar`); `frontend/src/pages/CallPage.tsx` |
| Worker | `reuniones_sondeo` (*/15) y `reuniones_retencion` (03:40), por organización |
| Nexus | herramienta `search_meetings` (`ai_chat/tool_execution/meetings.py`, `schema.py`, `politica.py`, `executor.py`) |
| Frontend | `pages/MeetingsAIPage.tsx` rehecha; `components/reuniones/*` (grabador, detalle, modales, `ConfigReuniones`); `services/api/reuniones.ts`; sección `reuniones` en `catalogoDeAjustes.tsx`; canal en `TraduccionSection.tsx`; i18n es/en/zh (bloque `reuniones`, `err_srv`, `ajustes.s_reuniones`, `traduccion_admin.canal.meetings`, `retencion_tipo_meetings`, `informe_control_meetings_*`) |
| Pruebas escritas | `tests/test_asistente_de_reuniones.py` (30 casos, terceros simulados); `tests/test_asistente_de_reuniones_llamadas.py` (4 casos de la cuarta vía); `tests/test_route_auth_coverage.py` (3 webhooks en `PUBLIC_ROUTES`); `frontend/src/__tests__/asistenteDeReuniones.test.tsx`; fila nueva en `configuracionUnica.test.ts` |

**Decisiones tomadas al implementar**

- Grabación propia: cada 30 s el navegador cierra el `MediaRecorder` y abre otro sobre la misma pista, para que cada trozo sea un WebM completo (con `start(30000)` solo el primero lleva cabecera y los demás no se transcriben sueltos).
- Sin diarización en la grabación propia: cada trozo es un segmento sin hablante con su marca de tiempo; se renombra o se asigna a una persona después (`PATCH …/segments/{id}`, con `apply_to_speaker` para todos los del mismo hablante). Teams, Zoom, Meet y el bot sí traen hablantes.
- El audio de la grabación propia vive en `uploads/reuniones/<empresa>/<reunión>/` (no en el almacén de documentos, que tiene otra retención).
- Teams: las grabaciones no se descargan (basta la transcripción; el audio ya está en Microsoft).
- Consentimiento: «completo» = todos han respondido; un «no» no bloquea, tacha lo que dijo y se reanaliza.
- Retención de la transcripción: borra segmentos, texto y traducciones; el resumen y las acciones se quedan.

**Avisos**

- **Migración:** el otro agente (proveedores y externalización) prepara una revisión `187` y aún no estaba en disco al crear la `188`, que se encadenó a la head visible (`186`). Si su `187` también cuelga de `186` habrá **dos heads**: hay que cambiar `down_revision` de la `188` a la `187` (o hacer un `merge`).
- Requisitos en Entra para Teams: permisos de aplicación `OnlineMeetings.Read.All`, `OnlineMeetingTranscript.Read.All`, `Calendars.Read` y una *application access policy* de Teams. Meet: cuenta de servicio con delegación de dominio y ámbito `meetings.space.readonly`. Zoom: app Server-to-Server OAuth con `recording:read` y el secreto del webhook.
- Los textos de eventos `linked`, `asked` y `gdpr_erased` no tienen etiqueta en la pantalla (se ven con su nombre).

## Bot activado por defecto (19-11-2026)

Por decisión del usuario, `bots.enabled` viene **activado** por defecto (`app/services/reuniones/config.py`,
`POR_DEFECTO`). Activado no significa que salgan datos: invitar el bot sigue exigiendo la referencia
del contrato de encargado de tratamiento (RGPD art. 28) y la clave del proveedor (`bots.proveedor`
lanza `reuniones_proveedor_sin_contrato` / `reuniones_conector_sin_credenciales`). Guardar la
configuración con el bot activado y sin contrato ya no da error. La pantalla solo lo ofrece como
disponible con contrato y clave (`available.bots`), y el informe de cumplimiento sigue señalando
«bot activado sin contrato».

**Bot en el calendario, por defecto para todos (19-11-2026).** `bot_for_my_calendar` viene activado:
la tarea de sondeo invita el bot a las reuniones con enlace (Teams, Zoom, Meet, Webex) de la próxima
hora del calendario de toda persona interna activa, salvo quien lo desactive en «Mis preferencias».
Los externos (`subcontractor`) no entran. Sin contrato ni clave del proveedor no se envía nada.
