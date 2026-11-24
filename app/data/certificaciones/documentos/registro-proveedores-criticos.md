# Registro de proveedores críticos — {{empresa}}

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

Recoger los proveedores críticos y el estado de su evaluación.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `seguridad-proveedores` | Seguridad en la relación con proveedores | iso27001 A.5.19, tisax 6.1.1, nis2 art.21.2.d, iec62443 SPE 1 |
| `seguimiento-proveedores` | Seguimiento de servicios de proveedores e informes de aseguramiento | iso27001 A.5.22, tisax 6.1.1, sox ITGC-CO-05, jsox ITGC-EXT-01 |
| `cadena-suministro-tic` | Seguridad de la cadena de suministro TIC | iso27001 A.5.21, nis2 art.21.2.d, nis2 art.21.3, iec62443 SM-9 |

## 4. Funciones y responsabilidades

- **Responsable de cumplimiento**: Coordina las evidencias y su relación con cada norma.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Proveedor | Nombre | Sí |
| Servicio | Descripción | Sí |
| Criticidad | Nivel | Sí |
| Evaluación | Fecha y resultado | Sí |
| Aseguramiento | Certificados, etiquetas o informes SOC | Sí |
| Próxima revisión | Fecha | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
