"""Asistente de reuniones (19-11-2026): Teams, Zoom y Meet al terminar, bot invitado,
grabación propia, análisis, traducción y GRC. Diseño en `docs/ASISTENTE_DE_REUNIONES.md`.

Módulos:
- `config`: configuración por empresa (secretos cifrados) y validación.
- `consultas`: visibilidad, gestión y serialización.
- `servicio`: altas, audio, consentimiento, acciones, acta, preguntas, búsqueda.
- `transcripcion`: STT permitido por la empresa, VTT y texto pegado a segmentos.
- `analisis`, `vinculacion`, `traduccion`, `almacen`, `eventos`.
- `conectores/` (Teams, Zoom, Meet), `bots/` (interfaz + Recall.ai), `webhooks`.
- `trabajos` (sondeo y retención), `rgpd`, `cumplimiento`.
"""
