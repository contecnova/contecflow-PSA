# Inventario de activos — {{empresa}}

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

Recoger los activos del alcance con su propietario, clasificación y criticidad.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `inventario-activos` | Inventario de activos de información | iso27001 A.5.9, tisax 1.3.1, nis2 art.21.2.i, iec62443 SR 7.8, iec62443 CR 7.8, iec62443 SPE 2 |
| `clasificacion-informacion` | Clasificación de la información | iso27001 A.5.12, tisax 1.3.2, iec62443 SPE 5 |

## 4. Funciones y responsabilidades

- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.
- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Activo | Nombre e identificador de la CMDB | Sí |
| Tipo | Información, sistema, componente OT, servicio | Sí |
| Propietario | Persona responsable | Sí |
| Clasificación | Nivel | Sí |
| Sede o zona | Ubicación | Sí |
| Criticidad | Según el análisis de impacto | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
