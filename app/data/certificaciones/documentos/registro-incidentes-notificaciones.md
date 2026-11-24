# Registro de incidentes y notificaciones — {{empresa}}

| Campo | Valor |
|---|---|
| Tipo | Registro |
| Código | {{codigo_documento}} |
| Versión | {{version}} |
| Propietario | {{propietario}} |
| Aprobado por | {{aprobador}} (flujo de aprobación de Documentos) |
| Fecha de aprobación | {{fecha_aprobacion}} |
| Próxima revisión | {{fecha_revision}} |
| Clasificación | {{clasificacion}} |
| Alcance | {{alcance}} |

> Plantilla redactada por contecflow. Sustituya los marcadores `{{...}}` y adapte el contenido a su organización. No incluye texto de normas con derechos de autor; si su empresa tiene licencia, puede importar el texto oficial en el catálogo.

## 1. Objeto

Recoger los incidentes y, si son significativos, cada notificación con su sello de tiempo.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `respuesta-incidentes` | Respuesta a incidentes | iso27001 A.5.26, tisax 1.6.2, nis2 art.21.2.b |
| `notificacion-incidentes-significativos` | Notificación de incidentes significativos | nis2 art.23.1, nis2 art.23.3 |
| `alerta-temprana-24h` | Alerta temprana en 24 horas | nis2 art.23.4.a |
| `notificacion-incidente-72h` | Notificación del incidente en 72 horas | nis2 art.23.4.b |
| `informe-final-incidente` | Informe final en un mes | nis2 art.23.4.d, nis2 art.23.4.e |

## 4. Funciones y responsabilidades

- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **Responsable de cumplimiento**: Coordina las evidencias y su relación con cada norma.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Incidente | Referencia del Service Desk | Sí |
| Hora de conocimiento | Fecha y hora | Sí |
| Significativo | Sí o no y motivo | Sí |
| Alerta temprana | Fecha y hora de envío | Sí |
| Notificación | Fecha y hora de envío | Sí |
| Informe final | Fecha de envío | Sí |
| Autoridad | Destinatario | Sí |
| Comunicación a clientes | Sí o no y fecha | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
