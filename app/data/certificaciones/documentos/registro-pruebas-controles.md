# Registro de pruebas de controles — {{empresa}}

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

Recoger cada prueba de diseño o de eficacia y su resultado.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `evaluacion-direccion-control-interno` | Evaluación por la dirección del control interno sobre la información financiera | sox Sec.404(a), jsox FIEA-24-4-4 |
| `independencia-probadores` | Independencia de quien prueba | iec62443 SVV-5 |

## 4. Funciones y responsabilidades

- **Auditoría interna**: Comprueba de forma independiente que se aplica.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Control | Clave común | Sí |
| Tipo de prueba | Diseño o eficacia | Sí |
| Población | Descripción y tamaño | Sí |
| Muestra | Tamaño y selección | Sí |
| Resultado | Eficaz o con excepciones | Sí |
| Probado por | Persona distinta de quien implanta | Sí |
| Fecha | Fecha | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
