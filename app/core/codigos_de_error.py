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
}


def texto(codigo: str, params: Optional[dict] = None) -> str:
    """El texto en castellano del codigo con sus datos (o el codigo si no existe)."""
    plantilla = MENSAJES.get(codigo, codigo)
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
