# Matriz de segregación de funciones — {{empresa}}

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

Recoger las funciones incompatibles, los conflictos detectados y sus compensaciones.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `segregacion-funciones` | Segregación de funciones | iso27001 A.5.3, sox ITGC-APD-06, jsox ITGC-SEG-06 |
| `asientos-manuales` | Asientos manuales | sox FC-02, jsox FCRP-02 |

## 4. Funciones y responsabilidades

- **Finanzas**: Es propietaria de los controles sobre la información financiera.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Función A | Permiso o rol | Sí |
| Función B | Permiso o rol incompatible | Sí |
| Riesgo | Qué permite el conflicto | Sí |
| Usuarios en conflicto | Listado | Sí |
| Control compensatorio | Descripción y responsable | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
