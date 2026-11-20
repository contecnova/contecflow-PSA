"""Toda ruta que escribe lleva guarda de rol, o una exención con motivo escrito.

Auditoría 2026-09. Al cerrar las 24 rutas `DELETE` de §3.trigies salió que el
problema era mucho más ancho: el detector de ABAC sólo miraba rutas que llaman
a `enforce_abac`, y eso es casi todo `DELETE`. Contando **todas** las rutas de
escritura —`POST`, `PUT`, `PATCH`, `DELETE`— aparecieron **563 sin ningún
control de rol**, frente a 603 que sí lo tenían: casi la mitad de la capa de
escritura de la API no comprobaba quién eras más allá de estar autenticado.

`TenantSession` seguía impidiendo el acceso entre organizaciones. Lo que
faltaba era quién, **dentro** de la misma empresa, puede hacer cada cosa.

## Por qué esto es un test y no una nota en un documento

Porque el número vuelve solo. Cada endpoint nuevo nace sin guarda si nadie la
exige, y un `POST` sin control funciona perfectamente: no falla, no avisa, y
sólo se nota el día que alguien hace algo que no debía.

## Qué cuenta como exención

Ponerle guarda a las 563 habría sido la chapuza que este test existe para
evitar. Hay cuatro motivos por los que una ruta puede no llevarla, y los cuatro
se comprueban, no se suponen:

- **Otra superficie de autenticación.** El portal de cliente
  (`get_current_client`), las API key y los webhooks de proveedor no tienen
  usuario interno: un cliente no tiene rol de empleado y Twilio no tiene rol.
  Exigirles `require_internal_user` sería romperlos, no protegerlos.
- **Sin sujeto autenticado**: login, recuperación de contraseña, callbacks de
  SSO, formularios públicos. Por definición se llaman antes de tener usuario.
- **Acotada al propio usuario**, detectado con `_acota_por_propiedad`, el mismo
  comprobador ya validado de `test_abac_coverage`.
- **Revisada a mano** (`EXENTAS_REVISADAS`): el control existe pero vive dentro
  del endpoint, donde ningún detector lo ve. Cada una lleva su motivo.

## Las 32 pruebas que corrigieron la primera pasada

La primera aplicación puso 372 guardas y dejó **32 tests en rojo**. Todos
señalaban lo mismo: rutas de autoservicio restringidas de más. Y lo decían con
sus propios nombres —`test_un_empleado_puede_editar_sus_propios_datos_de_perfil`,
`test_user_can_create_own_plan`—, que es la intención escrita del producto.
Ahí el test tiene razón y la guarda no. De ahí salió `EXENTAS_REVISADAS`.
"""
from __future__ import annotations

import inspect
import re

from tests.test_abac_coverage import _acota_por_propiedad, _api_routes, _source

ESCRITURA = {"POST", "PUT", "PATCH", "DELETE"}

# `require_worker` (externos como internos, 16-11-2026) es guarda de rol: deja
# fuera a quien no tiene rol de trabajo. `test_guardas_deniegan` no la sondea
# porque ningún rol de usuario queda fuera de ella.
# `requiere_capacidad("x")` (19-11-2026) es guarda de rol leída de la matriz de
# permisos (`app/core/capacidades.py`): cuenta igual que las `require_*`.
GUARDA = re.compile(
    r"require_(admin_or_pm|admin_or_hr|any_manager|internal_user|worker|superadmin|admin)\b"
    r"|\brequiere_capacidad\(\s*[\"'][\w.]+[\"']\s*\)")
PORTAL = re.compile(r"get_current_client|get_current_portal_user|portal_user")
APIKEY = re.compile(r"require_api_key|require_scim_token|verify_api_key|x_api_key")
USUARIO = re.compile(r"get_current_user|get_current_active_user")


#: Rutas sin guarda de rol, decididas a mano, con el motivo de cada una.
#:
#: No son un hueco: son sitios donde el control existe y vive **dentro** del
#: endpoint —«¿eres tú el aprobador designado?», «¿es tu propio perfil?»—, que
#: es justo lo que un barrido no puede ver.
EXENTAS_REVISADAS = {
    # (2026-11: `POST /auth/mfa/setup` y `verify-setup` salen de aqui: ahora tocan
    # los codigos de respaldo de `current_user.id` y el detector las ve acotadas.)
    "PUT /api/v1/approvals/out-of-office": "fijar la propia ausencia y su delegado (solo toca al usuario de la sesion; el delegado ha de ser de su empresa y activo)",
    # Perfil propio. `PATCH /users/{user_id}` se queda fuera a propósito: el
    # endpoint YA distingue perfil propio de ficha ajena y rechaza los campos
    # reservados, y eso lo prueban los cuatro tests de
    # `test_user_update_authorization`. Una guarda de rol encima romperia que
    # un empleado edite sus propios datos.
    "PATCH /api/v1/users/me": "editar el perfil propio",
    "PUT /api/v1/users/me/notification-preferences": "elegir los propios avisos (solo toca las preferencias del usuario de la sesion)",
    "PATCH /api/v1/users/{user_id}": (
        "el endpoint ya distingue perfil propio de ficha ajena; lo prueban los "
        "cuatro tests de test_user_update_authorization"),
    # Cosas de uno mismo en la interfaz.
    "POST /api/v1/dashboard/widgets": "los widgets del propio panel",
    "PATCH /api/v1/dashboard/widgets/reorder": "reordenar los widgets propios",
    "POST /api/v1/epics/mentions/read-all": "marcar por leídas las menciones propias",
    # Aprobaciones: presenta cualquiera, decide el designado. El endpoint
    # comprueba que lo eres; una guarda de rol dejaría fuera al aprobador que
    # no sea admin, que es el caso normal.
    "POST /api/v1/approvals/requests": "cualquiera presenta algo a aprobación",
    "POST /api/v1/approvals/requests/{request_id}/decide": (
        "decide el aprobador designado, y el endpoint comprueba que lo eres"),
    "POST /api/v1/approvals/requests/{request_id}/cancel": (
        "cancela quien la presentó, y el endpoint lo comprueba"),
    # Ausencias (tarea #25, rev. 167): la ausencia se crea SIEMPRE para el usuario
    # de la sesión (`solicitudes.construir` pone `user_id=usuario.id`; no hay
    # campo para pedirla por otro). Antes el endpoint comparaba `current_user.id`
    # en su cuerpo y el detector lo veía; ahora lo hace el servicio.
    "POST /api/v1/absences/my": "pedir la ausencia propia (el servicio la crea para current_user)",
    # Evaluación y desarrollo propios.
    "PATCH /api/v1/performance/reviews/{review_id}": "rellenar la evaluación propia",
    "POST /api/v1/performance/reviews/{review_id}/submit": "enviar la evaluación propia",
    "POST /api/v1/performance/dev-plans": "el plan de desarrollo propio",
    "PATCH /api/v1/performance/dev-plans/{plan_id}": "el plan de desarrollo propio",
    "POST /api/v1/performance/dev-plans/{plan_id}/goals": "los objetivos del plan propio",
    "PATCH /api/v1/performance/dev-goals/{goal_id}": "los objetivos del plan propio",
    "DELETE /api/v1/performance/dev-goals/{goal_id}": "los objetivos del plan propio",
    # Licencias y hardware (16-11-2026, 1b80248f). «Mis equipos y licencias» es
    # de toda persona con sesión (también subcontratas): una guarda de rol la
    # dejaría sin su propio equipo. El control es de PROPIEDAD y vive en el
    # servicio, con columnas que el detector no conoce (`holder_user_id`,
    # `signer_user_id`).
    "POST /api/v1/alm/acts/{act_id}/sign": (
        "firma solo la persona del acta: alm_actas.firmar compara signer_user_id con el usuario (403)"),
    "POST /api/v1/alm/integracion/mio/actas/{acta_id}/firmar": (
        "firma solo la persona del acta (alm_actas.firmar, signer_user_id; 403)"),
    "POST /api/v1/alm/integracion/mio/asignaciones/{aid}/averia": (
        "solo sobre una asignación propia activa: autoservicio._mia exige holder_user_id == user.id (404)"),
    "POST /api/v1/alm/integracion/mio/asignaciones/{aid}/dejar": (
        "solo sobre una asignación propia activa: autoservicio._mia exige holder_user_id == user.id (404)"),
    "POST /api/v1/alm/integracion/mio/asignaciones/{aid}/devolver": (
        "solo sobre una asignación propia activa: autoservicio._mia exige holder_user_id == user.id (404)"),
    "POST /api/v1/alm/integracion/mio/peticiones": (
        "cualquiera pide para sí; pedir para otro exige ser su responsable, admin o RRHH "
        "(catalogo.pedir, 403), y el proyecto ha de ser visible"),
    "POST /api/v1/alm/integracion/proyectos/{project_id}/asignar": (
        "decide el PM del proyecto o admin (proyecto.puede_gestionar, 403), sobre un proyecto visible"),
    "POST /api/v1/alm/integracion/proyectos/{project_id}/asignaciones/{aid}/liberar": (
        "decide el PM del proyecto o admin (proyecto.puede_gestionar, 403), sobre un proyecto visible"),
    "POST /api/v1/alm/uso/recuperaciones/{rec_id}/conservar": (
        "«la sigo necesitando»: la persona titular (r.user_id) o un gestor; si no, 404 (recuperacion.conservar)"),
    # Traducción en tiempo real (16-11-2026, e2a94c61): traducir un texto suelto
    # del editor o del chat interno. No escribe datos de negocio, solo la cache
    # de la empresa de quien pide; el gasto lo frena el tope diario de IA.
    "POST /api/v1/translation/text": (
        "traducir un texto propio: solo escribe la cache de traducción de la empresa del usuario; tope de gasto de IA"),
}

#: Exenciones detectadas automáticamente, por motivo y en su número medido.
#:
#: Trinquete de dos direcciones, como los demás de este repositorio: si sube,
#: alguien ha dejado de poner una guarda; si baja, una exención dejó de hacer
#: falta y la foto se quedó vieja. Las dos cosas hay que mirarlas.
EXENCIONES_ESPERADAS = {
    # 92 desde 2026-11-03: POST y DELETE /reports/templates pasan a admin o PM,
    # como su pantalla (el generador de informes).
    # 93 desde 2026-11-04: PATCH /auth/mfa/webauthn/credentials/{id} (renombrar
    # una passkey propia).
    # 93 desde 2026-11-09: fuera PATCH/DELETE /sd/tickets/{id}/internal-comments (las
    # notas internas viven en los comentarios del ticket) y POST /capacity/plans
    # pasa a exigir gestor.
    # 94 desde 2026-11-16: +1 POST /translation/messages (e2a94c61), mensajes
    # guardados en el idioma de quien mira, acotados a `current_user.id`.
    # 93 desde 2026-11-20: POST /ai/chat sale de aquí (la conversación ya se acotaba a
    # `current_user.id` en `prepare_chat`) y gana `require_internal_user` en la firma.
    "acotada al propio usuario": 93,  # +1 medido, tarea #25 (rev. 167): rutas nuevas de /absences que `_acota_por_propiedad` ve acotadas al usuario (vista previa y adjuntar documento; POST /absences/my va en EXENTAS_REVISADAS); 2026-11 un solo TOTP: -4 rutas /mfa/* (setup, verify, validate, disable) retiradas, +2 /auth/mfa/setup y verify-setup (antes en EXENTAS_REVISADAS);  # +1 2026-11: cambio de empresa en la sesión; +2: reservar y liberar un documento (decide el permiso del documento, como el resto de /documents); +1 auditoria 2026-11 #22: change-password (antes en EXENTAS_REVISADAS) revoca las sesiones de `current_user.id` y el detector ya la ve acotada
    "superficie: API key": 6,  # 2026-11: fuera POST /bookings/api-keys/verify (oraculo)
    # 20 desde 2026-11-09: fuera la copia de /clients/{cid}/portal-users (POST y
    # PATCH) que no exigía el máximo de usuarios del portal.
    # 21 desde 2026-11-16: +1 POST /portal/collaboration/notifications/{id}/read
    # (campana del portal), acotada al cliente que llama (404 si es de otro).
    "superficie: portal de cliente": 21,  # +1: valorar una respuesta del chat del portal (2026-11)
    # 38 desde 2026-11-02: POST /sd/events/{source} autentica el token de la
    # organizacion y POST /sd/kb/{id}/deflected exige `lector_de_la_kb`
    # (cliente del portal o usuario); el clasificador no reconoce ninguno.
    # 42 desde 2026-11-09: POST /git/webhooks/{github|gitlab}/{slug}, firmados con
    # el secreto de cada empresa.
    # 52 desde 2026-11-16 (+8, medido con git blame de cada ruta, todas de 1b80248f):
    # chat en vivo del portal (POST /sd/channels/livechat, .../{id}/messages y
    # .../{id}/agent) y asistente del portal (POST /sd/portal-assistant/intent,
    # .../actions/{id}/confirm y .../cancel), con la sesion del cliente del portal
    # (`get_current_portal_client`, que el clasificador no reconoce, como las
    # demas de /sd/tickets/client); y los webhooks firmados de Slack (POST
    # /sd/channels/slack/interactions) y WhatsApp (POST /sd/channels/whatsapp/webhook).
    # 53 desde 2026-11-17 (+1, medido con _clasificar): POST /sd/channels/slack/events
    # (Events API de Slack, rev. 179). Sin sesion: `canal_slack.leer_evento` exige la
    # firma `X-Slack-Signature` (HMAC-SHA256 con el signing secret de la empresa del
    # `team_id`, marca de tiempo de 5 min como mucho) y responde 403 si no cuadra o si
    # el workspace no es de una sola empresa; `url_verification` vale con cualquier
    # signing secret conocido. El evento se procesa en la empresa del workspace.
    # 56 desde 2026-11-20 (+3, medido con _clasificar): avisos del asistente de reuniones,
    # POST /webhooks/meetings/{recall|teams|zoom}/{org_id}. Sin sesión: `reuniones/webhooks.py`
    # exige la firma de cada proveedor (Svix de Recall, clientState de Graph, HMAC de Zoom)
    # con el secreto de la empresa del {org_id} y responde 403 si falta o no cuadra
    # (test_asistente_de_reuniones::test_webhooks_sin_secreto_o_con_firma_mala_dan_403).
    "superficie: sin sujeto autenticado": 56,  # +1 elegir empresa tras la contraseña; +1 decidir desde el correo; +1 webhook de Stripe (firma); +1 POST /client-errors (solo log)
}

#: Rutas de escritura que sí llevan guarda de rol. Sólo puede subir.
CON_GUARDA_MINIMO = 929


def _desenvolver(fn):
    """El endpoint real: `slowapi` y compañía lo envuelven en un decorador."""
    visto = set()
    while hasattr(fn, "__wrapped__") and id(fn) not in visto:
        visto.add(id(fn))
        fn = fn.__wrapped__
    return fn


def _clasificar():
    con_guarda = 0
    exentas: dict[str, list[str]] = {}
    revisadas: list[str] = []
    sin_control: list[str] = []
    vistas: set[tuple] = set()

    for _route, path, methods, _dep, endpoint in _api_routes():
        escritoras = methods & ESCRITURA
        if not escritoras:
            continue
        real = _desenvolver(endpoint)

        # `main.py` monta los routers en v1 y en v2, así que cada endpoint sale
        # dos veces con dos paths. Se cuenta la FUNCIÓN, que es lo que se guarda.
        try:
            clave = (inspect.getsourcefile(real) or "?", inspect.getsourcelines(real)[1])
        except OSError:
            clave = (real.__module__, id(real))
        if clave in vistas:
            continue
        vistas.add(clave)

        fuente = _source(endpoint) + _source(real)
        etiqueta = f"{','.join(sorted(escritoras))} {path}"

        if GUARDA.search(fuente):
            con_guarda += 1
        elif PORTAL.search(fuente):
            exentas.setdefault("superficie: portal de cliente", []).append(etiqueta)
        elif APIKEY.search(fuente):
            exentas.setdefault("superficie: API key", []).append(etiqueta)
        elif not USUARIO.search(fuente):
            exentas.setdefault("superficie: sin sujeto autenticado", []).append(etiqueta)
        elif _acota_por_propiedad(real) or _acota_por_propiedad(endpoint):
            exentas.setdefault("acotada al propio usuario", []).append(etiqueta)
        elif etiqueta in EXENTAS_REVISADAS:
            revisadas.append(etiqueta)
        else:
            sin_control.append(etiqueta)

    return con_guarda, exentas, revisadas, sin_control


def test_ninguna_ruta_de_escritura_se_queda_sin_control():
    """Ni una sola ruta que escribe sin guarda de rol y sin motivo escrito."""
    _con, _ex, _rev, sin_control = _clasificar()
    assert not sin_control, (
        f"{len(sin_control)} rutas que escriben sin guarda de rol y sin motivo de "
        "exención. Pon la guarda que corresponda en la firma del endpoint o, si de "
        "verdad no la necesita, deja escrito por qué en EXENTAS_REVISADAS — con el "
        "motivo, no sólo la ruta.\n  - " + "\n  - ".join(sorted(sin_control))
    )


def test_las_exenciones_revisadas_siguen_existiendo():
    """Una exención escrita para una ruta que ya no existe es ruido.

    Falla también cuando una ruta de `EXENTAS_REVISADAS` ha ganado guarda por
    otro camino: entonces la entrada sobra y hay que quitarla, porque si no la
    lista deja de describir el código y pasa a describir el pasado.
    """
    _con, _ex, revisadas, _sin = _clasificar()
    huerfanas = sorted(set(EXENTAS_REVISADAS) - set(revisadas))
    assert not huerfanas, (
        "Estas entradas de EXENTAS_REVISADAS ya no corresponden a una ruta sin "
        "guarda: o la ruta desapareció, o alguien le puso una guarda y la entrada "
        "sobra. Quítalas.\n  - " + "\n  - ".join(huerfanas)
    )


def test_el_reparto_de_exenciones_no_cambia_en_silencio():
    """El trinquete de las exenciones automáticas, en su número medido."""
    _con, exentas, _rev, _sin = _clasificar()
    medido = {motivo: len(rutas) for motivo, rutas in exentas.items()}

    desvios = [
        f"{motivo}: esperado {EXENCIONES_ESPERADAS.get(motivo, 0)}, medido {medido.get(motivo, 0)}"
        for motivo in sorted(set(medido) | set(EXENCIONES_ESPERADAS))
        if EXENCIONES_ESPERADAS.get(motivo, 0) != medido.get(motivo, 0)
    ]
    assert not desvios, (
        "El reparto de exenciones ha cambiado. Si es una mejora, actualiza "
        "EXENCIONES_ESPERADAS; si no, mira qué ruta ha perdido su guarda:\n  - "
        + "\n  - ".join(desvios)
    )


def test_las_guardas_de_rol_no_retroceden():
    """De 603 rutas guardadas a 929. Sólo puede subir."""
    con_guarda, _ex, _rev, _sin = _clasificar()
    assert con_guarda >= CON_GUARDA_MINIMO, (
        f"Había {CON_GUARDA_MINIMO} rutas de escritura con guarda de rol y ahora "
        f"hay {con_guarda}. Alguien ha quitado una."
    )
