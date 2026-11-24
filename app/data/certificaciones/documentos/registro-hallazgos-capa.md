# Registro de hallazgos y acciones correctivas — {{empresa}}

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

Recoger los hallazgos de cualquier auditoría y su tratamiento.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `no-conformidades-acciones-correctivas` | No conformidades y acciones correctivas | iso27001 10.2, nis2 art.21.4, iec62443 SM-11, sox ELC-04, jsox ELC-04 |

## 4. Funciones y responsabilidades

- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **Auditoría interna**: Comprueba de forma independiente que se aplica.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Hallazgo | Descripción | Sí |
| Origen | Auditoría y norma | Sí |
| Tipo | NC mayor, NC menor, observación, oportunidad de mejora | Sí |
| Causa | Análisis | Sí |
| Acción | Descripción, responsable y plazo | Sí |
| Verificación | Quién y cuándo | Sí |
| Cierre | Fecha | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
