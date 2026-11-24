# Chat del portal (operador ↔ cliente)

24-11-2026. Las conversaciones formales del portal (las «gobernadas»: política GRC por tema, ocultación de datos
sensibles, aprobación previa, SLA de primera respuesta) pasan a tener lo mismo que el chat interno. Migración
`209_chat_del_portal_completo` (padre `208_empresa_obligatoria_y_portal`) y, para la pestaña «Chat» (§9),
`210_chat_del_portal_colaboracion` (padre 209) y, para el chat en vivo de Soporte (§10),
`211_chat_en_vivo_completo` (padre 210). Los tres chats usan la MISMA pantalla que el chat interno (§11).

- Operador: **Clientes → ficha → Portal → Conversaciones** y **Portal de clientes → Solicitudes**
  (`TeamGovernedConversationInbox`, `frontend/src/components/portal/GovernedConversations*.tsx`).
- Cliente: **Portal → Mensajes → Formal** (`ClientGovernedConversationInbox`).
- Backend: `app/api/v1/endpoints/portal_conversations.py` y `app/services/portal_conversation_service/`
  (`adjuntos`, `interaccion`, `llamadas`, `en_vivo`, `ajustes`, `rgpd`).

## 1. Qué hay en cada lado

| Función | Operador | Cliente |
|---|---|---|
| Texto con enlaces (se abren en otra pestaña, `noopener`, URL saneada) | sí | sí |
| Imágenes (miniatura y ampliación) y ficheros (descarga) | sí | sí |
| Emojis en el texto (selector del kit) y reacciones | sí | sí |
| Responder citando un mensaje | sí | sí (solo cita lo que puede ver) |
| Editar y borrar el propio mensaje (plazo por empresa) | sí | sí |
| Ver el historial de ediciones y borrados de un mensaje | sí | no |
| «Escribiendo…» y «Leído» | sí | sí |
| Tiempo real (mensajes, reacciones, leído, llamadas) | sí | sí |
| Notas internas | sí | no (nunca las ve) |
| Aprobar o rechazar mensajes pendientes | sí | no |
| **Iniciar** llamada o videollamada | sí (`clientes.llamar`) | **no** |
| Aceptar, rechazar, colgar | colgar y unirse | aceptar, rechazar y colgar |

Reutilizado del chat interno: la validación de subidas (`app/core/uploads.py`), el antivirus y DLP
(`collaboration.files.escanear`), el almacén de objetos (`collaboration._storage`), la firma de tokens de LiveKit
(`collaboration.livekit`), la conexión a la sala (`livekit-client`, como `CallPage.tsx`), el transporte en vivo
(`service_desk.canales_en_vivo._empujar` sobre los WebSocket `/ws/notifications` y `/ws/portal-notifications`) y,
en el kit, `SelectorDeEmoji` (con `REACCIONES_RAPIDAS`) y `TextoConEnlaces`.

Las conversaciones del **chat anterior** (`legacy:*`) siguen como estaban: texto y notas internas; sin adjuntos,
reacciones, edición ni llamadas (devuelven 422 con código).

## 2. «Solo el operador llama»

Se impone en el servidor, no solo en la interfaz:

1. **No hay vía de servicio** por la que un cliente cree una llamada. `llamadas.iniciar` recibe un usuario del
   equipo y su ruta (`POST /portal/conversations/team/{id}/calls`) exige la capacidad **`clientes.llamar`**
   (dirección, PM, jefes de equipo y RRHH por defecto; un rol personalizado puede quitarla).
2. La ruta del portal **`POST /portal/conversations/{id}/calls` existe a propósito y siempre responde 403
   `portal_llamada_solo_operador`**, y el intento queda en la auditoría (`call_start_denied`).
3. El cliente solo **acepta** (si suena o está en curso; es la única forma de recibir su token de LiveKit),
   **rechaza** (si suena) o **cuelga**. Aceptar comprueba además que la llamada la inició alguien del equipo.
4. La interfaz del cliente no tiene botón de llamar: solo el aviso de llamada entrante con *Aceptar* y *Rechazar*.

Por empresa (**Configuración › Portal › Chat del portal**, `org.administrar`):

| Ajuste | Defecto | Efecto |
|---|---|---|
| `PORTAL_CHAT_CALLS_ENABLED` | sí | Apagado: llamar da 403 `portal_llamadas_desactivadas` |
| `PORTAL_CHAT_VIDEO_ENABLED` | sí | Apagado: videollamar da 403 `portal_videollamadas_desactivadas` (voz sigue) |
| `PORTAL_CHAT_CALL_RING_SECONDS` | 60 | Sin respuesta en ese tiempo, la llamada pasa a `missed` |

Otras reglas: una llamada viva por conversación (409 `portal_llamada_en_curso`); la conversación tiene que tener
un cliente (422 `portal_llamada_sin_cliente`); para llamar o entrar hay que participar en la conversación o
administrar la empresa (403 `portal_llamada_sin_acceso`); cerrada o archivada, 409 `conversacion_cerrada`.

**Grabación.** Las llamadas del portal **no se graban ni se transcriben**: el token no lleva permiso de grabador y
no pasan por el asistente de reuniones. El cliente lo ve en el aviso de llamada y dentro de la llamada («Esta
llamada no se graba ni se transcribe»). Si algún día se graban, hará falta consentimiento previo del cliente y
entrar en retención y RGPD como `meetings`.

## 3. Seguridad de los ficheros

- **Activación, tipos y tamaño por empresa:** `PORTAL_CHAT_ATTACHMENTS_ENABLED`, `PORTAL_CHAT_ALLOWED_EXTENSIONS`
  (solo acotan el catálogo aprobado de la plataforma; el SVG queda siempre fuera porque puede llevar script) y
  `PORTAL_CHAT_MAX_FILE_MB` (nunca más que `MAX_FILE_SIZE_MB`). Se lee por trozos y se corta al pasarse.
- **Contenido, no solo extensión:** `validate_upload` (extensión, MIME declarado, ejecutables, comprimidos,
  coherencia declarado/real por bytes mágicos) y, además, que la extensión case con lo que dicen los bytes
  (`adjuntos.MIME_POR_EXTENSION`): un PNG renombrado a `.pdf` se rechaza (415 `portal_adjunto_contenido_no_coincide`).
- **Antivirus y DLP** como el chat interno; si cualquiera lo rechaza, el adjunto queda en cuarentena: se ve en el
  chat pero no se descarga (409 `portal_adjunto_en_cuarentena`).
- **Almacén:** clave `portal-chat/<empresa>/<conversación>/<marca>_<nombre seguro>`.
- **Descarga solo por la API con sesión** (nunca enlaces firmados al portador): equipo, si participa en la
  conversación o administra la empresa; cliente, si participa (él o su cliente), es de la misma empresa, ve el
  proyecto y ve el mensaje (no nota interna, no bloqueado, no pendiente de aprobación ajeno). Se sirve como
  `attachment`, con el tipo real, `X-Content-Type-Options: nosniff` y `Cache-Control: private, no-store`. La vista
  previa de imágenes la hace la pantalla desde un blob.
- **Aislamiento de empresa:** todas las consultas filtran por `organization_id` de la conversación, además del
  filtro de tenant de la sesión y la RLS; el acceso del cliente comprueba explícitamente su empresa.

## 4. Edición, borrado y rastro

- Solo el autor, solo texto o pie de adjunto, dentro de `PORTAL_CHAT_EDIT_WINDOW_MINUTES` (60; 0 = sin plazo).
- **Editar** vuelve a pasar la política GRC del tema: se ocultan los datos sensibles y, si la política exige
  aprobación para ese lado, el mensaje vuelve a «pendiente de revisión» (editar no salta una aprobación).
- **Borrar** es lógico: el mensaje queda como «Mensaje eliminado» para todos, sus reacciones se van y sus adjuntos
  se quitan del almacén al confirmar. Bajo bloqueo legal de un adjunto, 409 `portal_mensaje_bajo_bloqueo_legal`.
- **Rastro:** el texto anterior de cada cambio en `portal_conversation_message_versions` (solo lo ve el equipo:
  *Ver historial*) y la entrada en `portal_conversation_audits`.
- **Reacciones:** una por (empresa, mensaje, autor, emoji): los únicos `uq_portal_conv_reaction_user` y
  `_client` llevan `organization_id` delante, como el resto de tablas con empresa (24-11-2026, prueba general;
  `tests/test_unicos_por_organizacion.py`).
- **Ficheros al borrar:** los oyentes que quitan del almacén el fichero de un adjunto borrado (después de
  confirmar; nada si se deshace) viven en `app/db/portal_chat_borrado.py` y los registra `app/models/__init__.py`
  (24-11-2026: un modelo no importa servicios).
- **Respuestas de la API:** las listas (mensajes, conversaciones, llamadas, «suenan», versiones) van en el sobre
  de listas `{"items": [...], "meta": {...}}`; los objetos sueltos, en `{"data": ...}`.

## 5. GRC

**Auditoría** (`portal_conversation_audits`, por conversación): `message_sent`, `message_sent_by_client`,
`message_edited`, `message_deleted`, `attachment_uploaded`, `attachment_quarantined`, `attachment_downloaded`,
`attachment_deleted`, `call_started`, `call_accepted`, `call_declined`, `call_missed`, `call_joined`, `call_ended`
y `call_start_denied`. Los cambios de ajustes del grupo `portal_chat` quedan en la auditoría de ajustes.

**Retención y bloqueo legal** (GRC → Retención, `app/db/bloqueo_legal.py`):

| Tipo | Desde | Bloqueo por |
|---|---|---|
| `portal_conversation_attachments` | la subida (borrar la fila borra el fichero al confirmar) | id, conversación, subido por (cliente o equipo) |
| `portal_conversation_message_versions` | el cambio | id, mensaje, editado por (cliente o equipo) |
| `portal_conversation_calls` | el final (solo terminadas, rechazadas o perdidas) | id, conversación, iniciada por, contestada por |

**RGPD** (Empresa → RGPD, `cab_service/gdpr.py` → `portal_conversation_service/rgpd.py`), para la persona que es
usuario del portal:

- **Acceso y portabilidad:** sus mensajes (texto original), el rastro de sus ediciones, sus adjuntos (nombre, tipo,
  tamaño, fecha y huella SHA-256), sus reacciones y las llamadas que contestó, rechazó o colgó.
- **Supresión:** «[ERASED]» en el texto de sus mensajes, se borran sus versiones, adjuntos (fila y fichero) y
  reacciones; las llamadas quedan como metadatos de servicio, con la cuenta ya anonimizada. Se hace antes de
  anonimizar la cuenta (se la encuentra por el correo). Bajo bloqueo legal de un adjunto suyo, 409 antes de tocar
  nada.

**Privilegios por capacidad:** el equipo usa las rutas con `clientes.gestionar`; llamar y unirse a una llamada,
`clientes.llamar`; los ajustes, `org.administrar`. El cliente, solo con su sesión del portal y sobre lo suyo.

**Arreglos de paso (GRC):** el cliente veía mensajes del equipo **pendientes de aprobación** (solo se ocultaban
los bloqueados) y, en la lista de conversaciones, el último mensaje aunque fuera una **nota interna**; además
recibía `raw_body` (texto sin ocultar) y notas de moderación. Ahora no. El cliente podía mandar cualquier
`message_type` del enum por la ruta de texto; ahora solo `text` (422 `portal_tipo_de_mensaje_no_valido`), y el
mensaje citado tiene que ser de la misma conversación y visible para quien cita.

## 6. Tiempo real

Por los WebSocket que ya existen. El servidor empuja `{"type": "portal_conv", "event": ..., "conversation_id"}`
solo a los participantes (equipo por id de usuario; cliente por `client:<id>`, incluidos los usuarios del cliente
participante). Eventos: `message`, `reaction`, `read`, `typing` (con nombre) y `call` (`call_id`, `status`,
`kind`). Nunca viaja el contenido: cada lado lo pide por la API, que aplica sus permisos (el cliente no se entera de
notas internas ni de mensajes pendientes de aprobación). La pantalla manda `{"type": "portal_conv_typing",
"conversation_id"}` como mucho cada 3 s; el servidor comprueba que quien lo manda participa. Sin socket, las
pantallas siguen con su sondeo.

## 7. Errores con código

`portal_adjunto_tipo_no_permitido`, `portal_adjunto_contenido_no_coincide`, `portal_adjunto_no_disponible`,
`portal_adjuntos_desactivados`, `portal_adjunto_no_encontrado`, `portal_adjunto_en_cuarentena`,
`portal_adjunto_sin_acceso`, `portal_mensaje_citado_no_valido`, `portal_tipo_de_mensaje_no_valido`,
`portal_mensaje_no_editable`, `portal_mensaje_no_propio`, `portal_mensaje_ya_borrado`,
`portal_mensaje_fuera_de_plazo`, `portal_mensaje_bajo_bloqueo_legal`, `portal_reaccion_no_valida`,
`portal_llamada_tipo_no_valido`, `portal_llamada_no_disponible`, `portal_llamadas_desactivadas`,
`portal_videollamadas_desactivadas`, `portal_llamada_sin_cliente`, `portal_llamada_sin_acceso`,
`portal_llamada_en_curso`, `portal_llamada_no_encontrada`, `portal_llamada_terminada` y
`portal_llamada_solo_operador`. Están en `app/core/codigos_de_error.py` (catálogo del portal), en los 8
diccionarios del portal y en es/en/zh del operador. Los de subida (`subida_*`, `fichero_demasiado_grande`) tienen
ahora también su texto en los 8 idiomas del portal.

## 8. BPM

El catálogo de procesos sembrados (`app/services/bpmn_process_service.py`, `PROCESS_CATALOGUE`) tiene
**Conversación del portal (chat y llamadas)** (`portal_conversation`, service desk), con textos en es/en/zh en
`frontend/src/pages/bpm/catalogo/textosLineales/`: mensaje del cliente → validar adjuntos → política GRC y
aprobación → respuesta del operador → el operador inicia llamada o videollamada → el cliente acepta o rechaza →
llamada sin grabación y cierre. Cubre las dos (conversaciones formales y pestaña «Chat»). Ver docs/BPM.md §10.

## 9. Pestaña «Chat» del portal (dominio de colaboración)

24-11-2026, migración `210_chat_del_portal_colaboracion` (padre 209). Son las conversaciones a las que el equipo
invita al cliente desde el chat interno (directos, grupos y canales con miembros del portal). El operador las
atiende en el **chat interno** (`/chat`), que ya tenía adjuntos, reacciones, edición, hilos y llamadas; el cliente,
en **Portal → Mensajes → Chat** (`frontend/src/components/portal/ChatColaboracionDelPortal.tsx`), ahora con lo
mismo que las conversaciones formales. Servicio: `app/services/collaboration/portal_chat.py`; rutas en
`app/api/v1/endpoints/collaboration_portal.py` (`/portal/collaboration/*`).

| Función | Operador (chat interno) | Cliente (pestaña Chat) |
|---|---|---|
| Imágenes y ficheros | sí; con clientes en la conversación, **las mismas reglas de la empresa** (tipos, tamaño, contenido por bytes; `files.crear_adjunto`) | sí (`POST …/conversations/{id}/attachments`; descarga solo por la API, participante y misma empresa) |
| Emojis y reacciones | sí | sí (validadas, auditadas y en vivo) |
| Citar / responder | hilos; la cita sale también en la burbuja (`reply_to`) | responde citando; ve las respuestas del equipo en hilo en su lista, con la cita (antes no las veía) |
| Editar y borrar con rastro | sí; el borrado ahora también guarda el texto anterior (`change_type=delete`) | el propio, con plazo `PORTAL_CHAT_EDIT_WINDOW_MINUTES`, versión con `edited_by_client_id` |
| Enlaces seguros | `TextoConEnlaces` en la burbuja | igual |
| Escribiendo / leído | ve «escribiendo» del cliente | ve «escribiendo» del equipo y «Leído» (última lectura del equipo) |
| Tiempo real | bus de colaboración | el WebSocket del portal reenvía los avisos del bus de sus conversaciones (`portal_collab`, sin contenido) |
| Llamar / videollamar | sí, con `clientes.llamar` y si la empresa lo permite (`calls.start_call`) | **nunca**: `POST /portal/collaboration/calls` siempre 403 `portal_llamada_solo_operador` (auditado); acepta, rechaza o cuelga |

**Llamadas.** Iniciar en una conversación con clientes exige `clientes.llamar` (403 `portal_llamada_sin_capacidad`)
y los ajustes `PORTAL_CHAT_CALLS_ENABLED` / `PORTAL_CHAT_VIDEO_ENABLED`. El cliente ve la llamada sonar durante
`PORTAL_CHAT_CALL_RING_SECONDS` desde su inicio; al aceptar recibe su token de LiveKit (identidad `client:<id>`),
al rechazar queda como participante `declined`. **Sin grabación con clientes:** grabar, activar el asistente de
reuniones o transcribir trozos de audio en una llamada de una conversación con clientes da 409
`portal_llamada_no_se_graba`.

**GRC.**
- Auditoría en `collaboration_audit_events`: `attachment.uploaded` / `quarantined` / `downloaded` / `deleted`,
  `message.edited` / `deleted`, `reaction.added` / `removed`, `call.started`, `call.accepted`, `call.declined`,
  `call.left`, `call.start_denied`, con `actor_client_id` cuando es el cliente.
- Retención y bloqueo legal: los del chat de colaboración (Administración del chat, `compliance`): la retención
  borra mensajes, sus versiones y adjuntos con fichero; un bloqueo legal (usuario, **cliente** o canal) impide la
  retención y el borrado del cliente (409 `portal_mensaje_bajo_bloqueo_legal`).
- RGPD: la copia incluye sus mensajes, ediciones, adjuntos, reacciones y participaciones en llamadas
  (`portal_collaboration_chat`); la supresión deja «[ERASED]» y borra versiones, adjuntos con fichero y
  reacciones; bajo bloqueo legal de sus mensajes, 409 antes de tocar nada.

## 10. Chat en vivo de Soporte

24-11-2026, migración `211_chat_en_vivo_completo` (padre `210_chat_del_portal_colaboracion`). Es el tercer chat del
portal: **Portal → Soporte → Chat en vivo** (`PortalChatEnVivo` en
`frontend/src/pages/portal-client/PortalAsistenteYChat.tsx`): empieza con el asistente (artículos de la base de
conocimiento) y pasa a una persona del equipo; el operador lo atiende en **Service Desk → Bandeja de canales**
(`frontend/src/components/servicedesk/BandejaDeCanales.tsx`). Cada mensaje sigue siendo también comentario público
del ticket. Backend: `app/services/service_desk/chat_en_vivo.py` (nuevo), `conversaciones.py`, `canales_en_vivo.py`
y las rutas de `app/api/v1/endpoints/service_desk/canales.py`. Solo para conversaciones `livechat` (WhatsApp, Slack y
Teams siguen con lo suyo: 422 con código).

| Función | Operador (bandeja de canales) | Cliente (Soporte → Chat en vivo) |
|---|---|---|
| Imágenes y ficheros | `POST /sd/channels/conversations/{id}/files`; descarga `GET …/files/{adj}` | `POST /sd/channels/livechat/{id}/attachments`; descarga `GET …/attachments/{adj}` |
| Emojis y reacciones | `POST …/messages/{m}/reactions` | igual en `/livechat/{id}/…` |
| Responder citando | `reply_to_message_id` en `POST …/reply` y en la subida | en `POST /livechat/{id}/messages` y en la subida |
| Editar y borrar lo propio (plazo `PORTAL_CHAT_EDIT_WINDOW_MINUTES`) | `PUT`/`DELETE …/messages/{m}`; historial `GET …/messages/{m}/versions` | `PUT`/`DELETE /livechat/{id}/messages/{m}` |
| Enlaces seguros | `TextoConEnlaces` / texto traducido | `TextoConEnlaces` |
| Escribiendo / Leído | como antes, y «Leído» en cada mensaje propio | igual |
| Tiempo real | `sd_channel`: `message` (con `change` = `edited`/`deleted`), `reaction`, `call` | `livechat`: los mismos eventos |
| Llamar / videollamar | `POST …/calls` con `clientes.llamar` (y `sd.completo`), `…/join`, `…/end` | **nunca**: `POST /livechat/{id}/calls` siempre 403 `portal_llamada_solo_operador` (auditado); `GET /livechat/calls/ringing`, `…/accept`, `…/decline`, `…/end` |
| Grabar / transcribir | `POST …/calls/{c}/recording` → siempre 409 `portal_llamada_no_se_graba` | igual |
| Ajustes | `GET /sd/channels/chat-settings` (`can_call` según capacidad y empresa) | `GET /sd/channels/livechat/settings` (`can_call` siempre `false`) |

Reutiliza, sin duplicar: ajustes `portal_chat`, `adjuntos.validar_fichero` (contenido por bytes, catálogo de la
plataforma sin SVG, tamaño por empresa), `collaboration.files.escanear` (AV/DLP → cuarentena, 409
`portal_adjunto_en_cuarentena`), el almacén `collaboration._storage` (clave `livechat/<empresa>/<conversación>/…`), la
regla de emojis de `interaccion` y la sala y los tokens de LiveKit sin permiso de grabador. Descarga solo por la API,
como `attachment`, con `nosniff` y `private, no-store`.

**«Solo el operador llama».** (1) La única vía de servicio que crea una `ChannelCall` es
`chat_en_vivo.iniciar_llamada`, que recibe un usuario del equipo; su ruta exige `clientes.llamar` y el servicio,
además, `sd.completo`, llamadas (y vídeo) activadas en la empresa, conversación abierta con cliente y ninguna llamada
viva. (2) La ruta del cliente para iniciar existe y siempre responde 403 `portal_llamada_solo_operador` (auditoría
`livechat.call_start_denied`). (3) El cliente solo acepta (único modo de recibir su token; se comprueba que la inició
el equipo), rechaza o cuelga. (4) La pantalla del cliente no tiene botón de llamar y su cliente de API rechaza
`llamar` sin pedirlo.

**Edición y rastro.** El texto anterior de cada edición o borrado queda en `sd_channel_message_versions`; el borrado
es lógico («Mensaje eliminado», sin texto para nadie), quita sus reacciones y sus adjuntos (el fichero se borra al
confirmar; 409 `portal_mensaje_bajo_bloqueo_legal` si alguno está bajo bloqueo). El comentario del ticket que es el
mensaje se actualiza al editar y pasa a «[mensaje eliminado]» al borrar (el rastro queda en las versiones). Un mensaje
del agente editado se envía tal cual, sin volver a traducir.

**Aislamiento de empresa.** Toda consulta filtra por el `organization_id` de la conversación; el cliente, además, por
`client_user_id` y su empresa; el operador, por la empresa de su sesión (404 si no).

**GRC.**
- Auditoría (`audit_logs`, recurso `livechat`, con `organization_id` y `actor_client_id` si es el cliente):
  `LIVECHAT.ATTACHMENT_UPLOADED` / `_QUARANTINED` / `_DOWNLOADED` / `_DELETED`, `MESSAGE_EDITED`, `MESSAGE_DELETED`,
  `REACTION_ADDED` / `_REMOVED`, `CALL_STARTED`, `CALL_ACCEPTED`, `CALL_DECLINED`, `CALL_MISSED`, `CALL_JOINED`,
  `CALL_ENDED`, `CALL_START_DENIED` y `CALL_RECORDING_DENIED`.
- Retención y bloqueo legal (`app/db/bloqueo_legal.py`): `sd_channel_attachments` (desde la subida; bloqueo por id,
  conversación o quien lo subió), `sd_channel_message_versions` (desde el cambio; por id, conversación, mensaje o quien
  editó) y `sd_channel_calls` (terminadas, rechazadas o perdidas, desde el final). Borrar la fila de un adjunto borra
  su fichero al confirmar (`app/db/portal_chat_borrado.py`).
- RGPD (`cab_service/gdpr.py` → `chat_en_vivo.copia_rgpd` / `suprimir_rgpd`, clave `livechat`): copia de sus mensajes
  del chat en vivo, ediciones, adjuntos (metadatos y huella), reacciones y llamadas; la supresión deja «[ERASED]» en
  sus mensajes y en el nombre del visitante y borra versiones, adjuntos (con fichero) y reacciones; bajo bloqueo legal
  de un adjunto suyo, 409 antes de tocar nada. Antes el chat en vivo no entraba en el RGPD.
- Errores: los códigos `portal_*` del §7 (sin códigos nuevos), con texto en los 8 idiomas del portal y en es/en/zh.

**Tablas (211)**, todas con `organization_id` NOT NULL: `sd_channel_message_versions`, `sd_channel_attachments`,
`sd_channel_reactions` (únicos con la empresa delante) y `sd_channel_calls`; en `sd_channel_messages`:
`reply_to_message_id`, `edited_at`, `deleted_at`, `deleted_by_user_id` y `deleted_by_client_id`. Idempotente, SQLite y
Postgres (`batch_alter_table`), deshacer real.

**BPM.** El proceso sembrado `portal_conversation` cubre ahora los tres chats (descripción en la semilla y en es/en/zh).

Tests (escritos, sin ejecutar): `tests/test_chat_en_vivo_completo_2026_11_24.py`; frontend
`src/__tests__/chatEnVivoYChatUnico.test.ts`.

## 11. Un solo chat: las mismas piezas en el interno y en el portal

24-11-2026 (petición del usuario: «todos los chats iguales en comportamiento y diseño que el chat interno»). Las
piezas del chat interno se extrajeron a `frontend/src/components/chat/` (su CSS, `chat.css`, sale tal cual de
`pages/ChatPage.css`) y las usan el chat interno y los tres chats del portal en los dos lados:

| Pieza | Qué es | Dónde se usa |
|---|---|---|
| `PantallaDeChat` | la raíz: lista a la izquierda y panel (`incrustada` dentro de otra página) | formales (equipo y cliente), pestaña «Chat», chat en vivo (cliente y bandeja de canales) |
| `ListaDeChats`, `GrupoDeChats`, `FilaDeConversacion` | la columna de conversaciones: buscador, grupos y filas (avatar o icono + nombre, no leídos) | chat interno (`ListaDeConversaciones`), formales, pestaña «Chat», bandeja de canales |
| `PanelDeChat`, `CabeceraDeConversacion`, `ZonaDeMensajes`, `PanelVacio` | el panel con su barra superior (título, subtítulo, acciones a la derecha) y la zona de mensajes | chat interno (`PanelDeConversacion`) y los tres del portal |
| `FilaDeMensaje` | burbuja (propia a la derecha, ajena a la izquierda con avatar y nombre; §11.1): cita, texto, adjuntos, hora y estado dentro, reacciones debajo; las acciones en una **barra flotante junto a la burbuja** (al pasar el ratón o al enfocar con teclado; si no cabe, encima y hacia dentro; no cambia la altura de la fila) | chat interno (`MessageBubble`), formales, pestaña «Chat», chat en vivo (`MensajeDelChatEnVivo`) |
| `EditorDeChat`, `AvisoDelEditor` | un único cuadro: el texto; arriba a la derecha la @ (solo donde hay menciones) y el emoji; abajo, el clip a la izquierda y enviar a la derecha | todos (el interno gana el emoji) |
| `BotonesDeLlamada`, `BotonDeChat` | llamar y videollamar en la cabecera, como en el interno | interno; en el portal solo el operador con `clientes.llamar` |
| `EtiquetaDeAutor`, `EstadoDeEntrega`, `Escribiendo`, `IndicadorDeCabecera` | etiqueta junto al nombre (estilo de la de bot: «Cliente», «Interna»), Enviado/Leído, «escribiendo…», indicador discreto de la cabecera | los tres del portal |

Lo que cambia por contexto son las props: las acciones de la barra (el cliente no fija, guarda ni enlaza a tareas;
notas internas, aprobar e historial, solo el operador), los textos (cada lado con su diccionario) y lo que va bajo el
texto (adjuntos por la API, botones de revisión). **«Con supervisión» nunca se enseña al cliente**; al operador, una
sola vez, como indicador en la cabecera con su explicación según la política del tema
(`governedconversations.supervision_*`). El estado GRC y «ocultado» de cada mensaje solo los ve el equipo.

Se quitaron `ConversationListItem` y el CSS propio sin uso (`chat-portal-burbuja`, `-acciones`, `-reaccion*`, `-cita`,
`-contexto`, `-herramientas`, `-escribiendo`, `-estado`, `-texto`, `-adjunto…` de `ChatDelPortal.css` y 41 clases
`goveconv-*`/`governed-*` de `GovernedConversations.css`); los adjuntos del portal usan las clases del interno
(`chat-att*`). Vigilante: `frontend/scripts/kit_pendientes.mjs` (`comprobarChatUnico`) y el test
`chatEnVivoYChatUnico.test.ts` fallan si un chat del portal deja de importar `components/chat` o vuelve a pintar su
propia lista, burbuja o editor. Regla de diseño: `docs/GUIA_DE_DISENO.md` §17.

### 11.1 Cómo se ve: burbujas como en WhatsApp o Teams

24-11-2026 (pedido del usuario). En los tres chats del portal, en los dos lados, **lo que escribes tú aparece a la
derecha** (burbuja con el color del tema, sin foto) y **lo que escribe el otro, a la izquierda** (burbuja gris con
su inicial y su nombre):

- **El cliente** ve sus mensajes a la derecha y los del equipo (y los del asistente) a la izquierda.
- **El operador** ve los suyos a la derecha; el cliente, el asistente y los compañeros del equipo, a la izquierda
  (con su nombre, como en Teams).
- Dentro de cada burbuja, abajo a la derecha: la hora, «editado» si se cambió y, en los propios, ✓ (enviado) o ✓✓
  (leído). Las etiquetas «Cliente», «Interna» o el estado GRC (solo el equipo) van ahí mismo, en pequeño.
- Mensajes seguidos de la misma persona van juntos, sin repetir la foto ni el nombre. Entre días, un separador
  («Hoy», «Ayer» o la fecha). Los avisos del sistema («El cliente pide hablar con una persona») salen centrados en
  una pastilla.
- Las reacciones van en pastillas bajo la burbuja; al pasar el ratón (o con el teclado) aparece la barra de
  acciones al lado de la burbuja (a la izquierda de las tuyas, a la derecha de las de los demás).
- El asistente de Soporte y el asistente de IA del portal se ven igual: tu pregunta a la derecha y la respuesta
  del asistente a la izquierda, con el mismo cuadro de escribir.

Regla de diseño: `docs/GUIA_DE_DISENO.md` §17.1.

## 12. Pendiente

- Las llamadas con clientes no se graban (decisión); si se quisiera, consentimiento previo del cliente y retención
  como `meetings`.

Tests (escritos, sin ejecutar): `tests/test_chat_del_portal_2026_11_24.py` y
`tests/test_chat_del_portal_colaboracion_2026_11_24.py`; frontend `src/__tests__/chatDelPortal.test.ts`.
