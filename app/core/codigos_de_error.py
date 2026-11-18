"""Errores con codigo estable para lo que ve el cliente del portal (16-11-2026).

El portal de clientes ofrece 8 idiomas; el servidor escribia sus errores en
castellano (`detail`). Ahora los que puede ver un cliente salen con un codigo
estable y sus datos: `{"detail": <castellano, como antes>, "code": <codigo>,
"params": {...}}` (lo anade el manejador de `app/main.py`). El portal los pinta
con su clave `err_srv.<codigo>` en el idioma del cliente
(`frontend/src/utils/mensajeDeError.ts`); el operador, y cualquier cliente
antiguo de la API, siguen leyendo `detail`.

Es el mismo patron que `bpm` (`error_code` + `error_params` junto al texto) y
que los `alm_*`/`trad_*` (codigo estable que traduce la interfaz), sin cambiar
`detail` para no romper a quien ya lo lee.

Dos formas de lanzarlo:

- `error(404, "ticket_no_encontrado")`: un `ErrorDeDominio` con codigo.
- `ErrorConCodigo("encuesta_no_encontrada")`: para los servicios que lanzan
  `ValueError` y cuyo endpoint decide el estado HTTP (`except ValueError`); el
  endpoint lo convierte con `desde_valor(404, e)`, que conserva el codigo.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.errores import ErrorDeDominio

#: Codigo -> texto en castellano (el `detail` de siempre). Cada codigo tiene su
#: clave `err_srv.<codigo>` en los 8 diccionarios del portal.
MENSAJES: dict[str, str] = {
    # Sesion y perfil
    "sesion_invalida": "Token de cliente inválido o expirado",
    "credenciales_incorrectas": "Email o contraseña incorrectos",
    "cliente_no_encontrado": "Cliente no encontrado",
    "perfil_no_editable": "Edición de perfil deshabilitada para este portal",
    "cambio_contrasena_desactivado": "El cambio de contraseña está desactivado",
    "contrasena_actual_incorrecta": "La contraseña actual no es correcta",
    "contrasena_corta": "La contraseña debe tener al menos {n} caracteres",
    # Proyectos, documentos y facturas
    "sin_acceso_proyecto": "No tienes acceso a ese proyecto",
    "sin_proyectos": "No hay proyectos asignados a este cliente",
    "proyecto_no_encontrado": "Proyecto no encontrado",
    "proyecto_obligatorio": "Debes indicar un proyecto accesible",
    "documento_no_encontrado": "Documento no encontrado",
    "documento_ya_firmado": "El documento ya fue firmado",
    "ruta_pdf_invalida": "Ruta de PDF inválida",
    "pdf_firma_no_disponible": "PDF de firma no disponible",
    "archivo_firma_no_encontrado": "Archivo de firma no encontrado en el servidor",
    "factura_no_encontrada": "Factura no encontrada",
    "enlace_invalido": "Token inválido o expirado",
    # Solicitudes de cambio
    "sin_permiso_cambios": "No tienes permisos para solicitar cambios",
    "sin_proyecto_para_solicitudes": "No tienes un proyecto asignado para enviar solicitudes",
    "solicitud_no_encontrada": "FR no encontrada",
    "solicitud_no_editable": "Solo puedes editar solicitudes nuevas o en revisión",
    "solicitud_no_retirable": "Solo puedes retirar solicitudes nuevas o en revisión",
    "solicitud_sin_estimacion": "Solo se pueden aprobar FRs con estimación del equipo",
    # UAT
    "uat_no_encontrada": "UAT no encontrada",
    "sin_acceso_uat": "No tienes acceso a esta sesión UAT",
    "incidencia_no_encontrada": "Incidencia no encontrada",
    # Wiki, encuestas y asistente
    "pagina_no_encontrada": "Página no encontrada o no visible",
    "encuesta_no_encontrada": "Encuesta no encontrada",
    "encuesta_ya_respondida": "Esta encuesta ya ha sido respondida",
    "respuesta_no_encontrada": "Respuesta no encontrada",
    # Conversaciones del portal y chat en vivo
    "titulo_obligatorio": "El título es obligatorio",
    "conversacion_no_encontrada": "Conversación no encontrada",
    "conversacion_cerrada": "La conversación está cerrada",
    "mensaje_no_encontrado": "Mensaje no encontrado",
    "mensaje_vacio": "El mensaje está vacío",
    "nota_interna_no_permitida": "El cliente no puede enviar notas internas",
    "canal_desconocido": "Canal desconocido",
    # Tickets del portal
    "ticket_no_encontrado": "Ticket no encontrado",
    "solo_tickets_resueltos": "Solo tickets resueltos",
    "ticket_proyecto_ajeno": "No puedes crear tickets para proyectos a los que no perteneces",
    # Asistente del portal
    "accion_no_encontrada": "Acción no encontrada",
    "accion_ya_decidida": "La acción ya está decidida",
    "propuesta_caducada": "La propuesta ha caducado",
    "accion_desconocida": "Acción desconocida",
    "servicio_no_disponible": "El servicio ya no está disponible",
    "herramienta_sin_politica": "La herramienta '{herramienta}' no tiene política de acceso: no se ejecuta.",
    "acceso_denegado": "Acceso denegado",
    # Chat de IA del portal (y modulos de IA gobernados)
    "mensaje_obligatorio": "message required",
    "modulo_ia_no_activado": "El módulo de IA «{modulo}» no está activado en Gobierno de IA",
    "modulo_ia_desactivado": "El módulo de IA «{modulo}» está desactivado en Gobierno de IA",
    "modulo_ia_limite_diario": "Has llegado al límite diario de {n} acciones de «{modulo}»",
    # Mensajes del portal (`/portal/collaboration/*`)
    "sin_acceso_conversacion": "No tienes acceso a esta conversación",
    "sin_acceso": "No tienes acceso",
    "conversacion_obligatoria": "conversation_id requerido",
    "demasiados_mensajes": "Portal message rate limit exceeded. Retry in {segundos}s",
    # Campana del portal (16-11-2026)
    "notificacion_no_encontrada": "Notificación no encontrada",
    # Validacion de la peticion (17-11-2026, `app/core/validacion.py`): el
    # detalle por campo va en `params.errores`; la interfaz pinta cada error
    # junto a su campo (`validacion.<tipo>`).
    "validacion": "Revisa los datos",
}

#: Codigos que solo ve el operador (back office): se traducen en la interfaz de
#: operador con `err_srv.<codigo>` en `frontend/src/i18n/langs/{es,en,zh}.mjs`
#: (`extractErr` los resuelve), no en los 8 idiomas del portal. Mismo `detail`
#: en castellano de siempre. 17-11-2026: canales, turnos/ausencias por horas y
#: avisos (bloques 179-181).
MENSAJES_DEL_OPERADOR: dict[str, str] = {
    # Canales del service desk (bandeja y ficha del ticket)
    "whatsapp_fuera_de_ventana": "Han pasado más de 24 h desde el último mensaje del cliente y no hay "
                                 "plantilla de WhatsApp configurada: el mensaje no se puede enviar.",
    "whatsapp_adjunto_fuera_de_ventana": "Fuera de la ventana de 24 h de WhatsApp: los adjuntos solo salen "
                                         "después de un mensaje del cliente.",
    "slack_sin_token": "Slack sin token de bot en la empresa: no se puede contestar en el hilo.",
    "canal_sin_adjuntos": "Este canal no admite enviar adjuntos desde aquí.",
    "conversacion_sin_ticket": "La conversación no tiene ticket",
    "adjunto_no_encontrado": "Adjunto no encontrado",
    # Resumen IA de documentos
    "documento_sin_versiones": "El documento no tiene versiones que resumir",
    "documento_sin_archivo": "La última versión no tiene archivo",
    "documento_sin_texto": "No se pudo extraer texto del documento. Sube una versión con capa de texto "
                           "o habilita OCR (tesseract + pytesseract + pypdfium2).",
    # Turnos, jornadas y ausencias por horas
    "solo_persona_rrhh_o_admin": "Solo la persona, RRHH o administración",
    "rango_de_1_a_400_dias": "Un rango de 1 a 400 días",
    "saldo_no_existe": "Ese saldo no existe",
    "persona_no_existe_en_empresa": "Esa persona no existe en tu empresa",
    "cantidad_no_numerica": "La cantidad tiene que ser un número",
    "cantidad_cero": "La cantidad no puede ser 0",
    "caduca_antes_de_empezar": "Caduca antes de empezar a contar",
    "ajuste_sin_motivo": "Explica el motivo del ajuste",
    "unidad_de_saldo_no_valida": "La unidad es «dias» u «horas»",
    "ajuste_no_encontrado": "Ajuste no encontrado",
    "ajuste_de_bolsa_no_borrable": "Las horas de la bolsa salen de las imputaciones: corrige la imputación",
    "fecha_no_valida_en": "Fecha no válida en «{nombre}»",
    "hora_no_valida_en": "Hora no válida en «{nombre}» (HH:MM)",
    "indica_hora_inicio_y_fin": "Indica la hora de inicio y la de fin",
    "franja_misma_hora": "La franja empieza y acaba a la misma hora",
    "modo_de_peticion_no_valido": "El modo de la petición es «dias» u «horas»",
    "tipo_no_se_pide_por_horas": "«{tipo}» no se puede pedir por horas",
    "tipo_se_pide_por_horas": "«{tipo}» se pide por horas",
    "tipo_no_se_pide_por_medio_dia": "«{tipo}» no se puede pedir por medio día",
    "por_horas_indica_franja": "Por horas: indica la franja (hora de inicio y de fin)",
    "tipo_necesita_sustituto": "«{tipo}» necesita un sustituto",
    "franja_fuera_de_horario": "Esa franja no cae dentro de tu horario (turno o jornada) en esas fechas",
    "sin_dia_de_trabajo": "En esas fechas no tienes ningún día de trabajo (cuadrante o calendario laboral)",
    "saldo_insuficiente": "Pides {cantidad} y te quedan {disponible}",
    "saldo_insuficiente_con_limite": "Pides {cantidad} y te quedan {disponible} (se permite hasta −{permitido})",
    "saldo_agotado": "Pides {cantidad} y no te queda saldo",
    "saldo_agotado_con_limite": "Pides {cantidad} y no te queda saldo (se permite hasta −{permitido})",
    "tramos_de_turno_no_validos": "Tramos del turno no válidos: {detalle}",
    "turno_mas_de_un_dia": "Un turno no puede durar más de un día",
    "turno_misma_hora": "El turno empieza y acaba a la misma hora",
    "pausa_mayor_que_turno": "La pausa tiene que ser menor que la duración del turno",
    "jornada_no_encontrada": "Jornada no encontrada",
    "jornada_sin_nombre": "La jornada necesita un nombre",
    "asignacion_no_encontrada": "Asignación no encontrada",
    "ambito_desconocido": "Ámbito desconocido: {ambito}",
    "asignacion_sin_destino": "Indica a quién se aplica",
    "destino_no_existe_en_empresa": "Ese destino no existe en tu empresa",
    "jornada_anual_sin_fechas": "Una jornada que se repite cada año necesita fecha de inicio y de fin",
    "fecha_final_anterior": "La fecha final es anterior a la inicial",
    "persona_no_encontrada": "Persona no encontrada",
    "sede_no_existe": "Esa sede no existe",
    "maximo_de_dias": "Como mucho {max} días de una vez",
    # Horas extra (18-11-2026, `app/services/horas_extra/`)
    "horas_extra_desactivadas": "Las horas extra no están activadas en tu empresa",
    "horas_extra_no_encontrada": "Petición de horas extra no encontrada",
    "horas_extra_tipo_no_valido": "Tipo de horas extra no válido: {tipo}",
    "horas_extra_compensacion_no_permitida": "La compensación «{compensacion}» no está permitida",
    "horas_extra_horas_no_validas": "Las horas tienen que ser más de 0 y como mucho 24",
    "horas_extra_sin_franja_ni_horas": "Indica las horas o la franja",
    "horas_extra_horas_mayor_que_franja": "Pides {horas} h y la franja dura {franja} h",
    "horas_extra_franja_dentro_de_horario": "La franja cae dentro de tu horario ({horas} h): no son horas extra",
    "horas_extra_tipo_no_coincide": "«{tipo}» no coincide con el día {fecha} ({clase})",
    "horas_extra_solapada": "Ya tienes horas extra pedidas que se solapan el {fecha}",
    "horas_extra_motivo_obligatorio": "Explica el motivo",
    "horas_extra_requisitos": "Falta: {requisitos}",
    "horas_extra_bloqueada": "{mensaje}",
    "horas_extra_no_pendiente": "Solo se puede hacer con peticiones pendientes",
    "horas_extra_no_cancelable": "Solo se cancelan peticiones pendientes, o aprobadas de un día que aún no ha llegado",
    "horas_extra_no_puedes_pedir_para_otro": "No puedes pedir horas extra para esa persona",
    "horas_extra_sin_autorizar": "El {fecha} imputas {sin_autorizar} h fuera de tu horario sin autorización aprobada",
    "horas_extra_no_liquidable": "Solo se liquidan horas extra aprobadas que se pagan",
    "horas_extra_ya_liquidada": "Ya está liquidada",
    "horas_extra_autorizadas_no_validas": "Las horas autorizadas van de 0 a las pedidas ({horas})",
    "horas_extra_presupuesto_no_valido": "Presupuesto no válido: {detalle}",
    "horas_extra_presupuesto_no_encontrado": "Presupuesto no encontrado",
    "horas_extra_config_no_valida": "Configuración no válida: {detalle}",
    "horas_extra_referencia_obligatoria": "Indica la referencia de la nómina o del pago",
    # Avisos del service desk
    "aviso_no_encontrado": "Aviso no encontrado",
    "campo_obligatorio": "{campo} es obligatorio",
}

#: Todos los codigos (portal y operador): para `texto` y las comprobaciones.
TODOS: dict[str, str] = {**MENSAJES, **MENSAJES_DEL_OPERADOR}


def texto(codigo: str, params: Optional[dict] = None) -> str:
    """El texto en castellano del codigo con sus datos (o el codigo si no existe)."""
    plantilla = TODOS.get(codigo, codigo)
    try:
        return plantilla.format(**(params or {}))
    except (KeyError, IndexError, ValueError):
        return plantilla


def error(status_code: int, codigo: str, headers: Optional[dict] = None, **params: Any) -> ErrorDeDominio:
    """`ErrorDeDominio` con codigo estable: `raise error(404, "ticket_no_encontrado")`."""
    return ErrorDeDominio(status_code, texto(codigo, params), headers, code=codigo, params=params or {})


class ErrorConCodigo(ValueError):
    """`ValueError` con codigo: lo lanzan los servicios del portal que ya
    lanzaban `ValueError`. `str(e)` es el texto en castellano de siempre, asi
    que los `except ValueError` y las comprobaciones por texto siguen igual."""

    def __init__(self, codigo: str, **params: Any) -> None:
        self.codigo = codigo
        self.params = params
        super().__init__(texto(codigo, params))


def desde_valor(status_code: int, exc: Exception) -> ErrorDeDominio:
    """El `ErrorDeDominio` de un `ValueError` capturado en un endpoint: con su
    codigo si lo trae (`ErrorConCodigo`), si no con el texto tal cual."""
    if isinstance(exc, ErrorConCodigo):
        return ErrorDeDominio(status_code, str(exc), code=exc.codigo, params=exc.params or {})
    return ErrorDeDominio(status_code, str(exc))
