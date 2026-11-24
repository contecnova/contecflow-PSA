# Registro de versiones, SBOM y firmas — {{empresa}}

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

Recoger cada versión publicada con su SBOM, revisión independiente y firma.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `sbom-y-versiones-firmadas` | SBOM y versiones etiquetadas y firmadas | iec62443 SM-9, iec62443 SUM-3 |
| `aprobacion-independiente-paso-produccion` | Aprobación independiente del paso a producción | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |

## 4. Funciones y responsabilidades

- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Producto | Nombre | Sí |
| Versión | Etiqueta | Sí |
| SBOM | Referencia del fichero | Sí |
| Revisor independiente | Persona distinta del autor | Sí |
| Firma | Huella y certificado | Sí |
| Fecha de publicación | Fecha | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
